from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QObject, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from core.data_store import Project
from core.scanner import FolderEntry, ImageEntry
from ui.jobs import Jobs, to_qimage

ENTRY = Qt.ItemDataRole.UserRole + 1
PHOTO = ENTRY + 1
LOADING = object()
CARD_DETAILS_HEIGHT = 79
CARD_INSET = 10
DEFAULT_COLUMNS = 4


class Thumbnails(QObject):
    ready = Signal(str)
    progress = Signal(int, int)

    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.jobs = Jobs(self, threads=4)
        self.root = None
        self.generation = 0
        self.size = 256
        self.queued = OrderedDict()
        self.running = set()
        self.images = OrderedDict()
        self.done_count = self.total = 0
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self._pump)

    def reset(self, root, size):
        self.generation += 1
        self.root, self.size = root, size
        self.queued.clear()
        self.images.clear()
        self.done_count = self.total = 0
        self.progress.emit(0, 0)

    def request(self, entry):
        path = entry.relative
        if path in self.images:
            self.images.move_to_end(path)
            return self.images[path]
        if self.root is None or (self.generation, path) in self.running:
            return LOADING
        if path not in self.queued:
            self.total += 1
            self.queued[path] = entry
            if len(self.queued) > 128:
                self.queued.popitem(last=False)
                self.total -= 1
        else:
            self.queued.move_to_end(path)
        if not self.timer.isActive():
            self.timer.start(0)
        return LOADING

    def _pump(self):
        self.progress.emit(self.done_count, self.total)
        while self.queued and len(self.running) < 4:
            path, entry = self.queued.popitem(last=True)
            generation, root, size = self.generation, self.root, self.size
            self.running.add((generation, path))
            self.jobs.start(lambda _, r=root, e=entry, s=size: to_qimage(self.cache.get(r, e, s)),
                            lambda image, error, g=generation, p=path: self._complete(g, p, image, error))

    def _complete(self, generation, path, image, error):
        self.running.discard((generation, path))
        if generation == self.generation:
            self.images[path] = None if error else QPixmap.fromImage(image)
            if len(self.images) > 180:
                self.images.popitem(last=False)
            self.done_count += 1
            self.ready.emit(path)
        self._pump()


class GalleryModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.rows = {}
        self.project = Project()
        self.names = {}

    def set_entries(self, entries, project):
        self.beginResetModel()
        self.entries = entries
        self.rows = {entry.relative: row for row, entry in enumerate(entries)}
        self.project = project
        self.names = {item.id: item.name for item in project.categories}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.name
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f'Thư mục {entry.name}' if isinstance(entry, FolderEntry) else entry.name
        if role == ENTRY:
            return entry
        if isinstance(entry, FolderEntry):
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole):
                return f'Mở thư mục {entry.relative}'
            return None
        if role == PHOTO:
            return self.project.photo(entry.relative)
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole):
            photo = self.project.photo(entry.relative)
            detail = [entry.relative, *(self.names[tag] for tag in photo.category_ids)]
            if photo.stars:
                detail.append(f'{photo.stars} sao')
            if photo.ai_score is not None:
                detail.append(f'Điểm ảnh: {photo.ai_score}/100')
            if photo.favorite:
                detail.append('Yêu thích')
            if photo.note:
                detail.append('Có ghi chú chỉnh sửa')
            return '\n'.join(detail)
        return None

    def changed(self, paths):
        rows = sorted(self.rows[path] for path in set(paths) if path in self.rows)
        if not rows:
            return
        # Một tín hiệu cho thao tác hàng loạt để chỉ vẽ lại viewport một lần.
        self.dataChanged.emit(self.index(rows[0], 0), self.index(rows[-1], 0))


class Gallery(QListView):
    grid_resized = Signal()

    def __init__(self, thumbnails, parent=None):
        super().__init__(parent)
        self.columns = DEFAULT_COLUMNS
        self.gallery_model = GalleryModel(self)
        self.setModel(self.gallery_model)
        self.delegate = PhotoDelegate(thumbnails, self)
        self.setItemDelegate(self.delegate)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(160)
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Movement.Static)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Giữ chỗ cho thanh cuộn để chiều rộng ô không dao động khi lưới vừa đủ một trang.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAccessibleName('Lưới ảnh')
        self.update_grid()
        thumbnails.ready.connect(self.thumbnail_ready)

    def thumbnail_ready(self, path):
        if self.isVisible() and path in self.gallery_model.rows:
            rect = self.visualRect(self.gallery_model.index(self.gallery_model.rows[path], 0))
            self.viewport().update(rect)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Resize and hasattr(self, 'columns'):
            self.update_grid()
        return super().viewportEvent(event)

    def set_columns(self, columns):
        self.columns = columns
        self.update_grid()

    def update_grid(self):
        # QListView xuống hàng nếu mép ô chạm đúng mép viewport.
        cell = max(2 * CARD_INSET + 1, (self.viewport().width() - 1) // self.columns)
        size = QSize(cell, cell - 2 * CARD_INSET + CARD_DETAILS_HEIGHT)
        if size != self.gridSize():
            self.setGridSize(size)
            self.grid_resized.emit()

    def thumbnail_size(self):
        # Dùng các nấc cache thay vì tạo kích thước mới cho mỗi pixel khi kéo cửa sổ.
        pixels = (self.gridSize().width() - 2 * CARD_INSET) * self.devicePixelRatioF()
        return max(64, min(512, int((pixels + 63) // 64) * 64))

    def selected_paths(self):
        entries = (index.data(ENTRY) for index in sorted(self.selectedIndexes(), key=QModelIndex.row))
        return [entry.relative for entry in entries if isinstance(entry, ImageEntry)]


class PhotoDelegate(QStyledItemDelegate):
    def __init__(self, thumbnails, parent):
        super().__init__(parent)
        self.thumbnails = thumbnails
        self.categories = {}

    def sizeHint(self, option, index):
        return self.parent().gridSize()

    def paint(self, painter, option, index):
        entry, photo = index.data(ENTRY), index.data(PHOTO)
        if entry is None:
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        palette = option.palette
        text_color = palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        card = option.rect.adjusted(4, 4, -4, -4)
        side = option.rect.width() - 2 * CARD_INSET
        image_rect = QRect(option.rect.x() + CARD_INSET, option.rect.y() + CARD_INSET, side, side)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = text_color if focused and selected else palette.color(
            QPalette.ColorRole.Highlight if focused else QPalette.ColorRole.Mid)
        painter.setPen(QPen(outline, 2 if focused else 1))
        painter.setBrush(palette.color(QPalette.ColorRole.Highlight if selected else QPalette.ColorRole.Base))
        painter.drawRoundedRect(card, 8, 8)
        painter.fillRect(image_rect, palette.color(QPalette.ColorRole.AlternateBase))
        is_folder = isinstance(entry, FolderEntry)
        if is_folder:
            icon = self.parent().style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            icon_side = min(side - 6, 56)
            if icon_side > 0:
                target = QRect(0, 0, icon_side, icon_side)
                target.moveCenter(image_rect.center())
                icon.paint(painter, target)
        else:
            self.paint_thumbnail(painter, image_rect, palette, entry)

        painter.setPen(text_color)
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        left, width = image_rect.left(), image_rect.width()
        first = QRect(left, image_rect.bottom() + 5, width, 20)
        painter.drawText(first, Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(entry.name, Qt.TextElideMode.ElideMiddle, width))
        painter.setFont(option.font)
        y = first.bottom() + 3
        if is_folder:
            painter.drawText(QRect(left, y, width, 20), Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText('Thư mục', Qt.TextElideMode.ElideRight, width))
        else:
            self.paint_labels(painter, photo, text_color, left, width, y)
        painter.restore()

    def paint_thumbnail(self, painter, image_rect, palette, entry):
        image = self.thumbnails.request(entry)
        if image is LOADING or image is None:
            painter.setPen(palette.color(QPalette.ColorRole.Text))
            label = 'Đang tải…' if image is LOADING else '⚠  Ảnh lỗi'
            painter.drawText(image_rect, Qt.AlignmentFlag.AlignCenter, painter.fontMetrics().elidedText(
                label, Qt.TextElideMode.ElideRight, image_rect.width()))
        else:
            scaled = image.size().scaled(image_rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(image_rect.center().x() - scaled.width() // 2,
                           image_rect.center().y() - scaled.height() // 2, scaled.width(), scaled.height())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, image)

    def paint_labels(self, painter, photo, text_color, left, width, y):
        categories = [self.categories[tag] for tag in photo.category_ids if tag in self.categories]
        if categories:
            x = left
            for category in categories:
                if x + 10 > left + width // 2:
                    break
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(category.color))
                painter.drawEllipse(x, y + 6, 8, 8)
                x += 11
            painter.setPen(text_color)
            label = ' · '.join(category.name for category in categories)
            painter.drawText(QRect(x + 2, y, left + width - x - 2, 20), Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, left + width - x - 2))
        markers = [f'★ {photo.stars}' if photo.stars else '',
                   f'Điểm {photo.ai_score}' if photo.ai_score is not None else '',
                   '♥' if photo.favorite else '', '✎' if photo.note else '']
        painter.setPen(text_color)
        marker_text = painter.fontMetrics().elidedText('  '.join(filter(None, markers)), Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRect(left, y + 17, width, 18), Qt.AlignmentFlag.AlignVCenter, marker_text)
