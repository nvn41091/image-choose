from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from core.data_store import Category, validate_categories

HINTS = ('Làm thon mặt', 'Làm sáng da', 'Xóa người/vật thừa', 'Chỉnh màu', 'Mở mắt (ghép)')


def wrapping(text='', parent=None):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def dialog_buttons(dialog, text):
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text)
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Hủy')
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def confirm(parent, title, message, label):
    box = QMessageBox(QMessageBox.Icon.Question, title, message, parent=parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    proceed = box.addButton(label, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton('Hủy', QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() == proceed


def information(parent, title, message, warning=False):
    icon = QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information
    box = QMessageBox(icon, title, message, parent=parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.addButton('Đóng', QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def report(parent, title, summary, lines):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.addWidget(wrapping(summary))
    if lines:
        details = QPlainTextEdit('\n'.join(lines))
        details.setReadOnly(True)
        details.setAccessibleName('Chi tiết kết quả')
        layout.addWidget(details)
    close = QPushButton('Đóng')
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
    dialog.resize(575, 340 if lines else 120)
    dialog.exec()


class CategoryEditor(QDialog):
    def __init__(self, current, categories, parent):
        super().__init__(parent)
        self.current = current
        self.categories = categories
        self.result_item = None
        self.color = current.color if current else '#2563eb'
        self.setWindowTitle('Sửa loại ảnh' if current else 'Thêm loại ảnh')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(current.name if current else '')
        self.name.setAccessibleName('Tên loại ảnh')
        self.name.setMaxLength(90)
        form.addRow('&Tên loại', self.name)
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.pick_color)
        self.set_color(self.color)
        form.addRow('&Màu', self.color_button)
        self.shortcut = QComboBox()
        self.shortcut.setAccessibleName('Phím tắt loại ảnh')
        used = {category.shortcut for category in categories if category != current}
        for key in range(1, 10):
            if key not in used:
                self.shortcut.addItem(str(key), key)
        if current:
            self.shortcut.setCurrentIndex(self.shortcut.findData(current.shortcut))
        form.addRow('&Phím tắt', self.shortcut)
        self.maximum = QLineEdit('' if not current or current.max_count is None else str(current.max_count))
        self.maximum.setValidator(QIntValidator(0, 999_999_999, self.maximum))
        self.maximum.setAccessibleName('Số ảnh tối đa')
        self.maximum.setPlaceholderText('Để trống nếu không giới hạn')
        form.addRow('&Số ảnh tối đa', self.maximum)
        layout.addLayout(form)
        self.error = wrapping()
        self.error.setObjectName('inlineError')
        layout.addWidget(self.error)
        layout.addWidget(dialog_buttons(self, 'Lưu loại'))
        self.name.setFocus()
        self.resize(410, 220)

    def set_color(self, color):
        self.color = color
        self.color_button.setText(f'Chọn màu ({color.upper()})')

    def pick_color(self):
        dialog = QColorDialog(QColor(self.color), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        dialog.setWindowTitle('Chọn màu loại ảnh')
        if dialog.exec():
            self.set_color(dialog.selectedColor().name())

    def accept(self):
        maximum = self.maximum.text()
        if maximum and not self.maximum.hasAcceptableInput():
            self.error.setText('Số ảnh tối đa phải là số nguyên từ 0 đến 999.999.999.')
            self.maximum.setFocus()
            return
        item = Category(self.current.id if self.current else uuid4().hex, self.name.text().strip(),
                        self.color, self.shortcut.currentData(), int(maximum) if maximum else None)
        try:
            validate_categories([value for value in self.categories if value != self.current] + [item])
        except ValueError as error:
            self.error.setText(str(error))
            self.name.setFocus()
            return
        self.result_item = item
        super().accept()


class CategoriesDialog(QDialog):
    def __init__(self, project, parent):
        super().__init__(parent)
        self.setWindowTitle('Loại ảnh và gói cưới')
        self.categories = project.categories.copy()
        self.project = project
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.customer = QLineEdit(project.customer_name)
        self.customer.setAccessibleName('Tên khách hàng')
        self.customer.setMaxLength(180)
        form.addRow('&Tên khách hàng', self.customer)
        layout.addLayout(form)
        self.list = QListWidget()
        self.list.setAccessibleName('Các loại ảnh trong gói')
        self.list.itemDoubleClicked.connect(lambda _: self.edit())
        self.list.currentRowChanged.connect(self.update_buttons)
        layout.addWidget(self.list)
        actions = QHBoxLayout()
        self.add_button = QPushButton('Thêm loại')
        self.edit_button = QPushButton('Sửa loại')
        self.delete_button = QPushButton('Xóa loại')
        for button, action in ((self.add_button, lambda: self.edit(True)),
                               (self.edit_button, self.edit), (self.delete_button, self.delete)):
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(wrapping('Mỗi loại dùng một phím từ 1 đến 9. Giới hạn để trống nghĩa là không giới hạn.'))
        layout.addWidget(dialog_buttons(self, 'Lưu gói cưới'))
        self.refresh()
        self.resize(540, 380)

    def refresh(self, row=0):
        self.list.clear()
        for item in self.categories:
            maximum = 'Không giới hạn' if item.max_count is None else f'Tối đa {item.max_count} ảnh'
            self.list.addItem(f'{item.shortcut}   {item.name}    ·    {maximum}')
        self.list.setCurrentRow(min(row, len(self.categories) - 1))
        self.update_buttons()

    def update_buttons(self, *_):
        self.add_button.setEnabled(len(self.categories) < 9)
        self.edit_button.setEnabled(self.list.currentRow() >= 0)
        self.delete_button.setEnabled(self.list.currentRow() >= 0)

    def edit(self, adding=False):
        row = self.list.currentRow()
        current = self.categories[row] if row >= 0 and not adding else None
        dialog = CategoryEditor(current, self.categories, self)
        if dialog.exec():
            if current:
                self.categories[row] = dialog.result_item
            else:
                self.categories.append(dialog.result_item)
                row = len(self.categories) - 1
            self.refresh(row)

    def delete(self):
        row = self.list.currentRow()
        item = self.categories[row]
        affected = sum(item.id in photo.category_ids for photo in self.project.photos.values())
        if confirm(self, 'Xóa loại ảnh', f'Xóa “{item.name}” và bỏ loại này khỏi {affected} ảnh?', 'Xóa loại'):
            self.categories.pop(row)
            self.refresh(row)


class ExportDialog(QDialog):
    def __init__(self, project, total, counts, warnings, parent):
        super().__init__(parent)
        self.setWindowTitle('Tóm tắt trước khi gửi studio')
        layout = QVBoxLayout(self)
        layout.addWidget(wrapping(f'{project.customer_name or "Chưa nhập tên khách hàng"}  ·  {total} ảnh đã chọn'))
        lines = []
        for item in project.categories:
            count = counts[item.id]
            if item.max_count is None:
                status = f'{count} ảnh'
            else:
                difference = count - item.max_count
                status = f'{count}/{item.max_count} ảnh'
                if difference:
                    status += f' · {"Vượt" if difference > 0 else "Thiếu"} {abs(difference)} ảnh'
            lines.append(f'{item.name} — {status}')
        layout.addWidget(wrapping('\n'.join(lines)))
        if warnings:
            listed = ', '.join(warnings[:5]) + (', …' if len(warnings) > 5 else '')
            layout.addWidget(wrapping(f'Tên bỏ đuôi trùng nhau hoặc chứa dấu phẩy: {listed}. '
                                      'Studio có thể tra đường dẫn đầy đủ trong photo_tags.json.'))
        layout.addWidget(wrapping('Gói gồm Excel, danh sách Lightroom và dữ liệu lựa chọn. Bộ lọc đang dùng trên màn hình không giới hạn gói xuất.'))
        self.zip = QCheckBox('Tạo thêm file ZIP để gửi qua Zalo hoặc email')
        self.zip.setChecked(True)
        layout.addWidget(self.zip)
        layout.addWidget(dialog_buttons(self, 'Chọn nơi lưu…'))
        self.resize(540, 290)


class GuideDialog(QDialog):
    STEPS = (
        ('Mở thư mục ảnh', 'Chọn thư mục ảnh xem trước studio đã gửi. Bấm vào một thư mục trong lưới để xem ảnh bên trong.'),
        ('Tìm những tấm bạn thích', 'Dùng tim hoặc số sao để lọc vòng đầu. Chọn từ hai đến bốn tấm rồi bấm “So sánh” để xem nét mặt ở cùng mức phóng to.'),
        ('Chọn ảnh theo gói', 'Gán loại như Album hoặc Phóng lớn. Xem số ảnh đã chọn ở thanh gói và thêm yêu cầu hậu kỳ cho từng tấm.'),
        ('Gửi danh sách cho studio', 'Bấm “Hoàn tất và xuất danh sách”. Xem lại số ảnh mỗi loại rồi gửi file ZIP cho studio.'),
    )

    def __init__(self, assets, parent):
        super().__init__(parent)
        self.assets, self.page = assets, 0
        self.setWindowTitle('Hướng dẫn chọn ảnh cưới')
        layout = QVBoxLayout(self)
        self.title = wrapping()
        self.title.setObjectName('sectionTitle')
        layout.addWidget(self.title)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image)
        self.copy = wrapping()
        self.copy.setMinimumHeight(65)
        layout.addWidget(self.copy)
        buttons = QHBoxLayout()
        back = QPushButton('Bỏ qua')
        back.clicked.connect(self.reject)
        buttons.addWidget(back)
        buttons.addStretch()
        self.previous = QPushButton('Quay lại')
        self.previous.clicked.connect(lambda: self.show_page(self.page - 1))
        buttons.addWidget(self.previous)
        self.next = QPushButton()
        self.next.setDefault(True)
        self.next.clicked.connect(self.advance)
        buttons.addWidget(self.next)
        layout.addLayout(buttons)
        self.show_page(0)
        self.resize(560, 395)

    def show_page(self, index):
        self.page = index
        title, text = self.STEPS[index]
        self.title.setText(f'Bước {index + 1}/{len(self.STEPS)}  ·  {title}')
        self.copy.setText(text)
        self.image.setPixmap(QPixmap(str(self.assets / f'guide-{index + 1}.png')))
        self.previous.setEnabled(index > 0)
        self.next.setText('Bắt đầu chọn ảnh' if index == len(self.STEPS) - 1 else 'Tiếp theo')

    def advance(self):
        if self.page == len(self.STEPS) - 1:
            self.accept()
        else:
            self.show_page(self.page + 1)
