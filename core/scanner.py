from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from threading import Event

PHOTO_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff'})
RAW_EXTENSIONS = frozenset({'.cr2', '.cr3', '.nef', '.arw'})
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageEntry:
    relative: str
    name: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class FolderEntry:
    relative: str
    name: str


def scan(root: Path, recursive: bool, cancel: Event, extensions=PHOTO_EXTENSIONS,
         *, folders: list[FolderEntry] | None = None) -> list[ImageEntry]:
    pending = [root]
    entries = []
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as children:
                for child in children:
                    if cancel.is_set():
                        return []
                    try:
                        if child.is_dir(follow_symlinks=False):
                            if recursive:
                                attributes = getattr(child.stat(follow_symlinks=False), 'st_file_attributes', 0)
                                # Bỏ qua junction và symlink để tránh vòng lặp và đi ra ngoài thư mục ảnh.
                                if not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                                    pending.append(Path(child.path))
                                    if folders is not None:
                                        folders.append(FolderEntry(Path(child.path).relative_to(root).as_posix(), child.name))
                        elif (Path(child.name).suffix.lower() in extensions
                              and child.is_file(follow_symlinks=False)):
                            info = child.stat(follow_symlinks=False)
                            relative = Path(child.path).relative_to(root).as_posix()
                            entries.append(ImageEntry(relative, child.name, info.st_size, info.st_mtime_ns))
                    except OSError:
                        log.warning('Không đọc được mục %s', child.path, exc_info=True)
        except OSError:
            if folder == root:
                raise
            log.warning('Không đọc được thư mục %s', folder, exc_info=True)
    return sorted(entries, key=lambda entry: (entry.relative.casefold(), entry.relative))
