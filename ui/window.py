from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from threading import Event

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QLockFile, QSettings, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from core.data_store import (
    TAGS_FILE, Project, category_change, counts, load_project, new_project, reconcile_paths, save_project,
)
from core.scanner import FolderEntry, ImageEntry, scan
from core.sorting import SORT_OPTIONS, photo_sort_key
from core.thumbnail_cache import ThumbnailCache
from core.chatgpt_auth import ChatGPTAuth
from ui.ai_advisor import AdvisorDialog
from ui.backups import Backups
from ui.dialogs import CategoriesDialog, GuideDialog, HINTS, confirm, information, wrapping
from ui.gallery import DEFAULT_COLUMNS, ENTRY, Gallery, Thumbnails
from ui.jobs import Jobs
from ui.localization import choose_path
from ui.theme import apply_theme
from ui.transfers import Transfers
from ui.viewer import ViewerDialog

log = logging.getLogger(__name__)


def button(text, action, object_name=''):
    widget = QPushButton(text)
    widget.setObjectName(object_name)
    widget.clicked.connect(action)
    return widget


def section(text):
    title = wrapping(text)
    title.setObjectName('sectionTitle')
    return title


class MainWindow(QMainWindow):
    def __init__(self, local: Path, assets: Path, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.gallery_sort = settings.value('gallery_sort', 'name_asc', type=str)
        if self.gallery_sort not in dict(SORT_OPTIONS):
            self.gallery_sort = 'name_asc'
        self.assets = assets
        self.jobs = Jobs(self, threads=4)
        self.scan_jobs = Jobs(self, threads=1)
        cache = ThumbnailCache(local / 'cache')
        self.thumbnails = Thumbnails(cache, self)
        self.jobs.start(lambda _: cache.trim(), lambda *_: None)
        self.transfers = Transfers(self)
        self.backups = Backups(self, local)
        self.ai_api_key = ''
        self.chatgpt_auth = ChatGPTAuth(local)
        self.root = None
        self.lock = None
        self.read_only = ''
        self.project = Project()
        self.entries = []
        self.entry_map = {}
        self.active_folder = ''
        self.folders_by_parent = defaultdict(list)
        self.photos_by_parent = defaultdict(list)
        self.cancel_scan = Event()
        self.scanning = False
        self.scan_error = ''
        self.busy = ''
        self.dirty = False
        self.save_error = ''
        self.note_path = None
        self.total = 0
        self.totals = {}
        self.save_timer = QTimer(self, singleShot=True, interval=500)
        self.save_timer.timeout.connect(self.flush_save)
        self.size_timer = QTimer(self, singleShot=True, interval=120)
        self.size_timer.timeout.connect(self.apply_thumbnail_size)

        self.setWindowTitle('Chọn ảnh cưới')
        self.resize(1240, 790)
        self.setMinimumSize(940, 640)
        self.build_ui()
        self.build_shortcuts()
        self.refresh_categories()
        self.refresh_counts()
        self.refresh_controls()
        self.refresh_galleries()

    def build_ui(self):
        task_menu = self.menuBar().addMenu('Tác vụ')
        self.open_action = task_menu.addAction('Chọn thư mục…', self.choose_root)
        self.category_action = task_menu.addAction('Loại ảnh và gói cưới…', self.edit_categories)
        self.compare_action = task_menu.addAction('So sánh ảnh', self.compare)
        self.export_action = task_menu.addAction('Hoàn tất và xuất danh sách…', self.transfers.export)
        self.copy_action = task_menu.addAction('Sao chép ảnh theo loại…', self.transfers.preview_copy)
        task_menu.addSeparator()
        self.ai_action = task_menu.addAction('Đánh giá và chọn ảnh…', self.open_ai_advisor)
        backup_menu = self.menuBar().addMenu('Sao lưu và khôi phục')
        self.backup_action = backup_menu.addAction('Sao lưu dữ liệu và ảnh…', self.backups.backup)
        self.restore_action = backup_menu.addAction('Khôi phục từ backup…', self.backups.restore)
        view_menu = self.menuBar().addMenu('Hiển thị')
        self.dark = view_menu.addAction('Giao diện tối')
        self.dark.setCheckable(True)
        self.dark.setChecked(self.settings.value('dark', False, type=bool))
        self.dark.toggled.connect(self.set_dark)
        studio_menu = self.menuBar().addMenu('Studio')
        self.raw_action = studio_menu.addAction('Đối chiếu và sao chép RAW…', self.transfers.studio)
        help_menu = self.menuBar().addMenu('Trợ giúp')
        help_menu.addAction('Hướng dẫn chọn ảnh', self.show_guide)
        help_menu.addAction('Danh sách phím tắt', self.show_shortcuts)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(7)

        self.toolbar = QFrame(objectName='toolbar')
        bar = QHBoxLayout(self.toolbar)
        bar.setContentsMargins(8, 5, 8, 5)
        self.folder_button = button('Chọn thư mục', self.choose_root)
        bar.addWidget(self.folder_button)
        columns_label = QLabel('Ảnh mỗi &hàng')
        self.columns = QComboBox()
        self.columns.setAccessibleName('Số ảnh mỗi hàng')
        for number in range(3, 11):
            self.columns.addItem(str(number), number)
        index = self.columns.findData(self.settings.value('gallery_columns', DEFAULT_COLUMNS, type=int))
        self.columns.setCurrentIndex(index if index >= 0 else self.columns.findData(DEFAULT_COLUMNS))
        self.columns.currentIndexChanged.connect(self.change_columns)
        columns_label.setBuddy(self.columns)
        bar.addStretch()
        bar.addWidget(columns_label)
        bar.addWidget(self.columns)
        self.compare_button = button('So sánh', self.compare)
        self.compare_button.setToolTip('Chọn từ hai đến bốn ảnh để so sánh (C).')
        bar.addWidget(self.compare_button)
        self.ai_button = button('Đánh giá ảnh', self.open_ai_advisor)
        self.ai_button.setToolTip('Đánh giá ảnh đang chọn, thư mục hiện tại hoặc tất cả thư mục.')
        bar.addWidget(self.ai_button)
        self.export_button = button('Hoàn tất và xuất danh sách', self.transfers.export, 'primary')
        bar.addWidget(self.export_button)
        layout.addWidget(self.toolbar)

        self.path = QLineEdit(readOnly=True)
        self.path.setPlaceholderText('Chưa mở thư mục ảnh')
        self.path.setAccessibleName('Đường dẫn thư mục ảnh hiện tại')
        layout.addWidget(self.path)
        self.quota = wrapping('Gói cưới')
        self.quota.setAccessibleName('Tiến độ chọn theo gói cưới')
        layout.addWidget(self.quota)

        alert = QHBoxLayout()
        self.notice = wrapping()
        self.notice.setObjectName('inlineError')
        alert.addWidget(self.notice, 1)
        self.retry = button('Thử lưu lại', self.flush_save)
        alert.addWidget(self.retry)
        layout.addLayout(alert)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName('Chế độ duyệt ảnh')
        self.tabs.currentChanged.connect(self.tab_changed)
        self.galleries = []
        self.stacks = []
        self.empty_states = []
        self.filter_rows = []
        self.clear_filters_buttons = []
        self.sort_controls = []
        self.sort_rows = []
        for index, title in enumerate(('Tất cả ảnh', 'Ảnh đã chọn')):
            self.build_tab(index, title)
        body.addWidget(self.tabs, 1)
        self.inspector = self.build_inspector()
        body.addWidget(self.inspector)
        layout.addLayout(body, 1)

        self.status = QLabel('0 ảnh  ·  0 đã chọn')
        self.statusBar().addWidget(self.status, 1)
        self.task_progress = QProgressBar()
        self.task_progress.setAccessibleName('Tiến độ tác vụ')
        self.task_progress.setFixedWidth(170)
        self.statusBar().addPermanentWidget(self.task_progress)
        self.task_progress.hide()
        self.thumbnail_progress = QLabel('')
        self.statusBar().addPermanentWidget(self.thumbnail_progress)
        self.thumbnails.progress.connect(self.show_thumbnail_progress)
        self.build_view_menu(view_menu)
        self.statusBar().messageChanged.connect(self.update_status_visibility)

    def build_tab(self, index, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 7, 0, 0)
        controls = QHBoxLayout()
        if index == 0:
            self.folder_up = button('↑  Thư mục cha', self.go_up)
            controls.addWidget(self.folder_up)
            self.folder_path = QLabel()
            self.folder_path.setTextFormat(Qt.TextFormat.PlainText)
            self.folder_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.folder_path.setAccessibleName('Vị trí đang xem trong bộ ảnh')
            controls.addWidget(self.folder_path, 1)
        filter_row = QWidget()
        filters = QHBoxLayout(filter_row)
        filters.setContentsMargins(0, 0, 0, 0)
        stars = QComboBox()
        stars.setAccessibleName(f'Lọc theo sao trong {title}')
        stars.addItem('Mọi số sao', None)
        stars.addItem('Chưa đánh sao', 0)
        for score in range(1, 6):
            stars.addItem(f'{score} sao', score)
        stars.currentIndexChanged.connect(self.refresh_galleries)
        filters.addWidget(stars)
        favorite = QCheckBox('Chỉ ảnh yêu thích')
        favorite.toggled.connect(self.refresh_galleries)
        filters.addWidget(favorite)
        if index == 1:
            self.category_filter = QComboBox()
            self.category_filter.setAccessibleName('Lọc ảnh đã chọn theo loại')
            self.category_filter.currentIndexChanged.connect(self.refresh_galleries)
            filters.addWidget(self.category_filter)
            self.search = QLineEdit()
            self.search.setPlaceholderText('Tìm tên file…')
            self.search.setAccessibleName('Tìm ảnh đã chọn theo tên file')
            self.search.textChanged.connect(self.refresh_galleries)
            filters.addWidget(self.search, 1)
        controls.addWidget(filter_row)
        clear_filters = button('Đang lọc · Bỏ lọc', lambda _checked=False, i=index: self.reset_filters(i))
        controls.addWidget(clear_filters)
        self.filter_rows.append(filter_row)
        self.clear_filters_buttons.append(clear_filters)
        layout.addLayout(controls)

        sort_row = QWidget()
        sorting = QHBoxLayout(sort_row)
        sorting.setContentsMargins(0, 0, 0, 0)
        sorting.addStretch()
        sorting.addWidget(QLabel('Sắp xếp'))
        sort_control = QComboBox()
        sort_control.setAccessibleName(f'Sắp xếp ảnh trong {title}')
        for key, text in SORT_OPTIONS:
            sort_control.addItem(text, key)
        sort_control.setCurrentIndex(sort_control.findData(self.gallery_sort))
        sorting.addWidget(sort_control)
        self.sort_controls.append(sort_control)
        self.sort_rows.append(sort_row)
        sort_control.currentIndexChanged.connect(lambda _index, control=sort_control: self.change_sort(control.currentData()))
        layout.addWidget(sort_row)

        stack = QStackedWidget()
        gallery = Gallery(self.thumbnails)
        gallery.set_columns(self.columns.currentData())
        gallery.grid_resized.connect(self.schedule_thumbnail_size)
        gallery.setAccessibleName(f'Lưới {title.lower()}')
        gallery.selectionModel().selectionChanged.connect(self.refresh_inspector)
        gallery.doubleClicked.connect(self.open_viewer)
        if index == 0:
            gallery.clicked.connect(self.open_folder_card)
            gallery.activated.connect(self.open_folder_card)
        gallery.customContextMenuRequested.connect(lambda point, view=gallery: self.context_menu(view, point))
        stack.addWidget(gallery)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title, empty_message = section(''), wrapping()
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_message.setMaximumWidth(440)
        empty_button = button('', lambda i=index: self.empty_action(i))
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_message)
        empty_layout.addWidget(empty_button, alignment=Qt.AlignmentFlag.AlignCenter)
        stack.addWidget(empty)
        layout.addWidget(stack, 1)
        self.galleries.append(gallery)
        self.stacks.append((stack, stars, favorite))
        self.empty_states.append((empty_title, empty_message, empty_button))
        self.tabs.addTab(page, title)

    def build_view_menu(self, menu):
        menu.addSeparator()
        self.focus_mode = menu.addAction('Tập trung vào ảnh')
        self.focus_mode.setCheckable(True)
        self.focus_mode.setShortcut(QKeySequence('Ctrl+Shift+F'))
        self.focus_mode.setChecked(self.settings.value('view/focus', False, type=bool))
        self.focus_mode.toggled.connect(lambda enabled: self.save_view_option('focus', enabled))
        self.view_actions = {}
        for key, text, default in (
            ('toolbar', 'Thanh tác vụ', True), ('path', 'Đường dẫn thư mục', False),
            ('quota', 'Tiến độ gói cưới', True), ('filters', 'Bộ lọc', True),
            ('inspector', 'Bảng chọn và ghi chú', True), ('status', 'Thanh trạng thái', True),
        ):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(self.settings.value(f'view/{key}', default, type=bool))
            action.toggled.connect(lambda enabled, name=key: self.save_view_option(name, enabled))
            self.view_actions[key] = action
        menu.addSeparator()
        columns_menu = menu.addMenu('Ảnh mỗi hàng')
        group = QActionGroup(columns_menu)
        self.column_actions = {}
        for index in range(self.columns.count()):
            columns = self.columns.itemData(index)
            action = columns_menu.addAction(str(columns))
            action.setCheckable(True)
            action.setChecked(columns == self.columns.currentData())
            group.addAction(action)
            action.triggered.connect(lambda _checked, row=index: self.columns.setCurrentIndex(row))
            self.column_actions[columns] = action
        sort_menu = menu.addMenu('Sắp xếp ảnh')
        sort_group = QActionGroup(sort_menu)
        self.sort_actions = {}
        for key, text in SORT_OPTIONS:
            action = sort_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(key == self.gallery_sort)
            sort_group.addAction(action)
            action.triggered.connect(lambda _checked, mode=key: self.change_sort(mode))
            self.sort_actions[key] = action
        self.apply_view_options()

    def change_sort(self, mode):
        if mode not in dict(SORT_OPTIONS):
            return
        self.gallery_sort = mode
        self.settings.setValue('gallery_sort', mode)
        for control in self.sort_controls:
            with QSignalBlocker(control):
                control.setCurrentIndex(control.findData(mode))
        for key, action in self.sort_actions.items():
            action.setChecked(key == mode)
        self.refresh_galleries()

    def save_view_option(self, key, enabled):
        self.settings.setValue(f'view/{key}', enabled)
        self.apply_view_options()

    def view_option_enabled(self, key):
        return not self.focus_mode.isChecked() and self.view_actions[key].isChecked()

    def apply_view_options(self):
        for action in self.view_actions.values():
            action.setEnabled(not self.focus_mode.isChecked())
        for key, widget in (('toolbar', self.toolbar), ('path', self.path), ('quota', self.quota),
                            ('inspector', self.inspector)):
            widget.setVisible(self.view_option_enabled(key))
        self.update_filter_visibility()
        self.update_status_visibility()

    def update_filter_visibility(self):
        visible = self.view_option_enabled('filters')
        for row in self.sort_rows:
            row.setVisible(visible)
        for index, (row, clear_button) in enumerate(zip(self.filter_rows, self.clear_filters_buttons)):
            row.setVisible(visible)
            clear_button.setVisible(not visible and self.filters_active(index))

    def update_status_visibility(self, *_):
        status = self.statusBar()
        status.setVisible(self.view_option_enabled('status') or bool(self.busy or status.currentMessage()))

    def build_inspector(self):
        frame = QFrame(objectName='panel')
        frame.setFixedWidth(276)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(section('Lựa chọn của bạn'))
        self.selection_label = wrapping('Bấm vào một ảnh để bắt đầu.')
        self.selection_label.setObjectName('muted')
        layout.addWidget(self.selection_label)
        self.tag_button = QPushButton('Gán loại ảnh')
        self.tag_menu = QMenu(self.tag_button)
        self.tag_button.setMenu(self.tag_menu)
        layout.addWidget(self.tag_button)
        self.clear_button = button('Bỏ tất cả loại', self.clear_tags)
        layout.addWidget(self.clear_button)
        self.tags_label = wrapping()
        layout.addWidget(self.tags_label)

        score_row = QHBoxLayout()
        score_row.addWidget(QLabel('Điểm ảnh'))
        self.score_input = QSpinBox()
        self.score_input.setRange(-1, 100)
        self.score_input.setSpecialValueText('Chưa chấm')
        self.score_input.setSuffix(' / 100')
        self.score_input.setKeyboardTracking(False)
        self.score_input.setAccessibleName('Điểm của ảnh đang chọn')
        self.score_input.setToolTip('Nhập điểm 0–100 cho một ảnh. Chọn “Chưa chấm” để bỏ điểm.')
        self.score_input.valueChanged.connect(self.change_score)
        score_row.addWidget(self.score_input, 1)
        layout.addLayout(score_row)

        layout.addWidget(section('Đánh dấu để xem lại'))
        rating = QHBoxLayout()
        self.stars_buttons = []
        for score in range(1, 6):
            star = button(str(score), lambda checked=False, value=score: self.set_stars(value))
            star.setAccessibleName(f'Đánh giá {score} sao')
            star.setToolTip(f'{score} sao (Shift+{score})')
            star.setCheckable(True)
            star.setMinimumWidth(35)
            rating.addWidget(star)
            self.stars_buttons.append(star)
        layout.addLayout(rating)
        self.favorite_button = button('♡  Yêu thích', self.toggle_favorite)
        self.favorite_button.setCheckable(True)
        layout.addWidget(self.favorite_button)

        note_title = section('Ghi chú chỉnh sửa')
        layout.addWidget(note_title)
        self.note = QPlainTextEdit()
        self.note.setAccessibleName('Ghi chú chỉnh sửa cho ảnh đang chọn')
        self.note.setPlaceholderText('Ví dụ: Làm sáng da và giữ màu nền…')
        self.note.setFixedHeight(74)
        self.note.textChanged.connect(self.note_changed)
        layout.addWidget(self.note)
        hints = QGridLayout()
        self.hints = []
        for i, hint in enumerate(HINTS):
            hint_button = button(hint, lambda checked=False, value=hint: self.add_hint(value))
            if i == 2:
                hints.addWidget(hint_button, 1, 0, 1, 2)
            else:
                row, column = (0, i) if i < 2 else (2, i - 3)
                hints.addWidget(hint_button, row, column)
            self.hints.append(hint_button)
        layout.addLayout(hints)
        layout.addStretch()
        return frame

    def build_shortcuts(self):
        for key in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(key)), self)
            shortcut.activated.connect(lambda number=key: self.tag_shortcut(number))
        for number, shifted in enumerate('!@#$%', 1):
            shortcut = QShortcut(self)
            shortcut.setKeys([QKeySequence(f'Shift+{number}'), QKeySequence(f'Shift+{shifted}')])
            shortcut.activated.connect(lambda score=number: self.shortcut_action(lambda: self.set_stars(score)))
        for key, callback in (('0', self.clear_tags), ('Delete', self.clear_tags), ('F', self.toggle_favorite),
                              ('C', self.compare)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda action=callback: self.shortcut_action(action))
        shortcut = QShortcut(QKeySequence('F1'), self)
        shortcut.activated.connect(self.show_shortcuts)

    def shortcut_action(self, action):
        if not isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit, QComboBox, QSpinBox)):
            action()

    def tag_shortcut(self, key):
        item = next((item for item in self.project.categories if item.shortcut == key), None)
        if item:
            self.shortcut_action(lambda: self.toggle_category(item.id, self.selected_paths()))

    def show_shortcuts(self):
        categories = '\n'.join(f'{item.shortcut}  Gán hoặc bỏ {item.name}' for item in self.project.categories)
        information(self, 'Danh sách phím tắt', '\n'.join(filter(None, [categories, '0 hoặc Delete  Bỏ tất cả loại',
                    'Shift+1 đến Shift+5  Đánh giá sao', 'F  Bật hoặc tắt yêu thích', 'C  So sánh 2–4 ảnh',
                    'Ctrl+Shift+F  Bật hoặc tắt chế độ tập trung vào ảnh',
                    '← và →  Chuyển ảnh trong trình xem', 'Esc  Đóng trình xem', 'F1  Mở danh sách này'])))

    def show_guide(self):
        GuideDialog(self.assets, self).exec()
        self.settings.setValue('guide_seen', True)

    def restore(self):
        if not self.settings.value('guide_seen', False, type=bool):
            self.show_guide()
        last = self.settings.value('last_root', '', type=str)
        if last:
            if Path(last).is_dir():
                self.open_root(Path(last), restoring=True)
            else:
                self.statusBar().showMessage('Thư mục lần trước không còn khả dụng. Hãy chọn thư mục ảnh.', 9000)

    def set_dark(self, enabled):
        self.settings.setValue('dark', enabled)
        apply_theme(QApplication.instance(), enabled)

    def choose_root(self):
        if self.busy:
            return
        folder = choose_path(self, 'Chọn thư mục ảnh cưới', str(self.root or ''))
        if folder:
            self.open_root(Path(folder))

    def open_root(self, root, restoring=False):
        if self.busy or not self.flush_save():
            return
        root = root.resolve()
        if root == self.root and not self.read_only:
            self.start_scan()
            return
        if self.lock:
            self.lock.unlock()
        if root != self.root:
            self.active_folder = ''
        self.root = root
        self.lock = QLockFile(str(root / f'{TAGS_FILE}.lock'))
        self.lock.setStaleLockTime(0)
        self.read_only = ''
        if not self.lock.tryLock(0):
            self.read_only = 'Chỉ đọc. Thư mục đang mở ở phiên khác hoặc bạn chưa có quyền ghi.'

        existed = False
        warning = ''
        try:
            self.project = load_project(root / TAGS_FILE)
            existed = True
        except FileNotFoundError:
            try:
                self.project = new_project(root)
            except (OSError, ValueError) as error:
                warning = f'Không đọc được goi_chup.json. Đã dùng gói mặc định.\n{error}'
                self.project = Project()
        except (OSError, ValueError) as error:
            log.warning('Không nạp được phiên %s', root, exc_info=True)
            self.project = Project()
            self.read_only = f'Chỉ đọc. Không đọc được photo_tags.json. {error}'

        self.path.setText(str(root))
        self.path.setToolTip(str(root))
        self.folder_button.setToolTip(str(root))
        self.settings.setValue('last_root', str(root))
        self.refresh_categories()
        self.start_scan()
        if self.project.needs_save and not self.read_only:
            self.mark_dirty()
        if existed:
            self.statusBar().showMessage('Tiếp tục lựa chọn lần trước', 6500 if restoring else 4500)
        if warning:
            information(self, 'Cấu hình gói cưới', warning, warning=True)

    def start_scan(self):
        self.cancel_scan.set()
        self.scan_jobs.pool.clear()
        self.scan_jobs.handlers.clear()
        cancel = self.cancel_scan = Event()
        root = self.root
        self.scanning = True
        self.scan_error = ''
        self.entries = []
        self.entry_map = {}
        self.folders_by_parent.clear()
        self.photos_by_parent.clear()
        self.thumbnails.reset(root, self.thumbnails.size)
        self.refresh_counts()
        self.refresh_galleries()

        project = Project(self.project.customer_name, self.project.categories, self.project.photos.copy())

        def work(_):
            folders = []
            entries = scan(root, True, cancel, folders=folders)
            changed = not cancel.is_set() and reconcile_paths(root, project, [entry.relative for entry in entries], True)
            return entries, sorted(folders, key=lambda folder: folder.name.casefold()), changed

        def complete(result, error):
            if cancel.is_set():
                return
            self.scanning = False
            if error:
                self.scan_error = f'Không thể đọc thư mục ảnh. {error}'
            else:
                entries, folders, changed = result
                self.entries = entries
                self.entry_map = {entry.relative: entry for entry in entries}
                for entry in entries:
                    self.photos_by_parent[entry.relative.rpartition('/')[0]].append(entry)
                for folder in folders:
                    self.folders_by_parent[folder.relative.rpartition('/')[0]].append(folder)
                if self.active_folder and not any(folder.relative == self.active_folder for folder in folders):
                    self.active_folder = ''
                if changed:
                    self.project.photos = project.photos
                    if not self.read_only:
                        self.mark_dirty()
            self.refresh_counts()
            self.refresh_galleries()

        self.scan_jobs.start(work, complete)

    def change_columns(self, _):
        columns = self.columns.currentData()
        self.settings.setValue('gallery_columns', columns)
        self.column_actions[columns].setChecked(True)
        for gallery in self.galleries:
            gallery.set_columns(columns)

    def schedule_thumbnail_size(self):
        self.size_timer.start()

    def apply_thumbnail_size(self):
        gallery = self.galleries[self.tabs.currentIndex()]
        if gallery.isVisible() and gallery.thumbnail_size() != self.thumbnails.size:
            self.thumbnails.reset(self.root, gallery.thumbnail_size())
            gallery.viewport().update()

    def show_thumbnail_progress(self, done, total):
        self.thumbnail_progress.setText(f'Ảnh thu nhỏ {done}/{total}' if total else '')

    def tab_changed(self, _):
        if hasattr(self, 'selection_label'):
            self.schedule_thumbnail_size()
            self.refresh_inspector()

    def open_folder_card(self, index):
        entry = index.data(ENTRY)
        if isinstance(entry, FolderEntry):
            self.browse_folder(entry.relative)

    def go_up(self):
        self.browse_folder(self.active_folder.rpartition('/')[0])

    def browse_folder(self, relative):
        if relative == self.active_folder:
            return
        self.active_folder = relative
        gallery = self.galleries[0]
        gallery.clearSelection()
        self.refresh_galleries()
        gallery.scrollToTop()
        if gallery.isVisible():
            gallery.selectionModel().setCurrentIndex(gallery.gallery_model.index(0, 0),
                                                     QItemSelectionModel.SelectionFlag.NoUpdate)
            gallery.setFocus()
        else:
            self.folder_up.setFocus()

    def refresh_categories(self):
        categories = {item.id: item for item in self.project.categories}
        for gallery in self.galleries:
            gallery.delegate.categories = categories
            gallery.gallery_model.names = {key: item.name for key, item in categories.items()}
            gallery.viewport().update()
        previous = self.category_filter.currentData()
        with QSignalBlocker(self.category_filter):
            self.category_filter.clear()
            self.category_filter.addItem('Tất cả loại', None)
            for item in self.project.categories:
                self.category_filter.addItem(item.name, item.id)
            self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(previous)))

    def refresh_counts(self):
        self.total, self.totals = counts(self.project, self.entry_map)
        package = []
        for item in self.project.categories:
            count = self.totals[item.id]
            value = f'{count}/{item.max_count}' if item.max_count is not None else str(count)
            package.append(f'{item.name} {value}')
        self.quota.setText('  ·  '.join(package) if package else 'Chưa thiết lập loại ảnh cho gói cưới')
        self.status.setText(f'{len(self.entries):,} ảnh  ·  {self.total:,} đã chọn')

    def refresh_galleries(self, *_):
        root_name = (self.root.name or str(self.root)) if self.root else ''
        breadcrumb = ' / '.join([root_name, *self.active_folder.split('/')]) if self.active_folder else root_name
        self.folder_path.setText(breadcrumb)
        self.folder_path.setToolTip(str(self.root / self.active_folder) if self.root else '')
        self.folder_up.setEnabled(bool(self.active_folder) and not self.scanning)
        for i, (stack, stars, favorite) in enumerate(self.stacks):
            rating = stars.currentData()
            loved = favorite.isChecked()
            category = self.category_filter.currentData() if i == 1 else None
            search = self.search.text().strip().casefold() if i == 1 else ''
            visible = self.folders_by_parent.get(self.active_folder, []).copy() if i == 0 else []
            photos = self.photos_by_parent.get(self.active_folder, []) if i == 0 else self.entries
            photos = sorted(photos, key=lambda entry: photo_sort_key(
                entry.relative, self.project.photo(entry.relative), self.gallery_sort),
                reverse=self.gallery_sort == 'name_desc')
            for entry in photos:
                photo = self.project.photo(entry.relative)
                if ((i == 0 or photo.category_ids) and (category is None or category in photo.category_ids)
                        and (rating is None or photo.stars == rating) and (not loved or photo.favorite)
                        and (not search or search in entry.name.casefold())):
                    visible.append(entry)
            view = self.galleries[i]
            model = view.gallery_model
            if model.entries != visible or model.project is not self.project:
                self.set_gallery_entries(view, visible)
            stack.setCurrentIndex(0 if visible else 1)
            if not visible:
                self.refresh_empty(i, rating is not None or loved or bool(category or search))
        self.refresh_controls()
        self.refresh_inspector()
        self.update_filter_visibility()

    def set_gallery_entries(self, view, entries):
        model = view.gallery_model
        selected = view.selected_paths()
        current = view.currentIndex().data(ENTRY)
        selection = view.selectionModel()
        with QSignalBlocker(selection):
            model.set_entries(entries, self.project)
            rows = sorted(model.rows[path] for path in selected if path in model.rows)
            if rows:
                group = QItemSelection()
                first = last = rows[0]
                for row in rows[1:]:
                    if row != last + 1:
                        group.select(model.index(first, 0), model.index(last, 0))
                        first = row
                    last = row
                group.select(model.index(first, 0), model.index(last, 0))
                selection.select(group, QItemSelectionModel.SelectionFlag.Select)
            if current and current.relative in model.rows:
                selection.setCurrentIndex(model.index(model.rows[current.relative], 0), QItemSelectionModel.SelectionFlag.NoUpdate)

    def refresh_empty(self, index, filtered):
        title, message, action = self.empty_states[index]
        if self.scanning:
            heading, copy, label = 'Đang tìm ảnh…', 'Ảnh sẽ xuất hiện khi quét xong thư mục.', ''
        elif self.scan_error:
            heading, copy, label = 'Chưa mở được thư mục', self.scan_error, 'Chọn thư mục khác'
        elif self.root is None:
            heading, copy, label = 'Mở thư mục ảnh cưới', 'Chọn thư mục ảnh xem trước mà studio đã gửi cho bạn.', 'Chọn thư mục'
        elif index == 0 and self.active_folder and not filtered:
            heading, copy, label = 'Thư mục này chưa có ảnh', 'Quay lên để xem các thư mục khác.', 'Quay về thư mục cha'
        elif not self.entries:
            heading, copy, label = 'Thư mục chưa có ảnh', 'Hãy chọn thư mục chứa ảnh xem trước.', 'Chọn thư mục khác'
        elif filtered:
            heading, copy, label = 'Không tìm thấy ảnh phù hợp', 'Đặt lại bộ lọc để xem thêm ảnh.', 'Đặt lại bộ lọc'
        else:
            heading, copy, label = 'Bạn chưa chọn ảnh nào', 'Gán ít nhất một loại trong tab Tất cả ảnh để ảnh xuất hiện ở đây.', 'Xem tất cả ảnh'
        title.setText(heading)
        message.setText(copy)
        action.setText(label)
        action.setVisible(bool(label))

    def empty_action(self, index):
        label = self.empty_states[index][2].text()
        if label == 'Xem tất cả ảnh':
            self.tabs.setCurrentIndex(0)
        elif label == 'Quay về thư mục cha':
            self.go_up()
        elif label == 'Đặt lại bộ lọc':
            self.reset_filters(index)
        else:
            self.choose_root()

    def filters_active(self, index):
        _, stars, favorite = self.stacks[index]
        return stars.currentData() is not None or favorite.isChecked() or (
            index == 1 and (self.category_filter.currentData() is not None or bool(self.search.text().strip())))

    def reset_filters(self, index):
        _, stars, favorite = self.stacks[index]
        with QSignalBlocker(stars), QSignalBlocker(favorite):
            stars.setCurrentIndex(0)
            favorite.setChecked(False)
        if index == 1:
            with QSignalBlocker(self.category_filter), QSignalBlocker(self.search):
                self.category_filter.setCurrentIndex(0)
                self.search.clear()
        self.refresh_galleries()

    def selected_paths(self):
        return self.galleries[self.tabs.currentIndex()].selected_paths()

    def available(self):
        return self.root is not None and not (self.busy or self.scanning or self.scan_error)

    def editable(self):
        return self.available() and not self.read_only

    def refresh_controls(self):
        self.folder_button.setEnabled(not self.busy)
        self.open_action.setEnabled(not self.busy)
        self.category_action.setEnabled(self.editable())
        self.ai_action.setEnabled(self.editable() and bool(self.entries))
        self.ai_button.setEnabled(self.ai_action.isEnabled())
        self.backup_action.setEnabled(self.available())
        self.restore_action.setEnabled(not self.busy and not self.scanning)
        self.copy_action.setEnabled(self.available() and self.total > 0)
        self.raw_action.setEnabled(not self.busy)
        self.export_button.setEnabled(self.available() and self.total > 0)
        self.export_action.setEnabled(self.export_button.isEnabled())
        self.export_button.setToolTip('Gán loại cho ít nhất một ảnh để xuất danh sách.' if not self.total else '')
        self.notice.setText(self.read_only or self.save_error)
        self.notice.setVisible(bool(self.read_only or self.save_error))
        self.retry.setVisible(bool(self.save_error))

    def refresh_inspector(self, *_):
        paths = self.selected_paths()
        can_edit = self.editable() and bool(paths)
        records = [self.project.photo(path) for path in paths]
        single = records[0] if len(records) == 1 else None
        self.compare_button.setEnabled(self.available() and 2 <= len(paths) <= 4)
        self.compare_action.setEnabled(self.compare_button.isEnabled())
        self.tag_button.setEnabled(can_edit and bool(self.project.categories))
        self.clear_button.setEnabled(can_edit and any(photo.category_ids for photo in records))
        if single is not None:
            self.selection_label.setText(self.entry_map.get(paths[0], Path(paths[0])).name)
            self.selection_label.setToolTip(paths[0])
            tags = [item.name for item in self.project.categories if item.id in single.category_ids]
            self.tags_label.setText(' · '.join(tags) or 'Chưa gán loại')
        else:
            self.selection_label.setText(f'{len(paths)} ảnh đang được chọn' if paths else 'Bấm vào một ảnh để bắt đầu.')
            self.selection_label.setToolTip('')
            self.tags_label.setText('')
        self.tags_label.setVisible(single is not None)
        self.score_input.setEnabled(can_edit and single is not None)
        with QSignalBlocker(self.score_input):
            self.score_input.setValue(single.ai_score if single is not None and single.ai_score is not None else -1)
        self.fill_tag_menu(self.tag_menu, paths)
        for number, star in enumerate(self.stars_buttons, 1):
            star.setEnabled(can_edit)
            star.setChecked(bool(records) and all(photo.stars == number for photo in records))
        favorite = bool(records) and all(photo.favorite for photo in records)
        self.favorite_button.setEnabled(can_edit)
        self.favorite_button.setChecked(favorite)
        self.favorite_button.setText('♥  Đã yêu thích' if favorite else '♡  Yêu thích')
        self.note_path = paths[0] if single is not None else None
        self.note.setEnabled(single is not None)
        self.note.setReadOnly(not can_edit)
        text = single.note if single is not None else ''
        if self.note.toPlainText() != text:
            with QSignalBlocker(self.note):
                self.note.setPlainText(text)
        for hint in self.hints:
            hint.setEnabled(can_edit and single is not None)

    def fill_tag_menu(self, menu, paths, after=None, parent=None):
        menu.clear()
        for item in self.project.categories:
            label = item.name.replace('&', '&&')
            action = menu.addAction(f'{item.shortcut}  {label}')
            action.setCheckable(True)
            action.setChecked(bool(paths) and all(item.id in self.project.photo(path).category_ids for path in paths))
            action.setEnabled(self.editable() and bool(paths))

            def toggle(_checked=False, category_id=item.id):
                self.toggle_category(category_id, paths, parent)
                if after:
                    after()

            action.triggered.connect(toggle)

    def context_menu(self, view, point):
        index = view.indexAt(point)
        if not isinstance(index.data(ENTRY), ImageEntry):
            return
        selection = view.selectionModel()
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        menu = QMenu(self)
        self.fill_tag_menu(menu, view.selected_paths())
        menu.addSeparator()
        menu.addAction('Xem ảnh lớn', lambda: self.open_viewer(index))
        compare = menu.addAction('So sánh ảnh', self.compare)
        compare.setEnabled(self.compare_action.isEnabled())
        clear = menu.addAction('Bỏ tất cả loại', self.clear_tags)
        clear.setEnabled(self.clear_button.isEnabled())
        menu.addSeparator()
        rating = menu.addMenu('Đánh giá sao')
        rating.setEnabled(self.editable())
        for number in range(1, 6):
            star = rating.addAction(f'{number} sao')
            star.setCheckable(True)
            star.setChecked(self.stars_buttons[number - 1].isChecked())
            star.triggered.connect(lambda _checked, score=number: self.set_stars(score))
        favorite = menu.addAction('Yêu thích', self.toggle_favorite)
        favorite.setCheckable(True)
        favorite.setChecked(self.favorite_button.isChecked())
        favorite.setEnabled(self.editable())
        note = menu.addAction('Ghi chú chỉnh sửa…', self.show_note_panel)
        note.setEnabled(self.note_path is not None)
        menu.exec(view.viewport().mapToGlobal(point))
        menu.deleteLater()

    def show_note_panel(self):
        self.focus_mode.setChecked(False)
        self.view_actions['inspector'].setChecked(True)
        self.note.setFocus()

    def toggle_category(self, category_id, paths, parent=None):
        if not self.editable() or not paths:
            return
        category = next((item for item in self.project.categories if item.id == category_id), None)
        if not category:
            return
        adding, affected = category_change(self.project, paths, category_id)
        projected = self.totals[category_id] + len(affected)
        if (adding and category.max_count is not None and projected > category.max_count
                and not confirm(parent or self, 'Chọn thêm ảnh ngoài gói',
                                f'“{category.name}” sẽ có {projected}/{category.max_count} ảnh. '
                                'Studio có thể tính thêm phí cho phần vượt gói. Bạn muốn chọn thêm?', 'Chọn thêm')):
            self.refresh_inspector()
            return
        for path in affected:
            previous = self.project.photo(path).category_ids
            updated = previous + (category_id,) if adding else tuple(tag for tag in previous if tag != category_id)
            self.project.update(path, category_ids=updated)
        self.photos_changed(affected)

    def change_selection(self, **changes):
        if self.editable():
            updated = [path for path in self.selected_paths() if self.project.update(path, **changes)]
            self.photos_changed(updated)

    def clear_tags(self):
        self.change_selection(category_ids=())

    def set_stars(self, rating):
        paths = self.selected_paths()
        reset = bool(paths) and all(self.project.photo(path).stars == rating for path in paths)
        self.change_selection(stars=0 if reset else rating)

    def change_score(self, score):
        paths = self.selected_paths()
        if self.editable() and len(paths) == 1 and -1 <= score <= 100:
            value = None if score == -1 else score
            if self.project.update(paths[0], ai_score=value):
                self.photos_changed(paths)

    def toggle_favorite(self):
        paths = self.selected_paths()
        unset = bool(paths) and all(self.project.photo(path).favorite for path in paths)
        self.change_selection(favorite=not unset)

    def note_changed(self):
        if self.note_path and self.editable() and self.project.update(self.note_path, note=self.note.toPlainText()):
            self.mark_dirty()
            for gallery in self.galleries:
                gallery.gallery_model.changed([self.note_path])

    def add_hint(self, hint):
        current = self.note.toPlainText().strip()
        if hint not in current.split('\n'):
            self.note.appendPlainText(hint)
            self.note.setFocus()

    def photos_changed(self, paths):
        if paths:
            self.mark_dirty()
            self.refresh_counts()
            self.refresh_galleries()
            for gallery in self.galleries:
                gallery.gallery_model.changed(paths)

    def edit_categories(self):
        if not self.editable():
            return
        dialog = CategoriesDialog(self.project, self)
        if dialog.exec():
            categories = dialog.categories
            customer = dialog.customer.text().strip()
            if categories == self.project.categories and customer == self.project.customer_name:
                return
            self.project.customer_name = customer
            self.project.categories = categories
            ids = {item.id for item in categories}
            for path, record in list(self.project.photos.items()):
                self.project.update(path, category_ids=tuple(tag for tag in record.category_ids if tag in ids))
            self.mark_dirty()
            self.refresh_categories()
            self.refresh_counts()
            self.refresh_galleries()

    def mark_dirty(self):
        self.dirty = True
        self.save_timer.start()

    def flush_save(self):
        self.save_timer.stop()
        if not self.dirty:
            return True
        try:
            save_project(self.root / TAGS_FILE, self.project)
        except (OSError, ValueError) as error:
            log.warning('Không lưu được lựa chọn', exc_info=True)
            self.save_error = f'Chưa lưu được lựa chọn. Hãy thử lưu lại. {error}'
            self.refresh_controls()
            return False
        self.dirty = False
        self.save_error = ''
        self.refresh_controls()
        return True

    def snapshot(self):
        return self.project.snapshot(self.entry_map.keys())

    def set_busy(self, label, total=0):
        self.busy = label
        self.task_progress.setRange(0, total)
        self.task_progress.setValue(0)
        self.task_progress.setVisible(bool(label))
        if label:
            self.status.setText(label)
        else:
            self.refresh_counts()
        self.refresh_controls()
        self.refresh_inspector()
        self.update_status_visibility()

    def open_viewer(self, index):
        entry = index.data(ENTRY)
        if self.available() and isinstance(entry, ImageEntry):
            photos = [item for item in index.model().entries if isinstance(item, ImageEntry)]
            ViewerDialog(self, photos, photos.index(entry)).exec()

    def compare(self):
        paths = self.selected_paths()
        if self.available() and 2 <= len(paths) <= 4:
            ViewerDialog(self, [self.entry_map[path] for path in paths], compare=True).exec()

    def open_ai_advisor(self):
        if self.editable() and self.entries:
            AdvisorDialog(self).exec()

    def closeEvent(self, event):
        if self.busy or not self.flush_save():
            if self.busy:
                self.statusBar().showMessage('Hãy đợi tác vụ hoàn tất trước khi đóng cửa sổ.', 4000)
            event.ignore()
            return
        self.cancel_scan.set()
        self.scan_jobs.pool.clear()
        self.size_timer.stop()
        self.thumbnails.reset(None, self.thumbnails.size)
        if self.lock and self.lock.isLocked():
            self.lock.unlock()
        event.accept()
