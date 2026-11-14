from __future__ import annotations

import os
from dataclasses import replace
from threading import Event

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.ai_advisor import DEFAULT_MODEL, analyze_collection, apply_recommendations
from core.chatgpt_auth import AuthError, AuthorizationCodeRejected, PlanSession
from core.sorting import SORT_OPTIONS, photo_sort_key
from ui.dialogs import confirm, information, wrapping
from ui.viewer import ViewerDialog


class AdvisorDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.running = False
        self.auth_running = False
        self.auth_cancellable = False
        self.auth_cancel = Event()
        self.accounts = []
        self.cancel = Event()
        self.recommendations = ()
        self.setWindowTitle('Đánh giá và chọn ảnh')
        self.resize(1040, 880)
        layout = QVBoxLayout(self)
        layout.addWidget(wrapping(
            'Đánh giá bố cục, ánh sáng, biểu cảm và độ nét từ bản xem trước. '
            'Kết quả là gợi ý; bạn xem lại và chọn ảnh trước khi áp dụng.'))
        form = QFormLayout()
        self.scope = QComboBox()
        self.scope.addItem('Ảnh đang chọn', 'selected')
        self.scope.addItem('Thư mục hiện tại (kèm thư mục con)', 'folder')
        self.scope.addItem('Tất cả thư mục ảnh', 'all')
        self.scope.setCurrentIndex(0 if window.selected_paths() else 2)
        form.addRow('Phạm vi đánh giá', self.scope)
        self.auth_mode = QComboBox()
        self.auth_mode.addItem('Dùng gói ChatGPT (đăng nhập)', 'chatgpt')
        self.auth_mode.addItem('OpenAI API key (tính phí API)', 'api')
        form.addRow('Cách sử dụng', self.auth_mode)
        account_row = QHBoxLayout()
        self.account_picker = QComboBox()
        self.account_picker.setMinimumContentsLength(20)
        account_row.addWidget(self.account_picker, 1)
        self.login_button = QPushButton('Continue with ChatGPT')
        self.login_button.setToolTip('Đăng nhập hoặc cấp quyền dùng gói ChatGPT qua trình duyệt.')
        self.login_button.setStyleSheet('QPushButton { background: #111111; color: white; }')
        self.login_button.clicked.connect(self.sign_in)
        account_row.addWidget(self.login_button)
        self.logout_button = QPushButton('Đăng xuất')
        self.logout_button.clicked.connect(self.sign_out)
        account_row.addWidget(self.logout_button)
        self.account_label = wrapping('Tài khoản ChatGPT')
        form.addRow(self.account_label, account_row)
        self.plan_status = wrapping()
        plan_row = QHBoxLayout()
        plan_row.addWidget(self.plan_status, 1)
        self.usage_button = QPushButton('Quản lý hạn mức')
        self.usage_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://chatgpt.com/settings/usage')))
        plan_row.addWidget(self.usage_button)
        self.plan_detail_label = wrapping('Hạn mức')
        form.addRow(self.plan_detail_label, plan_row)
        self.api_key = QLineEdit(window.ai_api_key or os.environ.get('OPENAI_API_KEY', ''))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText('OpenAI API key — chỉ giữ trong phiên ứng dụng')
        self.api_key_label = wrapping('OpenAI API key')
        form.addRow(self.api_key_label, self.api_key)
        self.model = QLineEdit(window.settings.value('ai/model', DEFAULT_MODEL, type=str))
        models = QHBoxLayout()
        models.addWidget(self.model, 1)
        self.plan_model = QComboBox()
        models.addWidget(self.plan_model, 1)
        self.reload_models = QPushButton('Tải model')
        self.reload_models.clicked.connect(self.load_models)
        models.addWidget(self.reload_models)
        form.addRow('Model hỗ trợ ảnh', models)
        self.criteria = QPlainTextEdit()
        self.criteria.setPlaceholderText('Ví dụ: Ưu tiên nụ cười tự nhiên, đủ mặt hai người, đa dạng bối cảnh, phù hợp album cưới…')
        self.criteria.setFixedHeight(64)
        form.addRow('Tiêu chí chọn ảnh', self.criteria)
        layout.addLayout(form)
        self.scope_label = wrapping()
        layout.addWidget(self.scope_label)
        layout.addWidget(wrapping(
            'Ảnh gửi lên OpenAI được thu nhỏ tối đa 1280 px và bỏ EXIF/GPS. '
            'Không gửi tên tệp, đường dẫn, ghi chú hoặc dữ liệu gói cưới. '
            'Phiên ChatGPT được Windows mã hóa; khóa và phiên đăng nhập không nằm trong backup.'))
        self.consent = QCheckBox('Tôi đồng ý gửi bản xem trước và tiêu chí tới OpenAI; có thể phát sinh phí API.')
        layout.addWidget(self.consent)
        actions = QHBoxLayout()
        self.run_button = QPushButton('Đánh giá ảnh')
        self.run_button.clicked.connect(self.start)
        self.stop_button = QPushButton('Dừng sau nhóm hiện tại')
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        actions.addWidget(self.run_button)
        actions.addWidget(self.stop_button)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        actions.addWidget(self.progress, 1)
        layout.addLayout(actions)
        self.message = wrapping()
        self.message.setMaximumHeight(100)
        layout.addWidget(self.message)
        sort_row = QHBoxLayout()
        sort_row.addStretch()
        sort_row.addWidget(wrapping('Sắp xếp kết quả'))
        self.result_sort = QComboBox()
        self.result_sort.setAccessibleName('Sắp xếp kết quả đánh giá ảnh')
        for key, text in SORT_OPTIONS:
            self.result_sort.addItem(text, key)
        saved_sort = window.settings.value('ai/results_sort', 'score_desc', type=str)
        sort_index = self.result_sort.findData(saved_sort)
        self.result_sort.setCurrentIndex(sort_index if sort_index >= 0 else self.result_sort.findData('score_desc'))
        sort_row.addWidget(self.result_sort)
        layout.addLayout(sort_row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Chọn', 'Ảnh / thư mục', 'Điểm', 'Nhận xét', 'Gợi ý chỉnh sửa', 'Sao'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 50)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().sectionClicked.connect(self.header_sort)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        layout.addWidget(self.table, 1)
        self.table.itemDoubleClicked.connect(lambda *_: self.preview_photo())
        top = QHBoxLayout()
        self.top_count = QSpinBox()
        self.top_count.setRange(1, max(1, len(window.entries)))
        album = next((item for item in window.project.categories if item.id == 'album'), None)
        remaining = album.max_count - window.totals.get('album', 0) if album and album.max_count is not None else 20
        self.top_count.setValue(max(1, min(len(window.entries), remaining)))
        top.addWidget(wrapping('Số ảnh đề xuất'))
        top.addWidget(self.top_count)
        self.top_button = QPushButton('Chọn ảnh điểm cao nhất')
        self.top_button.clicked.connect(self.select_top)
        self.top_button.setEnabled(False)
        top.addWidget(self.top_button)
        self.clear_button = QPushButton('Bỏ chọn tất cả')
        self.clear_button.clicked.connect(self.clear_selection)
        self.clear_button.setEnabled(False)
        top.addWidget(self.clear_button)
        self.preview_button = QPushButton('Xem ảnh lớn')
        self.preview_button.clicked.connect(self.preview_photo)
        self.preview_button.setEnabled(False)
        top.addWidget(self.preview_button)
        top.addStretch()
        layout.addLayout(top)
        options = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem('Không gán loại', None)
        for item in window.project.categories:
            self.category.addItem(item.name, item.id)
        options.addWidget(self.category)
        self.stars = QCheckBox('Ghi đè số sao theo điểm')
        self.favorite = QCheckBox('Đánh dấu yêu thích')
        self.favorite.setChecked(True)
        self.notes = QCheckBox('Thêm gợi ý vào ghi chú')
        options.addWidget(self.stars)
        options.addWidget(self.favorite)
        options.addWidget(self.notes)
        layout.addLayout(options)
        footer = QHBoxLayout()
        self.selection_label = wrapping()
        footer.addWidget(self.selection_label, 1)
        self.apply_button = QPushButton('Áp dụng cho ảnh đã tích')
        self.apply_button.clicked.connect(self.apply)
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton('Đóng')
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.apply_button)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.table.itemChanged.connect(self.update_selection)
        self.result_sort.currentIndexChanged.connect(self.sort_results)
        self.scope.currentIndexChanged.connect(self.update_scope)
        self.consent.toggled.connect(self.update_scope)
        self.auth_mode.currentIndexChanged.connect(self.auth_mode_changed)
        self.account_picker.currentIndexChanged.connect(self.account_changed)
        self.plan_model.currentIndexChanged.connect(self.update_scope)
        self.refresh_accounts()
        self.auth_mode_changed()
        if self.selected_account() and self.selected_account().signed_in:
            QTimer.singleShot(0, self.load_models)

    def using_plan(self):
        return self.auth_mode.currentData() == 'chatgpt'

    def selected_account(self):
        client_id = self.account_picker.currentData()
        return next((item for item in self.accounts if item.client_id == client_id), None)

    def refresh_accounts(self):
        try:
            self.accounts, active = self.window.chatgpt_auth.accounts()
        except (AuthError, OSError) as error:
            self.accounts, active = [], ''
            self.message.setText(str(error))
        with QSignalBlocker(self.account_picker):
            self.account_picker.clear()
            for account in self.accounts:
                self.account_picker.addItem(account.label, account.client_id)
            self.account_picker.addItem('Thêm tài khoản ChatGPT…', '')
            self.account_picker.setCurrentIndex(max(0, self.account_picker.findData(active)))

    def auth_mode_changed(self, *_):
        plan = self.using_plan()
        for widget in (self.account_label, self.account_picker, self.login_button, self.logout_button,
                       self.plan_detail_label, self.plan_status, self.usage_button, self.plan_model, self.reload_models):
            widget.setVisible(plan)
        self.api_key_label.setVisible(not plan)
        self.api_key.setVisible(not plan)
        self.model.setVisible(not plan)
        self.consent.setChecked(False)
        self.consent.setText('Tôi đồng ý gửi bản xem trước và tiêu chí tới OpenAI; ' + (
            'sử dụng hạn mức/số dư ChatGPT.' if plan else 'có thể phát sinh phí API.'))
        self.account_status()
        self.update_scope()
        account = self.selected_account()
        if plan and account and account.signed_in and account.plan_enabled and not self.plan_model.count():
            QTimer.singleShot(0, self.load_models)

    def account_status(self):
        account = self.selected_account()
        if not account or not account.signed_in:
            text = 'Đăng nhập để dùng gói ChatGPT. Không tự chuyển sang API key.'
        elif not account.plan_enabled:
            text = 'Đã đăng nhập; chưa cấp quyền dùng gói. Bấm Continue with ChatGPT để cấp quyền.'
        else:
            text = 'Đang dùng gói ChatGPT · không dùng API credit. Chịu hạn mức/số dư ChatGPT.'
        self.plan_status.setText(text)
        self.logout_button.setEnabled(bool(account and account.signed_in) and not (self.running or self.auth_running))

    def account_changed(self, *_):
        if self.running or self.auth_running:
            return
        account = self.selected_account()
        if account:
            try:
                self.window.chatgpt_auth.set_active(account.client_id)
            except (AuthError, OSError) as error:
                self.message.setText(str(error))
        self.plan_model.clear()
        self.account_status()
        if account and account.signed_in and account.plan_enabled:
            self.load_models()
        self.update_scope()

    def auth_task(self, work, complete, label, *, cancellable=False, failed=None, progress=None):
        self.auth_running = True
        self.auth_cancellable = cancellable
        self.window.set_busy(label)
        self.message.setText(label)
        self.set_running_controls()

        def finished(result, error):
            self.auth_running = False
            self.window.set_busy('')
            self.refresh_accounts()
            if error:
                self.message.setText(str(error))
                if failed and failed(error):
                    return
            else:
                complete(result)
            self.set_running_controls()

        self.window.jobs.start(work, finished, progress)

    def sign_in(self, _checked=False, *, retry_client_id='', retry_count=0):
        if self.running or self.auth_running:
            return
        try:
            attempt = self.window.chatgpt_auth.prepare_login(retry_client_id or self.account_picker.currentData() or '')
        except (AuthError, OSError) as error:
            self.message.setText(str(error))
            return
        self.auth_cancel = Event()
        cancel = self.auth_cancel

        def work(progress):
            callback = attempt.wait(cancel)
            progress(1)
            return self.window.chatgpt_auth.finish_login(attempt, callback, cancel)

        def failed(error):
            if isinstance(error, AuthorizationCodeRejected) and retry_count < 1 and not cancel.is_set():
                self.sign_in(retry_client_id=error.client_id, retry_count=retry_count + 1)
                return True
            if not cancel.is_set():
                information(self, 'Chưa đăng nhập được ChatGPT', str(error), warning=True)
            return False

        def progress(_):
            self.message.setText('Đã nhận phản hồi từ trình duyệt. Đang đổi mã và xác thực phiên với OpenAI…')

        def complete(account):
            self.plan_model.clear()
            if account.plan_enabled:
                self.message.setText('Đã đăng nhập ChatGPT. Đang tải danh sách model…')
                if not account.welcomed:
                    information(self, 'Bạn đang dùng gói ChatGPT',
                                'Các lượt đánh giá ảnh đủ điều kiện sẽ dùng hạn mức/số dư ChatGPT của bạn. '
                                'Bạn có thể xem và điều chỉnh trong “Quản lý hạn mức”. Không tự dùng API key.')
                    try:
                        self.window.chatgpt_auth.mark_welcomed(account.client_id)
                    except (AuthError, OSError) as error:
                        self.message.setText(str(error))
                QTimer.singleShot(0, self.load_models)
            else:
                self.message.setText('Đã xác thực tài khoản nhưng chưa được cấp quyền dùng gói. '
                                     'Bấm Continue with ChatGPT để cấp quyền lại.')

        self.auth_task(work, complete, 'Đang chờ đăng nhập trong trình duyệt (tối đa 3 phút). Bấm “Hủy đăng nhập” để dừng.',
                       cancellable=True, failed=failed, progress=progress)
        if not QDesktopServices.openUrl(QUrl(attempt.url)):
            cancel.set()

    def load_models(self):
        if self.running or self.auth_running or not self.using_plan():
            return
        account = self.selected_account()
        self.plan_model.clear()
        if not account or not account.signed_in or not account.plan_enabled:
            self.account_status()
            self.update_scope()
            return
        client_id = account.client_id

        def complete(models):
            if self.account_picker.currentData() != client_id:
                return
            saved = self.window.settings.value('ai/chatgpt_model', '', type=str)
            for slug, name in models:
                self.plan_model.addItem(name, slug)
            self.plan_model.setCurrentIndex(max(0, self.plan_model.findData(saved)))
            self.message.setText('Đã tải model cho tài khoản ChatGPT. Chọn model có hỗ trợ ảnh rồi đánh giá.')

        self.auth_task(lambda _: self.window.chatgpt_auth.models(client_id), complete, 'Đang tải model từ tài khoản ChatGPT…')

    def sign_out(self):
        account = self.selected_account()
        if self.running or self.auth_running or not account:
            return

        def complete(revoked):
            self.plan_model.clear()
            self.message.setText('Đã đăng xuất ChatGPT.' if revoked else
                                 'Đã xóa phiên trên máy; chưa xác nhận được thu hồi từ OpenAI. '
                                 'Bạn có thể ngắt kết nối ứng dụng trong cài đặt ChatGPT.')

        self.auth_task(lambda _: self.window.chatgpt_auth.sign_out(account.client_id), complete, 'Đang đăng xuất ChatGPT…')

    def scope_paths(self):
        scope = self.scope.currentData()
        if scope == 'selected':
            return self.window.selected_paths()
        prefix = self.window.active_folder + '/' if self.window.active_folder else ''
        return [entry.relative for entry in self.window.entries
                if scope == 'all' or entry.relative.startswith(prefix)]

    def update_scope(self, *_):
        count = len(self.scope_paths())
        self.scope_label.setText(f'{count:,} ảnh · {(count + 11) // 12:,} lượt đánh giá (tối đa 12 ảnh/nhóm). '
                                 'Bộ lọc sao/yêu thích không giới hạn phạm vi thư mục.')
        account = self.selected_account()
        ready = not self.using_plan() or bool(account and account.signed_in and account.plan_enabled and self.plan_model.currentData())
        self.run_button.setEnabled(not (self.running or self.auth_running) and count > 0 and self.consent.isChecked() and ready)

    def start(self):
        if self.running or self.auth_running or not self.consent.isChecked():
            return
        paths = self.scope_paths()
        if not paths:
            return
        plan_session = None
        if self.using_plan():
            account = self.selected_account()
            model = self.plan_model.currentData()
            if not account or not account.signed_in or not account.plan_enabled or not model:
                self.message.setText('Đăng nhập, cấp quyền dùng gói ChatGPT và tải model trước khi đánh giá.')
                return
            key = ''
            plan_session = PlanSession(self.window.chatgpt_auth, account.client_id)
        else:
            key, model = self.api_key.text().strip(), self.model.text().strip()
        criteria = self.criteria.toPlainText().strip()
        if (not plan_session and not key) or not model or len(criteria) > 2000:
            self.message.setText('Nhập API key, model và tiêu chí tối đa 2.000 ký tự.')
            return
        if plan_session:
            self.window.settings.setValue('ai/chatgpt_model', model)
        else:
            self.window.ai_api_key = key
            self.window.settings.setValue('ai/model', model)
        self.cancel = Event()
        self.running = True
        self.recommendations = ()
        self.table.setRowCount(0)
        self.update_selection()
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.message.setText('Đang đánh giá… Có thể dừng sau khi nhóm hiện tại hoàn tất.')
        self.set_running_controls()
        self.window.set_busy('Đang đánh giá ảnh…', len(paths))
        root = self.window.root
        options = {'plan_session': plan_session} if plan_session else {}
        self.window.jobs.start(
            lambda progress: analyze_collection(root, paths, key, model, criteria, self.cancel, progress, **options),
            self.finished, self.update_progress)

    def update_progress(self, value):
        self.progress.setValue(value)
        self.window.task_progress.setValue(value)

    def set_running_controls(self):
        busy = self.running or self.auth_running
        for widget in (self.scope, self.api_key, self.model, self.criteria, self.consent, self.auth_mode,
                       self.account_picker, self.login_button, self.reload_models, self.plan_model, self.close_button,
                       self.result_sort):
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(self.running or self.auth_running and self.auth_cancellable)
        self.stop_button.setText('Hủy đăng nhập' if self.auth_running else 'Dừng sau nhóm hiện tại')
        self.top_button.setEnabled(not self.running and bool(self.recommendations))
        self.clear_button.setEnabled(not self.running and bool(self.recommendations))
        self.preview_button.setEnabled(not self.running and bool(self.recommendations))
        self.account_status()
        self.update_selection()
        self.update_scope()

    def stop(self):
        if self.auth_running:
            if not self.auth_cancellable:
                self.message.setText('Đợi kết nối ChatGPT hiện tại hoàn tất (mỗi yêu cầu mạng chờ tối đa 60 giây).')
                return
            self.auth_cancel.set()
            self.stop_button.setEnabled(False)
            self.message.setText('Đang hủy đăng nhập/kết nối. Đợi yêu cầu mạng hiện tại kết thúc nếu đã gửi.')
            return
        self.cancel.set()
        self.stop_button.setEnabled(False)
        self.message.setText('Đang dừng… Đợi nhóm hiện tại trả kết quả (thời gian chờ mạng tối đa 60 giây).')

    def finished(self, result, error):
        self.running = False
        self.window.set_busy('')
        if error:
            self.message.setText(f'Không đánh giá được ảnh. {error}')
        else:
            self.recommendations = result.review.photos
            scores_saved = False
            if self.window.editable():
                changed = [item.path for item in self.recommendations
                           if item.path in self.window.entry_map
                           and self.window.project.update(item.path, ai_score=item.score)]
                self.window.photos_changed(changed)
                scores_saved = self.window.flush_save()
            status = f'Đã xử lý {result.processed:,}/{result.total:,} ảnh · {len(result.review.photos):,} kết quả.'
            if result.skipped:
                status += f' Bỏ qua {len(result.skipped)} ảnh không đọc được: ' + ', '.join(result.skipped[:3])
            if result.stopped:
                status += ' Đã dừng theo yêu cầu.'
            if result.error:
                status += f' Đã dừng do lỗi: {result.error}'
            if self.recommendations:
                status += ' Đã lưu điểm ảnh.' if scores_saved else ' Điểm chưa lưu xuống đĩa; dùng “Thử lưu lại”.'
            self.message.setText(status + '\n' + result.review.summary)
            self.sort_results(checked_paths=set())
            self.select_top()
        self.set_running_controls()
        self.update_selection()

    def header_sort(self, column):
        if self.running or self.auth_running:
            return
        prefix = {1: 'name', 2: 'score', 5: 'stars'}.get(column)
        if prefix is None:
            return
        current = self.result_sort.currentData()
        default = 'asc' if prefix == 'name' else 'desc'
        direction = ('asc' if current.endswith('_desc') else 'desc') if current.startswith(prefix + '_') else default
        self.result_sort.setCurrentIndex(self.result_sort.findData(prefix + '_' + direction))

    def sort_results(self, _index=None, *, checked_paths=None):
        if self.running or self.auth_running:
            return
        if checked_paths is None:
            checked_paths = {item.path for item in self.selected_recommendations()}
        cell = self.table.item(self.table.currentRow(), 1) if self.table.currentRow() >= 0 else None
        current_path = cell.text() if cell else None
        mode = self.result_sort.currentData()
        self.window.settings.setValue('ai/results_sort', mode)
        self.recommendations = tuple(sorted(self.recommendations, key=lambda item: photo_sort_key(
            item.path, replace(self.window.project.photo(item.path), ai_score=item.score), mode),
            reverse=mode == 'name_desc'))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.recommendations))
        for row, item in enumerate(self.recommendations):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if item.path in checked_paths else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            stars = self.window.project.photo(item.path).stars
            values = (item.path, str(item.score), item.reason, item.editing_note, str(stars) if stars else '—')
            for column, value in enumerate(values, 1):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, column, cell)
        self.table.blockSignals(False)
        if self.recommendations:
            current_row = next((row for row, item in enumerate(self.recommendations) if item.path == current_path), 0)
            self.table.setCurrentCell(current_row, 1)
        column = 2 if mode.startswith('score') else 5 if mode.startswith('stars') else 1
        order = Qt.SortOrder.DescendingOrder if mode.endswith('_desc') else Qt.SortOrder.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(column, order)
        self.update_selection()

    def selected_recommendations(self):
        return [item for row, item in enumerate(self.recommendations)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def select_top(self):
        highest = sorted(self.recommendations, key=lambda item: (-item.score, item.path.casefold(), item.path))
        selected = {item.path for item in highest[:self.top_count.value()]}
        self.table.blockSignals(True)
        for row, item in enumerate(self.recommendations):
            self.table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if item.path in selected else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_selection()

    def preview_photo(self):
        row = self.table.currentRow()
        if self.running or not 0 <= row < len(self.recommendations):
            return
        entries = [self.window.entry_map[item.path] for item in self.recommendations]
        viewer = ViewerDialog(self.window, entries, row)
        viewer.setParent(self, viewer.windowFlags())
        viewer.exec()
        self.sort_results()

    def clear_selection(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_selection()

    def update_selection(self, *_):
        selected = self.selected_recommendations()
        self.selection_label.setText(f'{len(selected):,} ảnh đã tích')
        self.apply_button.setEnabled(not (self.running or self.auth_running) and bool(selected) and self.window.editable())

    def apply(self):
        if self.running or not self.window.editable():
            return
        selected = self.selected_recommendations()
        if not selected:
            return
        category_id = self.category.currentData()
        if not (category_id or self.stars.isChecked() or self.favorite.isChecked() or self.notes.isChecked()):
            self.message.setText('Chọn gán loại, số sao, yêu thích hoặc thêm ghi chú để áp dụng.')
            return
        if category_id:
            category = next(item for item in self.window.project.categories if item.id == category_id)
            added = sum(category_id not in self.window.project.photo(item.path).category_ids for item in selected)
            projected = self.window.totals[category_id] + added
            if (added and category.max_count is not None and projected > category.max_count
                    and not confirm(self, 'Chọn thêm ảnh ngoài gói',
                                    f'“{category.name}” sẽ có {projected}/{category.max_count} ảnh. '
                                    'Studio có thể tính thêm phí cho phần vượt gói. Bạn muốn chọn thêm?', 'Chọn thêm')):
                return
        changed = set(apply_recommendations(
            self.window.project, selected, stars=self.stars.isChecked(),
            favorite=self.favorite.isChecked(), notes=self.notes.isChecked()))
        if category_id:
            for item in selected:
                previous = self.window.project.photo(item.path).category_ids
                if category_id not in previous and self.window.project.update(item.path, category_ids=previous + (category_id,)):
                    changed.add(item.path)
        self.window.photos_changed(list(changed))
        saved = self.window.flush_save()
        self.sort_results()
        self.message.setText(f'Đã áp dụng cho {len(selected)} ảnh.' + (
            ' Đã lưu lựa chọn.' if saved else ' Chưa lưu được xuống đĩa; dùng “Thử lưu lại” ở cửa sổ chính.'))

    def reject(self):
        if self.running or self.auth_running:
            self.stop()
            return
        super().reject()

    def closeEvent(self, event):
        if self.running or self.auth_running:
            self.stop()
            event.ignore()
        else:
            super().closeEvent(event)
