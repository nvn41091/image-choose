from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Set
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

TAGS_FILE = 'photo_tags.json'
PACKAGE_FILE = 'goi_chup.json'
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    color: str
    shortcut: int
    max_count: int | None = None


DEFAULTS = (
    Category('album', 'Album', '#2563eb', 1),
    Category('phong_lon', 'Phóng lớn', '#c62828', 2),
    Category('anh_de_ban', 'Ảnh để bàn / ảnh nhỏ', '#b45309', 3),
    Category('mang_xa_hoi', 'Đăng mạng xã hội', '#15803d', 4),
    Category('chinh_sua', 'Cần chỉnh sửa đặc biệt', '#7e22ce', 5),
)


@dataclass(frozen=True)
class Photo:
    category_ids: tuple[str, ...] = ()
    stars: int = 0
    favorite: bool = False
    note: str = ''
    updated_at: str = ''
    ai_score: int | None = None


EMPTY_PHOTO = Photo()


@dataclass
class Project:
    customer_name: str = ''
    categories: list[Category] = field(default_factory=lambda: list(DEFAULTS))
    photos: dict[str, Photo] = field(default_factory=dict)
    needs_save: bool = field(default=False, compare=False, repr=False)

    def photo(self, path: str) -> Photo:
        return self.photos.get(path, EMPTY_PHOTO)

    def update(self, path: str, **changes) -> bool:
        previous = self.photo(path)
        updated = replace(previous, **changes)
        if updated == previous:
            return False
        if updated.category_ids or updated.stars or updated.favorite or updated.note or updated.ai_score is not None:
            self.photos[path] = replace(updated, updated_at=datetime.now(timezone.utc).isoformat())
        else:
            self.photos.pop(path, None)
        return True

    def snapshot(self, scope: Set[str]) -> Project:
        return Project(self.customer_name, self.categories.copy(), {
            path: photo for path, photo in self.photos.items() if path in scope
        })


def read_json(path: Path) -> dict:
    try:
        with path.open(encoding='utf-8-sig') as stream:
            data = json.load(stream)
    except json.JSONDecodeError as error:
        raise ValueError(f'JSON không hợp lệ ở dòng {error.lineno}, cột {error.colno}.') from error
    except UnicodeDecodeError as error:
        raise ValueError('Tệp JSON phải dùng mã hóa UTF-8.') from error
    if not isinstance(data, dict):
        raise ValueError('Nội dung JSON phải là một đối tượng.')
    return data


def relative_key(value: str) -> str:
    path = PureWindowsPath(value)
    if (not path.parts or path.anchor or '..' in path.parts
            or any(re.search(r'[<>:"|?*\x00-\x1f]', part) for part in path.parts)):
        raise ValueError('Đường dẫn ảnh tương đối không hợp lệ.')
    return path.as_posix()


def valid_limit(value: object) -> bool:
    return value is None or (type(value) is int and 0 <= value <= 999_999_999)


def validate_categories(categories: list[Category]) -> None:
    ids, names, shortcuts = set(), set(), set()
    for item in categories:
        if (not isinstance(item.id, str) or not item.id or item.id in ids
                or not isinstance(item.name, str) or not item.name.strip()
                or item.name.strip().casefold() in names
                or any(ord(char) < 32 for char in item.name)
                or not isinstance(item.color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', item.color)
                or type(item.shortcut) is not int or not 1 <= item.shortcut <= 9
                or item.shortcut in shortcuts or not valid_limit(item.max_count)):
            raise ValueError('Kiểm tra tên loại, màu, giới hạn và phím tắt. Mỗi loại cần tên và phím tắt riêng.')
        ids.add(item.id)
        names.add(item.name.strip().casefold())
        shortcuts.add(item.shortcut)


def load_project(path: Path) -> Project:
    return parse_project(read_json(path))


def clean_note(note: str) -> str:
    """Bỏ tiền tố cũ ở đầu dòng, giữ nguyên nội dung và các lần nhắc ở giữa dòng."""
    return re.sub(r'(?m)^\[ChatGPT\][ \t]?', '', note)


def parse_project(data: dict) -> Project:
    if not isinstance(data, dict):
        raise ValueError('Nội dung JSON phải là một đối tượng.')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('Phiên bản photo_tags.json chưa được hỗ trợ.')
    try:
        categories = [Category(**item) for item in data['categories']]
        validate_categories(categories)
        ids = {category.id for category in categories}
        customer = data.get('customer_name', '')
        if not isinstance(customer, str):
            raise ValueError('Tên khách hàng không hợp lệ.')
        photos = {}
        needs_save = False
        for relative, values in data['photos'].items():
            key = relative_key(relative)
            tags = values.get('category_ids', [])
            stars = values.get('stars', 0)
            favorite = values.get('favorite', False)
            note = values.get('note', '')
            updated = values.get('updated_at', '')
            ai_score = values.get('ai_score')
            if (not isinstance(tags, list) or any(not isinstance(tag, str) or tag not in ids for tag in tags)
                    or type(stars) is not int or not 0 <= stars <= 5 or type(favorite) is not bool
                    or not isinstance(note, str) or not isinstance(updated, str) or key in photos
                    or (ai_score is not None and (type(ai_score) is not int or not 0 <= ai_score <= 100))):
                raise ValueError(f'Dữ liệu ảnh không hợp lệ: {key}')
            cleaned = clean_note(note)
            needs_save = needs_save or cleaned != note
            photos[key] = Photo(tuple(dict.fromkeys(tags)), stars, favorite, cleaned, updated, ai_score)
        return Project(customer, categories, photos, needs_save=needs_save)
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError('Cấu trúc photo_tags.json không hợp lệ.') from error


def new_project(root: Path) -> Project:
    try:
        data = read_json(root / PACKAGE_FILE)
    except FileNotFoundError:
        return Project()
    name = data.get('customer_name', '')
    limits = data.get('limits', {})
    if (not isinstance(name, str) or not isinstance(limits, dict)
            or any(key not in {item.id for item in DEFAULTS} or not valid_limit(value)
                   for key, value in limits.items())):
        raise ValueError('Kiểm tra tên khách hàng, mã loại và giới hạn trong goi_chup.json.')
    return Project(name, [replace(item, max_count=limits.get(item.id)) for item in DEFAULTS])


def project_payload(project: Project) -> dict:
    return {'schema_version': 1, 'customer_name': project.customer_name,
            'categories': [asdict(item) for item in project.categories],
            'photos': {key: {**asdict(photo), 'category_ids': list(photo.category_ids)}
                       for key, photo in project.photos.items()}}


def save_project(path: Path, project: Project) -> None:
    payload = project_payload(project)
    # Tệp tạm nằm cạnh tệp đích để việc thay thế diễn ra trên cùng ổ đĩa.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=path.parent,
                                     prefix='.photo_tags-', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(temporary, path)
            project.needs_save = False
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)


def reconcile_paths(root: Path, project: Project, scanned: list[str], recursive: bool) -> bool:
    """Bỏ qua bản ghi ngoài phạm vi và khớp lại cách viết hoa trên Windows."""
    lookup = {os.path.normcase(path): path for path in scanned}
    changed = False
    for path in list(project.photos):
        if not recursive and '/' in path:
            continue
        actual = lookup.get(os.path.normcase(path))
        if actual and actual != path:
            photo = project.photos.pop(path)
            project.photos.setdefault(actual, photo)
            changed = True
        elif actual is None and not (root / path).is_file():
            log.warning('Bỏ qua ảnh đã mất hoặc đổi tên: %s', root / path)
            # Giữ bản ghi trên đĩa để có thể khôi phục khi ảnh xuất hiện lại.
    return changed


def counts(project: Project, paths) -> tuple[int, dict[str, int]]:
    result = dict.fromkeys((category.id for category in project.categories), 0)
    total = 0
    for path in paths:
        tags = project.photo(path).category_ids
        total += bool(tags)
        for tag in tags:
            result[tag] += 1
    return total, result


def category_change(project: Project, paths: list[str], category_id: str) -> tuple[bool, list[str]]:
    missing = [path for path in paths if category_id not in project.photo(path).category_ids]
    return (True, missing) if missing else (False, paths)
