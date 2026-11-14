from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout

from core.backup import create_backup, read_backup, restore_images, restore_selection
from core.data_store import reconcile_paths
from ui.dialogs import confirm, dialog_buttons, information, wrapping
from ui.localization import choose_path


class Backups:
    def __init__(self, window, local: Path):
        self.window = window
        self.recovery_directory = local / 'backups'

    def backup(self):
        window = self.window
        if not window.available() or not window.flush_save():
            return
        dialog = QDialog(window)
        dialog.setWindowTitle('Sao lưu (backup)')
        layout = QVBoxLayout(dialog)
        layout.addWidget(wrapping(
            'Bản ZIP lưu đầy đủ tên khách hàng, loại ảnh, giới hạn gói, lựa chọn, số sao, '
            'yêu thích và ghi chú, kể cả bản ghi của ảnh hiện không có trong thư mục.'))
        images = QCheckBox(f'Kèm toàn bộ {len(window.entries):,} ảnh trong tất cả thư mục')
        layout.addWidget(images)
        layout.addWidget(wrapping('Bỏ chọn để chỉ sao lưu dữ liệu lựa chọn. '
                                  'Bản kèm ảnh có thể lớn và mất nhiều thời gian. API key không nằm trong backup.'))
        layout.addWidget(dialog_buttons(dialog, 'Chọn nơi sao lưu'))
        dialog.resize(520, 210)
        if not dialog.exec():
            return
        folder = choose_path(window, 'Chọn nơi lưu bản backup')
        if not folder:
            return
        project = window.project.snapshot(window.project.photos.keys())
        entries = window.entries.copy() if images.isChecked() else []
        root = window.root if images.isChecked() else None
        window.transfers.run(
            'Đang sao lưu…', lambda progress: create_backup(Path(folder), project, root, entries, progress),
            lambda path: information(window, 'Đã sao lưu', f'Bản backup đã được lưu tại\n{path}'), len(entries))

    def restore(self):
        window = self.window
        if window.busy or window.scanning or not window.flush_save():
            return
        filename = choose_path(window, 'Mở bản backup hoặc photo_tags.json',
                               name_filter='Bản sao lưu (*.zip *.json)')
        if filename:
            path = Path(filename)
            window.transfers.run('Đang kiểm tra bản backup…', lambda _: read_backup(path),
                                 lambda info: self.preview_restore(path, info))

    def preview_restore(self, path, info):
        window = self.window
        dialog = QDialog(window)
        dialog.setWindowTitle('Khôi phục (restore)')
        layout = QVBoxLayout(dialog)
        project = info.project
        layout.addWidget(wrapping(
            f'Khách hàng: {project.customer_name or "Chưa đặt tên"}\n'
            f'{len(project.categories)} loại ảnh · {len(project.photos):,} bản ghi lựa chọn\n'
            f'{len(info.image_paths):,} ảnh có trong backup'))
        with_images = QCheckBox('Khôi phục cả bộ ảnh vào thư mục mới')
        with_images.setChecked(bool(info.image_paths))
        with_images.setEnabled(bool(info.image_paths))
        layout.addWidget(with_images)
        layout.addWidget(wrapping(
            'Khôi phục cả bộ ảnh: chọn thư mục cha, ứng dụng tạo thư mục mới và mở bộ ảnh đã phục hồi.\n'
            'Chỉ khôi phục dữ liệu: thay lựa chọn trong thư mục ảnh đang mở; '
            'ứng dụng giữ một bản JSON cũ trước khi thay thế. Giữ cấu trúc thư mục để khớp đúng ảnh.'))
        layout.addWidget(dialog_buttons(dialog, 'Tiếp tục khôi phục'))
        dialog.resize(550, 280)
        if not dialog.exec():
            return
        if with_images.isChecked():
            destination = choose_path(window, 'Chọn thư mục cha chứa bộ ảnh khôi phục')
            if destination:
                window.transfers.run(
                    'Đang khôi phục bộ ảnh…', lambda progress: restore_images(path, Path(destination), progress),
                    self.images_restored, len(info.image_paths))
            return
        if not window.available() or not window.lock or not window.lock.isLocked():
            information(window, 'Chọn thư mục để khôi phục',
                        'Mở thư mục ảnh cần phục hồi dữ liệu trước. Cần quyền ghi và không được mở ở phiên khác.', warning=True)
            return
        reconcile_paths(window.root, project, list(window.entry_map), True)
        matches = sum(key in window.entry_map for key in project.photos)
        missing = len(project.photos) - matches
        if not confirm(window, 'Thay thế dữ liệu lựa chọn',
                       f'Khớp {matches:,} bản ghi với bộ ảnh đang mở. {missing:,} bản ghi chưa có ảnh tương ứng '
                       '(vẫn được giữ trong dữ liệu).\n\n'
                       'Toàn bộ loại ảnh, gói cưới, lựa chọn, sao và ghi chú hiện tại sẽ được thay thế. '
                       f'Dữ liệu cũ được giữ tại:\n{self.recovery_directory}', 'Khôi phục dữ liệu'):
            return
        root = window.root

        def finished(recovery):
            window.project = project
            window.read_only = ''
            window.save_error = ''
            window.dirty = False
            window.refresh_categories()
            window.refresh_counts()
            window.refresh_galleries()
            text = 'Đã khôi phục dữ liệu lựa chọn.'
            if recovery:
                text += f'\n\nDữ liệu trước khi khôi phục:\n{recovery}'
            information(window, 'Đã khôi phục', text)

        window.transfers.run('Đang khôi phục dữ liệu…',
                             lambda _: restore_selection(root, project, self.recovery_directory), finished)

    def images_restored(self, root):
        self.window.open_root(root)
        information(self.window, 'Đã khôi phục bộ ảnh', f'Ảnh và dữ liệu đã được khôi phục tại\n{root}')
