from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from core.data_store import counts, load_project
from core.exporter import (
    check_copy_destination, execute_copy, export_package, lightroom_warnings, match_raw, plan_copy, selected_paths,
)
from ui.dialogs import ExportDialog, information, report
from ui.localization import choose_path


class Transfers:
    def __init__(self, window):
        self.window = window

    def run(self, label, work, finished, total=0):
        window = self.window
        window.set_busy(label, total)

        def complete(result, error):
            window.set_busy('')
            if error:
                information(window, label, f'Tác vụ gặp lỗi.\n{error}', warning=True)
            else:
                finished(result)

        window.jobs.start(work, complete, window.task_progress.setValue)

    def export(self):
        window = self.window
        if not window.available() or not window.flush_save():
            return
        project = window.snapshot()
        total, totals = counts(project, project.photos)
        if not total:
            return
        dialog = ExportDialog(project, total, totals, lightroom_warnings(project), window)
        if not dialog.exec():
            return
        folder = choose_path(window, 'Chọn nơi lưu gói gửi studio')
        if not folder:
            return
        compressed = dialog.zip.isChecked()
        self.run('Đang xuất gói gửi studio…', lambda _: export_package(Path(folder), project, compressed),
                 self.export_finished)

    def export_finished(self, result):
        folder, archive = result
        message = f'Danh sách đã được lưu tại\n{folder}'
        if archive:
            message += f'\n\nFile gửi studio\n{archive}'
        box = QMessageBox(QMessageBox.Icon.Information, 'Đã xuất danh sách', message, parent=self.window)
        box.setTextFormat(Qt.TextFormat.PlainText)
        open_folder = box.addButton('Mở thư mục', QMessageBox.ButtonRole.ActionRole)
        box.addButton('Đóng', QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() == open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def preview_copy(self):
        window = self.window
        if not window.available():
            return
        project = window.snapshot()
        self.choose_copy_destination(window.root, project, {path: path for path in selected_paths(project)}, [])

    def studio(self):
        window = self.window
        if window.busy:
            return
        filename = choose_path(window, 'Mở photo_tags.json khách gửi', name_filter='Dữ liệu lựa chọn (*.json)')
        if not filename:
            return
        source = choose_path(window, 'Chọn thư mục ảnh RAW gốc')
        if not source:
            return
        root = Path(source).resolve()

        def work(_):
            project = load_project(Path(filename))
            matches, issues = match_raw(root, project)
            return project, matches, issues

        self.run('Đang đối chiếu ảnh RAW…', work, lambda result: self.raw_matches(root, *result))

    def raw_matches(self, root, project, matches, issues):
        if issues or not matches:
            report(self.window, 'Kết quả đối chiếu RAW', f'Khớp {len(matches)} ảnh. Cần kiểm tra {len(issues)} ảnh.', issues)
        if matches:
            self.choose_copy_destination(root, project, matches, issues)

    def choose_copy_destination(self, root, project, matches, raw_issues):
        if not matches:
            return
        window = self.window
        folder = choose_path(window, 'Chọn thư mục đích để sao chép ảnh theo loại')
        if not folder:
            return
        destination = Path(folder)
        try:
            check_copy_destination(root, destination)
        except (OSError, ValueError) as error:
            information(window, 'Kiểm tra thư mục đích', str(error), warning=True)
            return

        def prepare(_):
            items = plan_copy(root, destination, project, matches)
            return items, [item.destination for item in items if item.destination.exists()]

        self.run('Đang kiểm tra tên tệp…', prepare,
                 lambda result: self.copy(root, destination, *result, raw_issues))

    def copy(self, root, destination, items, collisions, raw_issues):
        confirmed = set()
        if collisions:
            box = QMessageBox(QMessageBox.Icon.Question, 'Có tệp trùng tên',
                              f'{len(collisions)} tệp đã có ở thư mục đích. Bạn muốn xử lý thế nào?', parent=self.window)
            replace = box.addButton('Ghi đè tệp trùng', QMessageBox.ButtonRole.DestructiveRole)
            keep = box.addButton('Giữ tệp hiện có', QMessageBox.ButtonRole.AcceptRole)
            box.addButton('Hủy', QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(keep)
            box.exec()
            if box.clickedButton() not in (replace, keep):
                return
            if box.clickedButton() == replace:
                confirmed.update(collisions)

        def finished(result):
            copied, skipped, issues = result
            report(self.window, 'Đã xử lý sao chép',
                   f'Đã sao chép {copied} tệp. Bỏ qua {skipped} tệp trùng. Cần kiểm tra {len(issues) + len(raw_issues)} mục.\n{destination}',
                   raw_issues + issues)

        self.run('Đang sao chép ảnh…', lambda progress: execute_copy(root, destination, items, confirmed, progress),
                 finished, len(items))
