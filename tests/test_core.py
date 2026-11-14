from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import load_workbook
from PIL import Image, UnidentifiedImageError

from core.data_store import (
    Photo, Project, category_change, counts, load_project, new_project, parse_project,
    project_payload, reconcile_paths, save_project,
)
from core.exporter import execute_copy, export_package, lightroom_warnings, match_raw, plan_copy
from core.scanner import scan
from core.sorting import photo_sort_key
from core.thumbnail_cache import ThumbnailCache, read_image


class CoreTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'Ảnh cưới thử'
        self.root.mkdir()

    def test_scan_cache_exif_and_broken_image(self):
        (self.root / 'Tiệc tối').mkdir()
        path = self.root / 'Tiệc tối' / 'Ảnh số 1.JPG'
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (240, 120), 'green').save(path, exif=exif)
        (self.root / 'hỏng.png').write_bytes(b'invalid')
        (self.root / 'not-image.txt').write_bytes(b'invalid')
        entries = scan(self.root, True, Event())
        self.assertEqual([entry.relative for entry in entries], ['hỏng.png', 'Tiệc tối/Ảnh số 1.JPG'])
        self.assertEqual(len(scan(self.root, False, Event())), 1)
        preview, resolution = read_image(path, 80)
        self.assertEqual((preview.size, resolution), ((40, 80), (120, 240)))
        cache = ThumbnailCache(self.base / 'cache')
        self.assertEqual(cache.get(self.root, entries[1], 100).size, (50, 100))
        self.assertEqual(cache.get(self.root, entries[1], 100).size, (50, 100))
        self.assertEqual(len(list(cache.directory.glob('*.png'))), 1)
        with self.assertRaises(UnidentifiedImageError):
            cache.get(self.root, entries[0], 100)

    def test_project_configuration_and_atomic_save_failure(self):
        config = self.root / 'goi_chup.json'
        config.write_text('{"customer_name":"Hà và Hưng","limits":{"album":60,"phong_lon":2}}', encoding='utf-8')
        project = new_project(self.root)
        self.assertEqual(project.customer_name, 'Hà và Hưng')
        self.assertEqual(project.categories[0].max_count, 60)
        path = self.root / 'photo_tags.json'
        project.update('Album/Ảnh thử.JPG', category_ids=('album', 'phong_lon'), favorite=True, stars=5,
                       note='Chỉnh sáng')
        save_project(path, project)
        self.assertEqual(load_project(path), project)
        self.assertTrue(project.photo('Album/Ảnh thử.JPG').updated_at.endswith('+00:00'))
        original = path.read_bytes()
        project.update('Album/Ảnh thử.JPG', note='Làm sáng da')
        with patch('core.data_store.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                save_project(path, project)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(list(self.root.glob('*.tmp')))
        path.write_text('{"schema_version":1,"categories":[],"photos":{"../escape.jpg":{}}}', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_project(path)

    def test_missing_records_and_batch_toggle(self):
        project = Project()
        project.update('a.jpg', category_ids=('album',))
        project.update('Thư mục con/b.jpg', note='Ảnh cũ')
        with self.assertLogs('core.data_store', level='WARNING'):
            reconcile_paths(self.root, project, [], False)
        self.assertEqual(project.photo('Thư mục con/b.jpg').note, 'Ảnh cũ')
        self.assertEqual(category_change(project, ['a.jpg', 'c.jpg'], 'album'), (True, ['c.jpg']))
        self.assertEqual(category_change(project, ['a.jpg'], 'album'), (False, ['a.jpg']))
        self.assertEqual(counts(project, ['a.jpg', 'c.jpg'])[0], 1)

    def test_ai_scores_load_old_projects_validate_and_keep_zero_score(self):
        project = Project()
        self.assertTrue(project.update('zero.jpg', ai_score=0))
        self.assertIn('zero.jpg', project.photos)
        path = self.root / 'photo_tags.json'
        save_project(path, project)
        self.assertEqual(load_project(path).photo('zero.jpg').ai_score, 0)
        self.assertEqual(counts(project, ['zero.jpg'])[0], 0)
        old = project_payload(project)
        old['photos']['zero.jpg'].pop('ai_score')
        self.assertIsNone(parse_project(old).photo('zero.jpg').ai_score)
        for value in (True, -1, 101, '90', 4.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                old['photos']['zero.jpg']['ai_score'] = value
                parse_project(old)
        project.update('zero.jpg', ai_score=None)
        self.assertNotIn('zero.jpg', project.photos)

    def test_numeric_sort_keeps_unrated_last_and_breaks_ties_by_name(self):
        photos = {'c.jpg': Photo(ai_score=100, stars=0), 'b.jpg': Photo(ai_score=100, stars=5),
                  'a.jpg': Photo(ai_score=0, stars=2), 'd.jpg': Photo()}

        def order(mode):
            return sorted(photos, key=lambda path: photo_sort_key(path, photos[path], mode))

        self.assertEqual(order('score_desc'), ['b.jpg', 'c.jpg', 'a.jpg', 'd.jpg'])
        self.assertEqual(order('score_asc'), ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])
        self.assertEqual(order('stars_desc'), ['b.jpg', 'a.jpg', 'c.jpg', 'd.jpg'])
        self.assertEqual(order('stars_asc'), ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])

    def test_studio_export_package(self):
        project = Project(customer_name='Ngọc và Minh')
        project.update('A/Ảnh 1.jpg', category_ids=('album', 'phong_lon'), stars=4, note='=1+1')
        project.update('B/Ảnh 1.JPG', category_ids=('album',))
        project.update('ảnh, đôi.png', category_ids=('album',))
        project.update('yêu thích.jpg', favorite=True)
        self.assertEqual(set(lightroom_warnings(project)), {'Ảnh 1', 'ảnh, đôi'})
        folder, archive = export_package(self.base, project, True)
        self.assertEqual(load_project(folder / 'photo_tags.json'), project)
        with ZipFile(archive) as package:
            self.assertEqual(set(package.namelist()), {'photo_tags.json', 'lightroom.txt', 'danh_sach_anh.xlsx'})
        lightroom = (folder / 'lightroom.txt').read_text(encoding='utf-8')
        self.assertIn('Phóng lớn: Ảnh 1\n', lightroom)
        self.assertNotIn('.JPG', lightroom)
        workbook = load_workbook(folder / 'danh_sach_anh.xlsx')
        self.assertEqual(len(workbook.sheetnames), len(project.categories) + 1)
        self.assertEqual(workbook['Tổng hợp']['B1'].value, 'Ngọc và Minh')
        self.assertEqual(workbook['Tổng hợp'].max_row, 6)
        self.assertEqual(workbook['Phóng lớn']['C4'].value, 4)
        self.assertEqual(workbook['Phóng lớn']['D4'].value, '=1+1')
        self.assertEqual(workbook['Phóng lớn']['D4'].data_type, 's')
        workbook.close()

    def test_raw_exact_fallback_ambiguity_and_copy(self):
        project = Project()
        for photo in ('A/match.JPG', 'unique.jpg', 'ambiguous.jpg', 'missing.jpg'):
            project.update(photo, category_ids=('album', 'anh_de_ban'))
        for name in ('A/match.CR3', 'B/match.NEF', 'B/unique.ARW', 'B/ambiguous.CR2', 'C/ambiguous.NEF'):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(name.encode())
        matches, issues = match_raw(self.root, project)
        self.assertEqual(matches, {'A/match.JPG': 'A/match.CR3', 'unique.jpg': 'B/unique.ARW'})
        self.assertEqual(len(issues), 2)
        originals = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        output = self.base / 'Đã chọn'
        output.mkdir()
        with self.assertRaises(ValueError):
            plan_copy(self.root, self.root / 'sub', project, matches)
        items = plan_copy(self.root, output, project, matches)
        progress = []
        self.assertEqual(execute_copy(self.root, output, items, set(), progress.append), (4, 0, []))
        self.assertEqual(progress, [4])
        self.assertEqual(execute_copy(self.root, output, items, set(), progress.append), (0, 4, []))
        items[0].destination.write_bytes(b'older copy')
        confirmed = {items[0].destination}
        self.assertEqual(execute_copy(self.root, output, items, confirmed, progress.append), (1, 3, []))
        for item in items:
            self.assertEqual(item.destination.read_bytes(), originals[item.source])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
