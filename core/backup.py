from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from core.data_store import TAGS_FILE, Project, load_project, parse_project, project_payload, relative_key, save_project
from core.scanner import PHOTO_EXTENSIONS, ImageEntry

MAX_METADATA = 16 * 1024 * 1024


@dataclass(frozen=True)
class BackupInfo:
    project: Project
    image_paths: tuple[str, ...] = ()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]


def safe_image_key(value: str) -> str:
    key = relative_key(value)
    if key != value or Path(key).suffix.lower() not in PHOTO_EXTENSIONS:
        raise ValueError('Đường dẫn ảnh trong bản sao lưu không hợp lệ.')
    for part in key.split('/'):
        if (part.endswith((' ', '.')) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', part, re.I)):
            raise ValueError('Tên ảnh không an toàn trên Windows.')
    return key


def create_backup(destination: Path, project: Project, root: Path | None = None,
                  entries: list[ImageEntry] | None = None, progress=lambda _: None) -> Path:
    """Xuất ZIP mới, chỉ công bố tệp khi tất cả dữ liệu đã ghi thành công."""
    entries = entries if entries is not None else []
    if entries and root is None:
        raise ValueError('Cần thư mục nguồn để sao lưu ảnh.')
    # Kiểm tra cả phiên gồm bản ghi ảnh tạm vắng mặt.
    payload = project_payload(project)
    parse_project(payload)
    metadata = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    if len(metadata) > MAX_METADATA:
        raise ValueError('Dữ liệu lựa chọn vượt quá giới hạn sao lưu 16 MB.')
    name = destination / f'Sao-luu-{timestamp()}.zip'
    descriptor, filename = tempfile.mkstemp(dir=destination, prefix='.backup-', suffix='.tmp')
    os.close(descriptor)
    temporary = Path(filename)
    try:
        with ZipFile(temporary, 'w', compression=ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr(TAGS_FILE, metadata)
            archive.writestr('backup.json', json.dumps({
                'backup_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'includes_images': root is not None,
                'image_count': len(entries),
            }))
            seen = set()
            for number, entry in enumerate(entries, 1):
                key = safe_image_key(entry.relative)
                if key.casefold() in seen:
                    raise ValueError('Có tên ảnh trùng nhau khi bỏ qua chữ hoa/thường.')
                seen.add(key.casefold())
                path = (root / key).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise ValueError('Ảnh nằm ngoài thư mục nguồn.')
                before = path.stat()
                if before.st_size != entry.size or before.st_mtime_ns != entry.mtime_ns:
                    raise ValueError(f'Ảnh đã thay đổi. Quét lại thư mục trước khi sao lưu: {key}')
                archive.write(path, 'images/' + key)
                after = path.stat()
                if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
                    raise ValueError(f'Ảnh thay đổi trong khi sao lưu: {key}')
                progress(number)
        os.replace(temporary, name)
        return name
    finally:
        temporary.unlink(missing_ok=True)


def read_small_json(archive: ZipFile, name: str) -> dict:
    if archive.getinfo(name).file_size > MAX_METADATA:
        raise ValueError('Dữ liệu sao lưu quá lớn.')
    return json.loads(archive.read(name).decode('utf-8-sig'))


def inspect_archive(archive: ZipFile) -> BackupInfo:
    names = [item.filename for item in archive.infolist()]
    if len(names) != len({name.casefold() for name in names}):
        raise ValueError('Bản sao lưu chứa tên tệp trùng.')
    project = parse_project(read_small_json(archive, TAGS_FILE))
    images = []
    for item in archive.infolist():
        name = item.filename
        if name in (TAGS_FILE, 'backup.json'):
            continue
        if (not name.startswith('images/') or item.is_dir()
                or ((item.external_attr >> 16) & 0o170000) == 0o120000):
            raise ValueError('Bản sao lưu chứa mục không được hỗ trợ.')
        images.append(safe_image_key(name[len('images/'):]))
    if 'backup.json' in names:
        manifest = read_small_json(archive, 'backup.json')
        if (not isinstance(manifest, dict) or type(manifest.get('backup_version')) is not int
                or manifest['backup_version'] != 1 or type(manifest.get('image_count')) is not int
                or manifest['image_count'] != len(images)
                or type(manifest.get('includes_images')) is not bool
                or (images and not manifest['includes_images'])):
            raise ValueError('Thông tin bản sao lưu không hợp lệ.')
    elif images:
        raise ValueError('Bản sao lưu ảnh thiếu thông tin phiên bản.')
    # Không cho phép a.jpg vừa là file vừa là thư mục cha của file khác.
    files = {key.casefold() for key in images}
    for key in files:
        if any(parent.as_posix() in files for parent in Path(key).parents if parent.as_posix() != '.'):
            raise ValueError('Đường dẫn ảnh xung đột trong bản sao lưu.')
    return BackupInfo(project, tuple(images))


def read_backup(path: Path) -> BackupInfo:
    try:
        if path.suffix.lower() == '.json':
            if path.stat().st_size > MAX_METADATA:
                raise ValueError('Dữ liệu sao lưu quá lớn.')
            return BackupInfo(load_project(path))
        with ZipFile(path) as archive:
            return inspect_archive(archive)
    except (BadZipFile, KeyError, UnicodeError, json.JSONDecodeError, NotImplementedError, RuntimeError) as error:
        raise ValueError('Bản sao lưu bị hỏng hoặc không đúng định dạng.') from error


def restore_images(path: Path, destination: Path, progress=lambda _: None) -> Path:
    """Giải nén vào thư mục mới, giữ nguyên mọi ảnh và dữ liệu hiện có."""
    temporary = Path(tempfile.mkdtemp(dir=destination, prefix='.restore-'))
    try:
        with ZipFile(path) as archive:
            info = inspect_archive(archive)
            if not info.image_paths:
                raise ValueError('Bản sao lưu này không chứa ảnh.')
            required = sum(archive.getinfo('images/' + key).file_size for key in info.image_paths)
            if required + MAX_METADATA > shutil.disk_usage(destination).free:
                raise ValueError('Không đủ dung lượng trống để khôi phục ảnh.')
            for number, key in enumerate(info.image_paths, 1):
                target = temporary / key
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open('images/' + key) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                progress(number)
            save_project(temporary / TAGS_FILE, info.project)
        result = destination / f'Khoi-phuc-{timestamp()}'
        os.rename(temporary, result)
        return result
    except (BadZipFile, KeyError, UnicodeError, NotImplementedError, RuntimeError) as error:
        raise ValueError('Bản sao lưu bị hỏng. Chưa công bố thư mục khôi phục.') from error
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def restore_selection(root: Path, project: Project, recovery_directory: Path) -> Path | None:
    """Lưu bản dữ liệu cũ trước khi thay thế nguyên tử; hỗ trợ cả JSON cũ bị lỗi."""
    parse_project(project_payload(project))
    previous = root / TAGS_FILE
    recovery = None
    if previous.exists():
        recovery_directory.mkdir(parents=True, exist_ok=True)
        recovery = recovery_directory / f'Truoc-khoi-phuc-{timestamp()}.json'
        shutil.copy2(previous, recovery)
    save_project(previous, project)
    return recovery
