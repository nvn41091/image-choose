from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from threading import Event
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from core.data_store import TAGS_FILE, Project, save_project
from core.scanner import RAW_EXTENSIONS, scan

log = logging.getLogger(__name__)


def selected_paths(project: Project) -> list[str]:
    return sorted((path for path, photo in project.photos.items() if photo.category_ids),
                  key=str.casefold)


def lightroom_warnings(project: Project) -> list[str]:
    stems = [Path(path).stem for path in selected_paths(project)]
    counts = Counter(stem.casefold() for stem in stems)
    return sorted({stem for stem in stems if ',' in stem or counts[stem.casefold()] > 1},
                  key=str.casefold)


def unique_name(name: str, used: set[str], limit: int) -> str:
    number = 1
    candidate = name[:limit].rstrip(" .'")
    while candidate.casefold() in used:
        number += 1
        suffix = f' ({number})'
        candidate = name[:limit - len(suffix)].rstrip(" .'") + suffix
    used.add(candidate.casefold())
    return candidate


def windows_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '-', value).strip(' .')[:90].rstrip(' .')
    if not value:
        return fallback
    return f'_{value}' if PureWindowsPath(value).is_reserved() else value


def sheet_name(value: str, used: set[str]) -> str:
    clean = re.sub(r'[\[\]:*?/\\\x00-\x1f]+', '-', value).strip(" .'") or 'Loại ảnh'
    return unique_name(clean, used, 31)


def excel_text(value: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)


def create_workbook(path: Path, project: Project, exported_at: datetime) -> None:
    book = Workbook()
    summary = book.active
    summary.title = 'Tổng hợp'
    used = {summary.title.casefold(), 'history'}
    sheets = {item.id: book.create_sheet(sheet_name(item.name, used)) for item in project.categories}
    names = {item.id: item.name for item in project.categories}

    def add_row(sheet, values):
        sheet.append([excel_text(value) if isinstance(value, str) else value for value in values])
        # Tên tệp và ghi chú là dữ liệu văn bản, kể cả khi bắt đầu bằng dấu bằng.
        for cell in sheet[sheet.max_row]:
            if cell.data_type in {'f', 'e'}:
                cell.data_type = 's'

    for sheet in [summary, *sheets.values()]:
        add_row(sheet, ['Khách hàng', project.customer_name or 'Chưa nhập tên'])
        add_row(sheet, ['Ngày xuất', exported_at.strftime('%d/%m/%Y %H:%M')])
        add_row(sheet, ['Tên file', 'Loại', 'Số sao', 'Ghi chú chỉnh sửa'])
        sheet.freeze_panes = 'A4'
        for cell in sheet[3]:
            cell.fill = PatternFill('solid', fgColor='304B43')
            cell.font = Font(bold=True, color='FFFFFF')
        for column, width in zip('ABCD', (36, 45, 12, 58)):
            sheet.column_dimensions[column].width = width

    for relative in selected_paths(project):
        photo = project.photos[relative]
        filename = Path(relative).name
        add_row(summary, [filename, '; '.join(names[tag] for tag in photo.category_ids), photo.stars, photo.note])
        for tag in photo.category_ids:
            add_row(sheets[tag], [filename, names[tag], photo.stars, photo.note])

    for sheet in book:
        sheet.auto_filter.ref = f'A3:D{sheet.max_row}'
        for row in sheet.iter_rows(min_row=4, min_col=4, max_col=4):
            row[0].alignment = Alignment(wrap_text=True, vertical='top')
    book.save(path)


def export_package(destination: Path, project: Project, compressed: bool) -> tuple[Path, Path | None]:
    now = datetime.now().astimezone()
    base = f'{windows_name(project.customer_name, "ChonAnhCuoi")} - {now:%Y%m%d-%H%M%S}'
    selected = selected_paths(project)
    filenames = ('danh_sach_anh.xlsx', 'lightroom.txt', TAGS_FILE)
    with tempfile.TemporaryDirectory(dir=destination, prefix='.xuat-anh-') as directory:
        staging = Path(directory) / 'goi'
        staging.mkdir()
        create_workbook(staging / filenames[0], project, now)
        with (staging / filenames[1]).open('w', encoding='utf-8', newline='\n') as stream:
            for category in project.categories:
                stems = [Path(relative).stem for relative in selected
                         if category.id in project.photos[relative].category_ids]
                stream.write(f'{category.name}: {", ".join(stems)}\n')
        save_project(staging / TAGS_FILE, project)

        index = 1
        while True:
            folder = destination / (base if index == 1 else f'{base} ({index})')
            archive = folder.with_name(f'{folder.name}.zip')
            if not folder.exists() and not archive.exists():
                break
            index += 1

        temporary_zip = Path(directory) / 'goi.zip'
        if compressed:
            with ZipFile(temporary_zip, 'w', ZIP_DEFLATED) as package:
                for name in filenames:
                    package.write(staging / name, name)
        staging.rename(folder)
        try:
            if compressed:
                temporary_zip.rename(archive)
        except OSError:
            folder.rename(staging)
            raise
    return folder, archive if compressed else None


def match_raw(root: Path, project: Project) -> tuple[dict[str, str], list[str]]:
    by_path = defaultdict(list)
    by_name = defaultdict(list)
    for entry in scan(root, True, Event(), RAW_EXTENSIONS):
        path = Path(entry.relative)
        by_path[path.with_suffix('').as_posix().casefold()].append(entry.relative)
        by_name[path.stem.casefold()].append(entry.relative)

    matches = {}
    issues = []
    for relative in selected_paths(project):
        path = Path(relative)
        candidates = by_path.get(path.with_suffix('').as_posix().casefold()) or by_name.get(path.stem.casefold(), [])
        if len(candidates) == 1:
            matches[relative] = candidates[0]
        elif candidates:
            issues.append(f'{relative} — nhiều kết quả: {", ".join(candidates)}')
        else:
            issues.append(f'{relative} — chưa tìm thấy RAW')
    return matches, issues


@dataclass(frozen=True)
class CopyItem:
    source: Path
    destination: Path


def check_copy_destination(root: Path, destination: Path) -> Path:
    target = destination.resolve()
    if target.is_relative_to(root.resolve()):
        raise ValueError('Hãy chọn thư mục đích bên ngoài thư mục ảnh nguồn.')
    return target


def plan_copy(root: Path, destination: Path, project: Project, matches: dict[str, str]) -> list[CopyItem]:
    target = check_copy_destination(root, destination)
    used: set[str] = set()
    folders = {item.id: unique_name(windows_name(item.name, 'Loại ảnh'), used, 100)
               for item in project.categories}
    items = {}
    for relative, source in matches.items():
        for tag in project.photos[relative].category_ids:
            output = target / folders[tag] / source
            items[os.path.normcase(output)] = CopyItem(root / source, output)
    return list(items.values())


def execute_copy(root: Path, destination: Path, items: list[CopyItem], confirmed: set[Path],
                 progress) -> tuple[int, int, list[str]]:
    copied, skipped, issues = 0, 0, []
    root = root.resolve()
    target = check_copy_destination(root, destination)
    for index, item in enumerate(items, 1):
        temporary = None
        try:
            overwrite = item.destination in confirmed
            resolved_source = item.source.resolve(strict=True)
            resolved_output = item.destination.resolve()
            if (not resolved_source.is_relative_to(root) or item.destination.is_symlink()
                    or resolved_output.is_relative_to(root) or not resolved_output.is_relative_to(target)):
                raise ValueError('Đường dẫn vượt ra ngoài phạm vi sao chép an toàn.')
            if item.destination.exists() and not overwrite:
                skipped += 1
                continue
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=item.destination.parent, prefix='.copy-', delete=False) as stream:
                temporary = Path(stream.name)
            shutil.copy2(resolved_source, temporary)
            if overwrite:
                os.replace(temporary, item.destination)
            elif os.name == 'nt':
                temporary.rename(item.destination)
            else:
                os.link(temporary, item.destination)
            copied += 1
        except FileExistsError:
            skipped += 1
        except (OSError, ValueError) as error:
            issues.append(f'{item.source.name} — {error}')
            log.warning('Không sao chép được %s', item.source, exc_info=True)
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    log.warning('Không dọn được tệp tạm %s', temporary, exc_info=True)
            if index == len(items) or index % 10 == 0:
                progress(index)
    return copied, skipped, issues
