from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QFileDialog


BUTTONS = {'OK': 'Đồng ý', 'Cancel': 'Hủy', 'Open': 'Mở', 'Choose': 'Chọn', 'Save': 'Lưu',
           'Close': 'Đóng', 'Yes': 'Có', 'No': 'Không', 'Apply': 'Áp dụng', '&Yes': '&Có', '&No': '&Không'}

QT_TEXT = {
    'QDialogButtonBox': BUTTONS,
    'QPlatformTheme': BUTTONS,
    'QFileDialog': {
        'Look in:': 'Thư mục:', '&Look in:': 'Thư &mục:', 'File &name:': '&Tên tệp:',
        'Files of &type:': '&Loại tệp:', 'Files of type:': 'Loại tệp:',
        '&Open': '&Mở', '&Choose': '&Chọn', '&Save': '&Lưu', '&Cancel': '&Hủy',
        'Back': 'Quay lại', 'Forward': 'Tiếp theo', 'Parent Directory': 'Thư mục cấp trên',
        'Create New Folder': 'Tạo thư mục mới', 'List View': 'Dạng danh sách', 'Detail View': 'Dạng chi tiết',
        'Computer': 'Máy tính', 'Drive': 'Ổ đĩa', 'File': 'Tệp', 'Folder': 'Thư mục',
        'New Folder': 'Thư mục mới', 'All Files (*)': 'Tất cả tệp (*)', 'Show ': 'Hiện ',
        '&Rename': 'Đổ&i tên', '&Delete': '&Xóa', 'Show &hidden files': 'Hiện tệp ẩ&n',
        'Directory:': 'Thư mục:', 'Choose': 'Chọn', 'Recent Places': 'Vị trí gần đây',
        '%1\nFile not found.\nCheck path and filename.': '%1\nKhông tìm thấy tệp.\nKiểm tra đường dẫn và tên tệp.',
    },
    'QFileSystemModel': {'Name': 'Tên', 'Size': 'Kích thước', 'Type': 'Loại', 'Date Modified': 'Ngày sửa',
                         'Kind': 'Loại', 'File': 'Tệp', 'File Folder': 'Thư mục'},
    'QColorDialog': {'Select Color': 'Chọn màu', 'Hu&e:': 'Sắ&c độ:', '&Sat:': 'Độ &bão hòa:',
                     '&Val:': 'Độ &sáng:', '&Red:': 'Đỏ:', '&Green:': 'Lục:', 'Bl&ue:': 'Lam:',
                     'A&lpha channel:': 'Độ trong:', '&HTML:': 'Mã &HTML:', '&Basic colors': 'Màu &cơ bản',
                     '&Custom colors': 'Màu &tùy chỉnh', '&Add to Custom Colors': 'T&hêm màu tùy chỉnh',
                     '&Pick Screen Color': 'Lấ&y màu trên màn hình'},
    'QLineEdit': {'&Undo': '&Hoàn tác', '&Redo': '&Làm lại', 'Cu&t': 'Cắ&t', '&Copy': '&Sao chép',
                  '&Paste': '&Dán', 'Delete': 'Xóa', 'Select All': 'Chọn tất cả'},
    'QWidgetTextControl': {'&Undo': '&Hoàn tác', '&Redo': '&Làm lại', 'Cu&t': 'Cắ&t', '&Copy': '&Sao chép',
                           '&Paste': '&Dán', 'Delete': 'Xóa', 'Select All': 'Chọn tất cả'},
}


class VietnameseQt(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):
        return QT_TEXT.get(context, {}).get(source_text, source_text)


def choose_path(parent, title, start='', name_filter=''):
    dialog = QFileDialog(parent)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
    dialog.setOption(QFileDialog.Option.ReadOnly)
    dialog.setWindowTitle(title)
    if start:
        dialog.setDirectory(start)
    if name_filter:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter(name_filter)
    else:
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
    dialog.setLabelText(QFileDialog.DialogLabel.Accept, 'Mở' if name_filter else 'Chọn thư mục')
    dialog.setLabelText(QFileDialog.DialogLabel.Reject, 'Hủy')
    dialog.setLabelText(QFileDialog.DialogLabel.FileName, 'Tên tệp:' if name_filter else 'Thư mục:')
    return dialog.selectedFiles()[0] if dialog.exec() and dialog.selectedFiles() else ''
