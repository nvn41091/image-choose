from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.data_store import load_project
from main import ASSETS
from ui.gallery import ENTRY
from ui.theme import apply_theme
from ui.viewer import ViewerDialog
from ui.window import MainWindow


class WindowsWorkflowTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.root = self.base / 'Ảnh thử'
        self.root.mkdir()
        self.window = self.create_window('settings')

    def create_window(self, name):
        apply_theme(self.app, False)
        settings = QSettings(str(self.base / f'{name}.ini'), QSettings.Format.IniFormat)
        window = MainWindow(self.base / name, ASSETS, settings)
        window.show()
        window.activateWindow()

        def close():
            window.close()
            for jobs in (window.jobs, window.scan_jobs, window.thumbnails.jobs):
                jobs.pool.waitForDone()
            self.app.processEvents()

        self.addCleanup(close)
        return window

    def wait(self, condition, seconds=8):
        deadline = monotonic() + seconds
        while not condition() and monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition(), 'Tác vụ giao diện chưa hoàn tất đúng hạn')

    def populate(self):
        Image.new('RGB', (180, 100), '#cfa29e').save(self.root / '01.jpg')
        Image.new('RGB', (100, 180), '#7aaf94').save(self.root / '02.jpg')
        (self.root / '03.JPG').write_bytes(b'invalid')
        (self.root / 'goi_chup.json').write_text('{"customer_name":"Minh và An","limits":{"album":1}}', encoding='utf-8')
        self.window.open_root(self.root)
        self.wait(lambda: len(self.window.entries) == 3)

    def select(self, *rows, tab=0):
        self.window.activateWindow()
        self.app.processEvents()
        self.window.tabs.setCurrentIndex(tab)
        view = self.window.galleries[tab]
        view.setFocus()
        model = view.gallery_model
        selection = view.selectionModel()
        selection.clearSelection()
        for row in rows:
            selection.select(model.index(row, 0), QItemSelectionModel.SelectionFlag.Select)
        return view

    def test_chatgpt_scopes_ranking_and_quota_review(self):
        from core.ai_advisor import CollectionReview, Recommendation, Review
        from ui.ai_advisor import AdvisorDialog

        nested = self.root / 'Lễ cưới' / 'Buổi sáng'
        nested.mkdir(parents=True)
        paths = ['01.jpg', 'Lễ cưới/02.jpg', 'Lễ cưới/Buổi sáng/03.jpg']
        for path in paths:
            Image.new('RGB', (90, 60)).save(self.root / path)
        (self.root / 'goi_chup.json').write_text('{"limits":{"album":1}}', encoding='utf-8')
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 3)
        window.browse_folder('Lễ cưới')
        dialog = AdvisorDialog(window)
        self.addCleanup(dialog.close)
        dialog.auth_mode.setCurrentIndex(dialog.auth_mode.findData('api'))
        dialog.show()
        dialog.scope.setCurrentIndex(dialog.scope.findData('folder'))
        self.assertEqual(dialog.scope_paths(), paths[1:])
        dialog.scope.setCurrentIndex(dialog.scope.findData('all'))
        window.stacks[0][2].setChecked(True)
        self.assertEqual(dialog.scope_paths(), paths)
        self.assertFalse(dialog.run_button.isEnabled())
        dialog.api_key.setText('test-session-key')
        dialog.consent.setChecked(True)
        recommendations = tuple(Recommendation(path, 95 - i * 10, 'Bố cục tốt', 'Tăng sáng')
                                for i, path in enumerate(paths))
        result = CollectionReview(Review('Gợi ý', recommendations), 3, 3)
        with patch('ui.ai_advisor.analyze_collection', return_value=result) as evaluate:
            dialog.run_button.click()
            self.assertTrue(window.busy)
            self.assertFalse(window.close())
            self.wait(lambda: dialog.table.rowCount() == 3)
        self.assertEqual(evaluate.call_args.args[1], paths)
        self.assertEqual(len(dialog.selected_recommendations()), 1)
        self.assertEqual(window.total, 0)
        self.assertTrue(all(not photo.category_ids and not photo.favorite for photo in window.project.photos.values()))
        self.assertEqual({path: photo.ai_score for path, photo in window.project.photos.items()},
                         dict(zip(paths, (95, 85, 75))))
        dialog.clear_button.click()
        self.assertFalse(dialog.selected_recommendations())
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.top_count.setValue(2)
        dialog.top_button.click()
        dialog.category.setCurrentIndex(dialog.category.findData('album'))
        dialog.notes.setChecked(True)
        with patch('ui.ai_advisor.confirm', return_value=False):
            dialog.apply_button.click()
        self.assertEqual(window.total, 0)
        self.assertTrue(all(not photo.category_ids and not photo.favorite for photo in window.project.photos.values()))
        with patch('ui.ai_advisor.confirm', return_value=True):
            dialog.apply_button.click()
        self.assertEqual(window.total, 2)
        saved = load_project(self.root / 'photo_tags.json')
        self.assertTrue(saved.photo(paths[0]).favorite)
        self.assertEqual(saved.photo(paths[0]).category_ids, ('album',))
        self.assertIn('Tăng sáng', saved.photo(paths[0]).note)
        self.assertNotIn('[ChatGPT]', saved.photo(paths[0]).note)
        self.assertEqual(saved.photo(paths[0]).stars, 0)
        window.settings.sync()
        self.assertNotIn('test-session-key', Path(window.settings.fileName()).read_text(encoding='utf-8'))
        self.assertNotIn('test-session-key', (self.root / 'photo_tags.json').read_text(encoding='utf-8'))

    def test_chatgpt_cancel_waits_for_worker_and_releases_busy_state(self):
        from core.ai_advisor import CollectionReview, Review
        from ui.ai_advisor import AdvisorDialog

        self.populate()
        dialog = AdvisorDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.auth_mode.setCurrentIndex(dialog.auth_mode.findData('api'))
        dialog.api_key.setText('test-key')
        dialog.consent.setChecked(True)
        dialog.show()

        def evaluate(root, paths, key, model, criteria, cancel, progress):
            cancel.wait(3)
            return CollectionReview(Review('Đã dừng', ()), 0, len(paths), True)

        with patch('ui.ai_advisor.analyze_collection', side_effect=evaluate):
            dialog.run_button.click()
            self.assertTrue(self.window.busy)
            dialog.reject()
            self.assertTrue(dialog.cancel.is_set())
            self.wait(lambda: not dialog.running)
        self.assertFalse(self.window.busy)
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertTrue(dialog.close())

    def test_chatgpt_plan_uses_selected_account_model_and_never_falls_back(self):
        from core.ai_advisor import CollectionReview, Review
        from core.chatgpt_auth import Account
        from ui.ai_advisor import AdvisorDialog

        self.populate()
        account = Account('oaiapp_ui_test', 'test@example.test', 'user-test', True, True, True)
        auth = Mock()
        auth.accounts.return_value = ([account], account.client_id)
        auth.models.return_value = [('available-vision-model', 'Vision model')]
        self.window.chatgpt_auth = auth
        self.window.ai_api_key = 'must-not-be-used'
        dialog = AdvisorDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.show()
        self.wait(lambda: dialog.plan_model.count() == 1 and not dialog.auth_running)
        self.assertEqual(dialog.auth_mode.currentData(), 'chatgpt')
        self.assertFalse(dialog.api_key.isVisible())
        self.assertIn('không dùng API credit', dialog.plan_status.text())
        dialog.consent.setChecked(True)
        result = CollectionReview(Review('Chưa có kết quả', ()), 0, 3, error='Đã chạm giới hạn dùng gói ChatGPT')
        with patch('ui.ai_advisor.analyze_collection', return_value=result) as evaluate:
            dialog.run_button.click()
            self.wait(lambda: not dialog.running)
        self.assertEqual(evaluate.call_args.args[2], '')
        self.assertEqual(evaluate.call_args.args[3], 'available-vision-model')
        self.assertEqual(evaluate.call_args.kwargs['plan_session'].client_id, account.client_id)
        self.assertEqual(dialog.auth_mode.currentData(), 'chatgpt')
        self.assertIn('giới hạn', dialog.message.text())
        self.assertEqual(self.window.ai_api_key, 'must-not-be-used')
        self.assertFalse(self.window.project.photos)
        with patch('ui.ai_advisor.QDesktopServices.openUrl', return_value=True) as open_url:
            dialog.usage_button.click()
        self.assertEqual(open_url.call_args.args[0].toString(), 'https://chatgpt.com/settings/usage')

    def test_chatgpt_sign_in_and_sign_out_ui(self):
        from core.chatgpt_auth import Account
        from ui.ai_advisor import AdvisorDialog

        self.populate()
        account = Account('oaiapp_new_ui', 'test@example.test', 'user-test', True, True, False)
        auth = Mock()
        registrations = []
        auth.accounts.side_effect = lambda: (registrations.copy(), account.client_id if registrations else '')
        attempt = Mock()
        attempt.url = 'https://auth.openai.com/api/accounts/authorize?state=unit-test'
        attempt.wait.return_value = {'state': 'unit-test', 'code': 'unit-test-code'}
        auth.prepare_login.return_value = attempt
        auth.models.return_value = [('vision', 'Vision')]

        def sign_in(*args):
            registrations.append(account)
            return account

        def sign_out(*args):
            registrations[:] = [Account(account.client_id, account.email, account.subject, False, True, True)]
            return False

        auth.finish_login.side_effect = sign_in
        auth.sign_out.side_effect = sign_out
        self.window.chatgpt_auth = auth
        dialog = AdvisorDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.show()
        with (patch('ui.ai_advisor.QDesktopServices.openUrl', return_value=True) as browser,
              patch('ui.ai_advisor.information') as welcome):
            dialog.login_button.click()
            self.wait(lambda: dialog.plan_model.count() == 1 and not dialog.auth_running)
        self.assertTrue(browser.called)
        self.assertTrue(welcome.called)
        auth.mark_welcomed.assert_called_once_with(account.client_id)
        self.assertTrue(dialog.logout_button.isEnabled())
        dialog.logout_button.click()
        self.wait(lambda: not dialog.auth_running)
        self.assertFalse(dialog.selected_account().signed_in)
        self.assertFalse(dialog.plan_model.count())
        self.assertIn('chưa xác nhận', dialog.message.text())
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertFalse(self.window.busy)

    def test_chatgpt_rejected_code_reopens_once_with_issued_client_then_signs_in(self):
        from core.chatgpt_auth import Account, AuthError, AuthorizationCodeRejected
        from ui.ai_advisor import AdvisorDialog

        self.populate()
        account = Account('oaiapp_retry', 'retry@example.test', 'user-retry', True, True, True)
        auth = Mock()
        registrations = []
        auth.accounts.side_effect = lambda: (registrations.copy(), account.client_id if registrations else '')
        attempt = Mock()
        attempt.url = 'https://auth.openai.com/api/accounts/authorize?state=unit-retry'
        attempt.wait.return_value = {'state': 'unit-retry', 'code': 'unit-code'}
        auth.prepare_login.return_value = attempt
        auth.models.return_value = [('vision', 'Vision')]
        calls = []

        def finish(*args):
            calls.append(1)
            if len(calls) == 1:
                raise AuthorizationCodeRejected(account.client_id, AuthError('Rejected', code='invalid_grant'))
            registrations.append(account)
            return account

        auth.finish_login.side_effect = finish
        self.window.chatgpt_auth = auth
        dialog = AdvisorDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.show()
        with (patch('ui.ai_advisor.QDesktopServices.openUrl', return_value=True) as browser,
              patch('ui.ai_advisor.information')):
            dialog.login_button.click()
            self.wait(lambda: dialog.plan_model.count() == 1 and not dialog.auth_running)
        self.assertEqual(browser.call_count, 2)
        self.assertEqual(auth.prepare_login.call_args_list[1].args, (account.client_id,))
        self.assertTrue(dialog.selected_account().signed_in)
        self.assertEqual(dialog.plan_model.currentData(), 'vision')
        self.assertFalse(self.window.busy)

    def test_chatgpt_rejected_code_stops_after_one_automatic_retry_and_shows_error(self):
        from core.chatgpt_auth import AuthError, AuthorizationCodeRejected
        from ui.ai_advisor import AdvisorDialog

        self.populate()
        auth = Mock()
        auth.accounts.return_value = ([], '')
        attempt = Mock()
        attempt.url = 'https://auth.openai.com/api/accounts/authorize?state=unit-error'
        auth.prepare_login.return_value = attempt
        auth.finish_login.side_effect = AuthorizationCodeRejected('oaiapp_retry', AuthError('Rejected', code='invalid_grant'))
        self.window.chatgpt_auth = auth
        dialog = AdvisorDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.show()
        with (patch('ui.ai_advisor.QDesktopServices.openUrl', return_value=True) as browser,
              patch('ui.ai_advisor.information') as message):
            dialog.login_button.click()
            self.wait(lambda: message.called and not dialog.auth_running)
        self.assertEqual(browser.call_count, 2)
        self.assertEqual(auth.finish_login.call_count, 2)
        self.assertIn('invalid_grant', message.call_args.args[2])
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertFalse(self.window.busy)

    def test_backup_and_restore_selection_ui(self):
        from core.backup import read_backup
        from PySide6.QtWidgets import QDialog

        self.populate()
        window = self.window
        window.project.update('01.jpg', category_ids=('album',), stars=5, note='Ghi chú ban đầu')
        window.mark_dirty()
        with (patch('ui.backups.QDialog.exec', return_value=QDialog.DialogCode.Accepted),
              patch('ui.backups.choose_path', return_value=str(self.base)),
              patch('ui.backups.information') as message):
            window.backups.backup()
            self.wait(lambda: message.called)
        archive = next(self.base.glob('Sao-luu-*.zip'))
        self.assertEqual(read_backup(archive).project.photo('01.jpg').stars, 5)
        window.project.update('01.jpg', stars=1, note='Đã sửa')
        window.mark_dirty()
        with (patch('ui.backups.QDialog.exec', return_value=QDialog.DialogCode.Accepted),
              patch('ui.backups.choose_path', return_value=str(archive)),
              patch('ui.backups.confirm', return_value=True),
              patch('ui.backups.information') as message):
            window.backups.restore()
            self.wait(lambda: message.called)
        self.assertEqual(window.project.photo('01.jpg').stars, 5)
        self.assertEqual(window.project.photo('01.jpg').note, 'Ghi chú ban đầu')
        recovery = next(window.backups.recovery_directory.glob('Truoc-khoi-phuc-*.json'))
        self.assertEqual(load_project(recovery).photo('01.jpg').stars, 1)
        self.assertEqual(load_project(self.root / 'photo_tags.json').photo('01.jpg').stars, 5)

    def test_gallery_sort_preserves_selection_folders_filters_and_preferences(self):
        (self.root / 'Thư mục con').mkdir()
        Image.new('RGB', (90, 60)).save(self.root / 'Thư mục con' / 'nested.jpg')
        for path in ('a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'):
            Image.new('RGB', (90, 60)).save(self.root / path)
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 5)
        for path, score, stars in [('a.jpg', 0, 2), ('b.jpg', 80, 5), ('c.jpg', 80, 0), ('d.jpg', None, 0)]:
            window.project.update(path, category_ids=('album',), ai_score=score, stars=stars, favorite=path == 'b.jpg')
        window.photos_changed(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])
        self.select(2)  # b.jpg, sau thẻ thư mục và a.jpg.

        def order(tab=0):
            return [entry.relative for entry in window.galleries[tab].gallery_model.entries]

        window.sort_controls[0].setCurrentIndex(window.sort_controls[0].findData('score_desc'))
        self.assertEqual(order(), ['Thư mục con', 'b.jpg', 'c.jpg', 'a.jpg', 'd.jpg'])
        self.assertEqual(window.selected_paths(), ['b.jpg'])
        self.assertEqual(window.sort_controls[1].currentData(), 'score_desc')
        window.change_sort('score_asc')
        self.assertEqual(order(), ['Thư mục con', 'a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])
        window.change_sort('stars_desc')
        self.assertEqual(order(), ['Thư mục con', 'b.jpg', 'a.jpg', 'c.jpg', 'd.jpg'])
        window.set_stars(1)
        self.assertEqual(order(), ['Thư mục con', 'a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])
        self.assertEqual(window.selected_paths(), ['b.jpg'])
        window.change_sort('stars_asc')
        self.assertEqual(order(), ['Thư mục con', 'b.jpg', 'a.jpg', 'c.jpg', 'd.jpg'])
        window.change_sort('name_desc')
        self.assertEqual(order(), ['Thư mục con', 'd.jpg', 'c.jpg', 'b.jpg', 'a.jpg'])
        window.tabs.setCurrentIndex(1)
        self.assertEqual(order(1), ['d.jpg', 'c.jpg', 'b.jpg', 'a.jpg'])
        window.stacks[1][2].setChecked(True)
        window.sort_actions['score_desc'].trigger()
        self.assertEqual(order(1), ['b.jpg'])
        window.stacks[1][2].setChecked(False)
        self.assertEqual(order(1), ['b.jpg', 'c.jpg', 'a.jpg', 'd.jpg'])
        window.settings.sync()
        self.assertTrue(window.flush_save())
        reopened = self.create_window('settings')
        self.assertEqual(reopened.gallery_sort, 'score_desc')
        self.assertTrue(window.close())
        reopened.open_root(self.root)
        self.wait(lambda: not reopened.scanning)
        self.assertEqual([entry.relative for entry in reopened.galleries[0].gallery_model.entries],
                         ['Thư mục con', 'b.jpg', 'c.jpg', 'a.jpg', 'd.jpg'])
        self.assertEqual(reopened.project.photo('a.jpg').ai_score, 0)

    def test_per_image_score_keeps_same_names_in_different_folders_separate(self):
        for folder in ('A', 'B'):
            (self.root / folder).mkdir()
            Image.new('RGB', (90, 60)).save(self.root / folder / 'same.jpg')
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 2)
        for path, score in [('A/same.jpg', 30), ('B/same.jpg', 80)]:
            window.project.update(path, ai_score=score, category_ids=('album',))
        window.photos_changed(['A/same.jpg', 'B/same.jpg'])
        window.change_sort('score_desc')
        gallery = self.select(0, tab=1)
        self.assertEqual(window.selected_paths(), ['B/same.jpg'])
        self.assertEqual(window.score_input.value(), 80)
        window.score_input.setValue(10)
        self.assertEqual([entry.relative for entry in gallery.gallery_model.entries], ['A/same.jpg', 'B/same.jpg'])
        self.assertEqual(window.selected_paths(), ['B/same.jpg'])
        self.assertEqual(window.project.photo('A/same.jpg').ai_score, 30)
        self.assertEqual(window.project.photo('B/same.jpg').ai_score, 10)
        window.score_input.setValue(0)
        self.assertEqual(window.project.photo('B/same.jpg').ai_score, 0)
        window.score_input.setValue(-1)
        self.assertIsNone(window.project.photo('B/same.jpg').ai_score)
        self.assertEqual(window.project.photo('B/same.jpg').category_ids, ('album',))
        self.select(0, 1, tab=1)
        self.assertFalse(window.score_input.isEnabled())
        self.assertTrue(window.flush_save())
        saved = load_project(self.root / 'photo_tags.json')
        self.assertEqual(saved.photo('A/same.jpg').ai_score, 30)
        self.assertIsNone(saved.photo('B/same.jpg').ai_score)
        self.assertNotIn('ChatGPT', window.ai_button.text())
        self.assertTrue(all('ChatGPT' not in control.itemText(control.findData('score_desc'))
                            for control in window.sort_controls))

    def test_open_project_cleans_legacy_note_prefix_without_changing_score(self):
        from core.data_store import Project, save_project

        Image.new('RGB', (90, 60)).save(self.root / 'a.jpg')
        project = Project()
        project.update('a.jpg', note='Ghi chú cũ\n[ChatGPT] Tăng sáng', ai_score=65, stars=4)
        timestamp = project.photo('a.jpg').updated_at
        save_project(self.root / 'photo_tags.json', project)
        self.window.open_root(self.root)
        self.wait(lambda: not self.window.scanning)
        self.assertEqual(self.window.project.photo('a.jpg').note, 'Ghi chú cũ\nTăng sáng')
        self.assertTrue(self.window.flush_save())
        saved = load_project(self.root / 'photo_tags.json')
        self.assertFalse(saved.needs_save)
        self.assertEqual(saved.photo('a.jpg').ai_score, 65)
        self.assertEqual(saved.photo('a.jpg').stars, 4)
        self.assertEqual(saved.photo('a.jpg').updated_at, timestamp)

    def test_chatgpt_result_sort_keeps_checks_preview_and_apply_attached_to_photo(self):
        from core.ai_advisor import CollectionReview, Recommendation, Review
        from ui.ai_advisor import AdvisorDialog

        for path in ('a.jpg', 'b.jpg', 'c.jpg'):
            Image.new('RGB', (90, 60)).save(self.root / path)
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 3)
        for path, stars in [('a.jpg', 1), ('b.jpg', 5), ('c.jpg', 3)]:
            window.project.update(path, stars=stars)
        window.photos_changed(['a.jpg', 'b.jpg', 'c.jpg'])
        dialog = AdvisorDialog(window)
        self.addCleanup(dialog.close)
        dialog.show()
        result = CollectionReview(Review('Đánh giá', (
            Recommendation('a.jpg', 9, 'A', ''), Recommendation('b.jpg', 80, 'B', ''),
            Recommendation('c.jpg', 100, 'C', ''),
        )), 3, 3)
        dialog.finished(result, None)
        self.assertEqual([item.path for item in dialog.recommendations], ['c.jpg', 'b.jpg', 'a.jpg'])
        saved = load_project(self.root / 'photo_tags.json')
        self.assertEqual(saved.photo('c.jpg').ai_score, 100)
        self.assertEqual(saved.photo('c.jpg').stars, 3)
        self.assertEqual(window.total, 0)
        dialog.top_count.setValue(1)
        dialog.select_top()
        dialog.result_sort.setCurrentIndex(dialog.result_sort.findData('stars_desc'))
        self.assertEqual([item.path for item in dialog.recommendations], ['b.jpg', 'c.jpg', 'a.jpg'])
        self.assertEqual([item.path for item in dialog.selected_recommendations()], ['c.jpg'])
        dialog.table.setCurrentCell(0, 1)  # b.jpg.
        dialog.result_sort.setCurrentIndex(dialog.result_sort.findData('score_asc'))
        self.assertEqual([item.score for item in dialog.recommendations], [9, 80, 100])
        self.assertEqual(dialog.table.item(dialog.table.currentRow(), 1).text(), 'b.jpg')
        dialog.select_top()
        self.assertEqual([item.path for item in dialog.selected_recommendations()], ['c.jpg'])
        with patch('ui.ai_advisor.ViewerDialog') as viewer:
            dialog.preview_photo()
        entries, index = viewer.call_args.args[1:]
        self.assertEqual(entries[index].relative, 'b.jpg')
        dialog.clear_selection()
        dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
        dialog.header_sort(5)
        self.assertEqual(dialog.result_sort.currentData(), 'stars_desc')
        self.assertEqual([item.path for item in dialog.selected_recommendations()], ['b.jpg'])
        dialog.stars.setChecked(True)
        dialog.apply()
        self.assertTrue(window.project.photo('b.jpg').favorite)
        self.assertFalse(window.project.photo('a.jpg').favorite)
        self.assertFalse(window.project.photo('c.jpg').favorite)
        self.assertEqual(window.project.photo('b.jpg').stars, 4)
        self.assertEqual(dialog.table.item(0, 5).text(), '4')

    def test_wedding_workflow(self):
        self.populate()
        window = self.window
        view = self.select(0, 1)
        with patch('ui.window.confirm', side_effect=[False, True]) as approve:
            QTest.keyClick(view, Qt.Key.Key_1)
            self.assertEqual(window.total, 0)
            QTest.keyClick(view, Qt.Key.Key_1)
            self.assertEqual(window.total, 2)
            self.assertEqual(approve.call_count, 2)

        view = self.select(0)
        QTest.keyClick(view, Qt.Key.Key_3, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(view, Qt.Key.Key_F)
        self.assertEqual(window.project.photo('01.jpg').stars, 3)
        self.assertTrue(window.project.photo('01.jpg').favorite)
        window.hints[0].click()
        QTest.keyClicks(window.note, ' F1')
        self.assertEqual(window.project.photo('01.jpg').note, 'Làm thon mặt F1')
        self.assertEqual(window.total, 2)
        self.assertTrue(window.flush_save())

        comparison = ViewerDialog(window, window.entries[:2], compare=True)
        comparison.show()
        self.wait(lambda: all(not panel.canvas.pixmap.isNull() for panel in comparison.panels))
        comparison.panels[0].canvas.change_zoom(2)
        self.assertTrue(all(panel.canvas.zoom == 2 for panel in comparison.panels))
        comparison.close()

        destination = self.base / 'Gói gửi'
        destination.mkdir()
        window.tabs.setCurrentIndex(1)
        window.search.setText('01')
        self.assertEqual(window.galleries[1].gallery_model.rowCount(), 1)
        with (patch('ui.transfers.choose_path', return_value=str(destination)),
              patch('ui.transfers.ExportDialog.exec', return_value=1),
              patch.object(window.transfers, 'export_finished') as finished):
            window.export_button.click()
            self.wait(lambda: finished.called)
        folder, archive = finished.call_args.args[0]
        saved = load_project(folder / 'photo_tags.json')
        self.assertEqual(set(saved.photos), {'01.jpg', '02.jpg'})
        self.assertTrue(archive.is_file())
        view = self.select(0, tab=1)
        QTest.keyClick(view, Qt.Key.Key_Delete)
        self.assertEqual(window.total, 1)
        self.assertEqual(window.project.photo('01.jpg').stars, 3)
        self.assertTrue(window.flush_save())
        self.assertTrue(window.close())
        restored = self.create_window('restored')
        restored.open_root(self.root, restoring=True)
        self.wait(lambda: not restored.scanning)
        self.assertEqual(restored.total, 1)
        self.assertIn('Tiếp tục lựa chọn', restored.statusBar().currentMessage())

    def test_locked_and_invalid_project_are_read_only(self):
        self.populate()
        secondary = self.create_window('locked')
        secondary.open_root(self.root)
        self.wait(lambda: not secondary.scanning)
        self.assertTrue(secondary.read_only)
        self.assertFalse(secondary.editable())
        self.assertTrue(secondary.close())
        self.assertTrue(self.window.close())
        invalid = self.root / 'photo_tags.json'
        invalid.write_bytes(b'invalid json')
        broken = self.create_window('invalid')
        broken.open_root(self.root)
        self.wait(lambda: not broken.scanning)
        self.assertIn('photo_tags.json', broken.read_only)
        self.assertEqual(invalid.read_bytes(), b'invalid json')

    def test_large_folder_keeps_painting_and_discards_old_work(self):
        source = self.base / 'source.jpg'
        Image.new('RGB', (96, 64), '#cca897').save(source)
        jpeg = source.read_bytes()
        for i in range(5000):
            (self.root / f'Ảnh {i:04}.JPG').write_bytes(jpeg)
        ticks = []
        timer = QTimer(self.window, interval=15)
        timer.timeout.connect(lambda: ticks.append(monotonic()))
        timer.start()
        self.addCleanup(timer.stop)
        self.window.open_root(self.root)
        self.wait(lambda: len(self.window.entries) == 5000)
        view = self.window.galleries[0]
        self.wait(lambda: self.window.thumbnails.done_count > 0)
        before_scroll = len(ticks)
        for columns in (3, 4, 5, 6, 10):
            self.window.columns.setCurrentIndex(self.window.columns.findData(columns))
            self.wait(lambda: self.row_wraps_at(view, columns))
        self.window.resize(960, 650)
        self.wait(lambda: self.row_wraps_at(view, 10) and self.window.thumbnails.size == view.thumbnail_size())
        view.scrollToBottom()
        self.wait(lambda: self.window.thumbnails.done_count > 0)
        self.assertGreater(len(ticks), before_scroll)
        other = self.base / 'Ảnh thay thế'
        other.mkdir()
        (other / 'Khác.JPG').write_bytes(jpeg)
        view.scrollToTop()
        self.window.open_root(other)
        self.wait(lambda: self.window.thumbnails.done_count > 0 and len(self.window.entries) == 1)
        self.assertEqual(set(self.window.thumbnails.images), {'Khác.JPG'})

    @staticmethod
    def row_wraps_at(view, columns):
        model = view.gallery_model
        first, last, next_row = [view.visualRect(model.index(row, 0)) for row in (0, columns - 1, columns)]
        return first.isValid() and first.top() == last.top() and first.top() < next_row.top()

    def test_folders_open_by_click_and_selection_stays_global(self):
        folder = self.root / 'Lễ cưới'
        nested = folder / 'Buổi sáng'
        nested.mkdir(parents=True)
        (self.root / 'Thư mục rỗng').mkdir()
        for path in (self.root / '01.jpg', folder / '02.jpg', nested / '03.jpg'):
            Image.new('RGB', (120, 90)).save(path)
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 3)
        gallery = window.galleries[0]
        model = gallery.gallery_model
        self.assertEqual([entry.relative for entry in model.entries], ['Lễ cưới', 'Thư mục rỗng', '01.jpg'])

        self.wait(lambda: gallery.visualRect(model.index(0, 0)).isValid())
        QTest.mouseClick(gallery.viewport(), Qt.MouseButton.LeftButton,
                         pos=gallery.visualRect(model.index(0, 0)).center())
        self.assertEqual(window.active_folder, 'Lễ cưới')
        self.assertEqual([entry.relative for entry in model.entries], ['Lễ cưới/Buổi sáng', 'Lễ cưới/02.jpg'])
        self.assertFalse(window.selected_paths())
        gallery.setFocus()
        gallery.selectionModel().setCurrentIndex(model.index(0, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        QTest.keyClick(gallery, Qt.Key.Key_Return)
        self.assertEqual(window.active_folder, 'Lễ cưới/Buổi sáng')
        self.assertEqual(model.index(0, 0).data(ENTRY).relative, 'Lễ cưới/Buổi sáng/03.jpg')
        window.toggle_category('album', ['Lễ cưới/Buổi sáng/03.jpg'])
        window.folder_up.click()
        window.folder_up.click()
        self.assertEqual(window.active_folder, '')
        self.assertIn('01.jpg', model.rows)
        self.assertEqual(window.total, 1)
        window.tabs.setCurrentIndex(1)
        self.assertEqual(list(window.galleries[1].gallery_model.rows), ['Lễ cưới/Buổi sáng/03.jpg'])
        self.assertIn('Lễ cưới/Buổi sáng/03.jpg', window.snapshot().photos)

    def test_focus_enlarges_gallery_and_preserves_view_preferences(self):
        for filename in ('01.jpg', '02.jpg'):
            Image.new('RGB', (120, 90)).save(self.root / filename)
        window = self.window
        window.open_root(self.root)
        self.wait(lambda: len(window.entries) == 2)
        gallery = self.select(0)
        window.toggle_category('album', ['01.jpg'])
        window.toggle_favorite()
        window.stacks[0][2].setChecked(True)
        window.view_actions['quota'].setChecked(False)
        window.view_actions['path'].setChecked(True)
        self.app.processEvents()
        original = gallery.viewport().size()

        QTest.keyClick(gallery, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(window.focus_mode.isChecked())
        self.wait(lambda: gallery.viewport().width() > original.width() and gallery.viewport().height() > original.height())
        self.assertTrue(window.toolbar.isHidden())
        self.assertTrue(window.inspector.isHidden())
        self.assertTrue(window.filter_rows[0].isHidden())
        self.assertTrue(window.statusBar().isHidden())
        self.assertTrue(window.export_action.isEnabled())
        self.assertTrue(window.clear_filters_buttons[0].isVisible())
        self.assertEqual(gallery.gallery_model.rowCount(), 1)
        window.column_actions[6].trigger()
        self.assertEqual(gallery.columns, 6)
        window.clear_filters_buttons[0].click()
        self.assertEqual(gallery.gallery_model.rowCount(), 2)
        self.assertTrue(window.clear_filters_buttons[0].isHidden())

        window.set_busy('Đang thử…', 2)
        self.assertTrue(window.statusBar().isVisible())
        window.set_busy('')
        self.assertTrue(window.statusBar().isHidden())
        window.focus_mode.trigger()
        self.assertTrue(window.inspector.isVisible())
        self.assertTrue(window.quota.isHidden())
        self.assertTrue(window.path.isVisible())
        window.settings.sync()
        reopened = self.create_window('settings')
        self.assertTrue(reopened.quota.isHidden())
        self.assertTrue(reopened.path.isVisible())
        self.assertEqual(reopened.columns.currentData(), 6)
