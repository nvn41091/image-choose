from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from core.thumbnail_cache import read_image
from ui.dialogs import wrapping
from ui.jobs import to_qimage


class Canvas(QWidget):
    view_changed = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.message = 'Đang tải ảnh…'
        self.zoom = 1.0
        self.center = QPointF(0.5, 0.5)
        self.drag = None
        self.setMinimumSize(220, 140)
        self.setAccessibleName('Ảnh xem lớn')
        self.setAccessibleDescription('Dùng con lăn để phóng to và kéo để di chuyển ảnh.')

    def set_image(self, image=None, error=False):
        self.pixmap = QPixmap.fromImage(image) if image is not None else QPixmap()
        self.message = '⚠  Không đọc được ảnh' if error else 'Đang tải ảnh…'
        self.update()

    def dimensions(self, zoom):
        if self.pixmap.isNull():
            return 1.0, 1.0
        fit = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        return self.pixmap.width() * fit * zoom, self.pixmap.height() * fit * zoom

    def image_rect(self):
        width, height = self.dimensions(self.zoom)
        # Tâm chuẩn hóa cho phép các ảnh khác tỉ lệ dùng chung trạng thái pan.
        x = self.clamp_center(self.center.x(), self.width(), width)
        y = self.clamp_center(self.center.y(), self.height(), height)
        return QRectF(self.width() / 2 - x * width, self.height() / 2 - y * height, width, height)

    @staticmethod
    def clamp_center(value, viewport, image):
        edge = min(0.5, viewport / (2 * image))
        return min(1 - edge, max(edge, value))

    def set_view(self, zoom, x, y):
        self.zoom, self.center = zoom, QPointF(x, y)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().alternateBase())
        if self.pixmap.isNull():
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        else:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.image_rect(), self.pixmap, QRectF(self.pixmap.rect()))

    def change_zoom(self, factor, position=None):
        if self.pixmap.isNull():
            return
        new_zoom = min(8.0, max(1.0, self.zoom * factor))
        if new_zoom == 1.0:
            self.view_changed.emit(1.0, 0.5, 0.5)
            return
        if new_zoom == self.zoom:
            return
        position = position or QPointF(self.width() / 2, self.height() / 2)
        rect = self.image_rect()
        width, height = self.dimensions(new_zoom)
        x = (position.x() - rect.x()) / rect.width() - (position.x() - self.width() / 2) / width
        y = (position.y() - rect.y()) / rect.height() - (position.y() - self.height() / 2) / height
        self.view_changed.emit(new_zoom, min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            self.change_zoom(1.25 ** steps, event.position())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.zoom > 1 and not self.pixmap.isNull():
            self.drag = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag is None:
            return
        delta = event.position() - self.drag
        self.drag = event.position()
        rect = self.image_rect()
        x = (self.width() / 2 - rect.x() - delta.x()) / rect.width()
        y = (self.height() / 2 - rect.y() - delta.y()) / rect.height()
        x = self.clamp_center(x, self.width(), rect.width()) if rect.width() > self.width() else self.center.x()
        y = self.clamp_center(y, self.height(), rect.height()) if rect.height() > self.height() else self.center.y()
        self.view_changed.emit(self.zoom, x, y)

    def mouseReleaseEvent(self, event):
        self.drag = None
        self.unsetCursor()


def load_preview(path):
    image, resolution = read_image(path, 4096)
    return to_qimage(image), resolution


class ViewerPanel(QWidget):
    def __init__(self, window, parent):
        super().__init__(parent)
        self.window = window
        self.entry = None
        self.token = None
        self.loading_entry = None
        self.canvas = Canvas(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)
        self.details = wrapping()
        layout.addWidget(self.details)
        self.tags = wrapping()
        layout.addWidget(self.tags)
        controls = QHBoxLayout()
        self.tag_button = QPushButton('Gán loại')
        self.tag_menu = QMenu(self.tag_button)
        self.tag_button.setMenu(self.tag_menu)
        controls.addWidget(self.tag_button)
        for text, action in (('Thu nhỏ', lambda: self.canvas.change_zoom(0.8)),
                             ('Phóng to', lambda: self.canvas.change_zoom(1.25))):
            button = QPushButton(text)
            button.clicked.connect(action)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)

    def show_entry(self, entry):
        self.entry = entry
        self.canvas.set_image()
        self.canvas.setAccessibleName(f'Ảnh xem lớn {entry.name}')
        self.details.setText(f'{entry.name}  ·  {entry.size / 1024:,.0f} KB')
        self.details.setToolTip(entry.relative)
        self.refresh_tags()
        if self.token is None:
            self.load_current()

    def load_current(self):
        self.loading_entry = self.entry
        path = self.window.root / self.entry.relative
        self.token = self.window.jobs.start(lambda _: load_preview(path), self.on_loaded)

    def on_loaded(self, result, error):
        self.token = None
        if self.loading_entry != self.entry:
            self.load_current()
        elif error:
            self.canvas.set_image(error=True)
        else:
            image, (width, height) = result
            self.details.setText(f'{self.entry.name}  ·  {self.entry.size / 1024:,.0f} KB  ·  {width} × {height} px')
            self.canvas.set_image(image)

    def refresh_tags(self):
        path = self.entry.relative
        project = self.window.project
        tags = project.photo(path).category_ids
        names = [item.name for item in project.categories if item.id in tags]
        self.tags.setText(' · '.join(names) or 'Chưa gán loại')
        self.tag_button.setAccessibleName(f'Gán loại cho {self.entry.name}')
        self.tag_button.setEnabled(self.window.editable() and bool(project.categories))
        self.window.fill_tag_menu(self.tag_menu, [path], self.refresh_tags, self)

    def stop(self):
        if self.token is not None:
            self.window.jobs.forget(self.token)


class ViewerDialog(QDialog):
    def __init__(self, window, entries, index=0, compare=False):
        super().__init__(window)
        self.window, self.entries, self.index = window, entries, index
        self.setWindowTitle('So sánh ảnh' if compare else 'Xem ảnh lớn')
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.position = QLabel()
        if not compare:
            self.previous = QPushButton('Ảnh trước')
            self.next = QPushButton('Ảnh sau')
            self.previous.clicked.connect(lambda: self.move_by(-1))
            self.next.clicked.connect(lambda: self.move_by(1))
            bar.addWidget(self.previous)
            bar.addWidget(self.next)
            bar.addWidget(self.position)
            for key, offset in (('Left', -1), ('Right', 1)):
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(lambda step=offset: self.move_by(step))
            for key in range(1, 10):
                shortcut = QShortcut(QKeySequence(str(key)), self)
                shortcut.activated.connect(lambda number=key: self.apply_shortcut(number))
        else:
            bar.addWidget(QLabel(f'{len(entries)} ảnh  ·  Phóng to và kéo đồng bộ'))
        bar.addStretch()
        reset = QPushButton('Vừa khung')
        reset.clicked.connect(lambda: self.sync_view(1.0, 0.5, 0.5))
        bar.addWidget(reset)
        close = QPushButton('Đóng')
        close.clicked.connect(self.accept)
        bar.addWidget(close)
        layout.addLayout(bar)
        grid = QGridLayout()
        self.panels = [ViewerPanel(window, self) for _ in range(len(entries) if compare else 1)]
        for i, panel in enumerate(self.panels):
            grid.addWidget(panel, i // 2, i % 2)
            panel.canvas.view_changed.connect(self.sync_view)
        layout.addLayout(grid, 1)
        if compare:
            for panel, entry in zip(self.panels, entries):
                panel.show_entry(entry)
        else:
            self.move_by(0)
        self.finished.connect(self.stop)
        self.resize(min(window.width(), 1200), max(620, window.height() - 40))

    def sync_view(self, zoom, x, y):
        for panel in self.panels:
            panel.canvas.set_view(zoom, x, y)

    def move_by(self, offset):
        target = self.index + offset
        if 0 <= target < len(self.entries):
            self.index = target
            self.sync_view(1.0, 0.5, 0.5)
            self.panels[0].show_entry(self.entries[target])
            self.position.setText(f'{target + 1}/{len(self.entries)}')
            self.previous.setEnabled(target > 0)
            self.next.setEnabled(target + 1 < len(self.entries))

    def apply_shortcut(self, shortcut):
        item = next((category for category in self.window.project.categories if category.shortcut == shortcut), None)
        if item:
            self.window.toggle_category(item.id, [self.entries[self.index].relative], self)
            self.panels[0].refresh_tags()

    def stop(self, _):
        for panel in self.panels:
            panel.stop()
