from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from core.scanner import ImageEntry

log = logging.getLogger(__name__)


def read_image(path: Path, size: int) -> tuple[Image.Image, tuple[int, int]]:
    with Image.open(path) as source:
        source.seek(0)
        width, height = source.size
        if source.getexif().get(274) in (5, 6, 7, 8):
            width, height = height, width
        # Giảm kích thước trước khi xoay để tránh tạo thêm bản sao toàn ảnh.
        source.thumbnail((size, size), Image.Resampling.LANCZOS)
        corrected = ImageOps.exif_transpose(source).convert('RGBA')
        return corrected, (width, height)


class ThumbnailCache:
    def __init__(self, directory: Path):
        self.directory = directory

    def get(self, root: Path, entry: ImageEntry, size: int) -> Image.Image:
        path = root / entry.relative
        identity = f'v1\0{os.path.normcase(path)}\0{entry.size}\0{entry.mtime_ns}\0{size}'
        key = hashlib.sha256(identity.encode('utf-8', errors='surrogatepass')).hexdigest()
        cached = self.directory / f'{key}.png'
        try:
            with Image.open(cached) as image:
                return image.convert('RGBA')
        except FileNotFoundError:
            pass
        except OSError:
            log.debug('Tạo lại thumbnail cache %s', cached, exc_info=True)

        image, _ = read_image(path, size)
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.directory, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                image.save(stream, format='PNG')
            os.replace(temporary, cached)
        except OSError:
            log.debug('Không ghi được cache %s', cached, exc_info=True)
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    log.debug('Không dọn được cache tạm %s', temporary, exc_info=True)
        return image

    def trim(self, budget: int = 768 * 1024 * 1024) -> None:
        files = []
        for path in self.directory.glob('*.png'):
            try:
                info = path.stat()
                files.append((info.st_mtime, info.st_size, path))
            except OSError:
                continue
        total = sum(item[1] for item in files)
        for _, size, path in sorted(files):
            if total <= budget:
                break
            try:
                path.unlink(missing_ok=True)
                total -= size
            except OSError:
                continue
