import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from zipfile import ZIP_STORED, ZipFile

from PIL import Image

from core.ai_advisor import (
    AdvisorError, Recommendation, Review, analyze_collection, analyze_photos,
    apply_recommendations, parse_review,
)
from core.backup import create_backup, read_backup, restore_images, restore_selection
from core.data_store import Project, load_project, project_payload, save_project
from core.scanner import scan


def response_for(items):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'summary': 'Ảnh phù hợp album', 'photos': items})}
    ]}]}


def result_item(number, score=90):
    return {'id': number, 'score': score, 'reason': 'Ánh sáng tốt', 'editing_note': 'Tăng sáng nhẹ'}


class AdvisorTest(TestCase):
    def test_request_sends_stripped_previews_and_validates_response(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'Tên riêng.jpg'
            exif = Image.Exif()
            exif[270] = 'Private metadata'
            exif[274] = 6
            Image.new('RGB', (1600, 800), '#ffeeaa').save(path, exif=exif)
            original = path.read_bytes()
            raw = json.dumps(response_for([result_item(1)])).encode()
            with patch('core.ai_advisor.urlopen', return_value=io.BytesIO(raw)) as send:
                review = analyze_photos(root, [path.name], 'test-key', criteria='Nụ cười tự nhiên')
            request = send.call_args.args[0]
            payload = json.loads(request.data)
            self.assertFalse(payload['store'])
            self.assertTrue(payload['text']['format']['strict'])
            self.assertNotIn(path.name, request.data.decode())
            self.assertNotIn('test-key', request.data.decode())
            encoded = payload['input'][0]['content'][2]['image_url'].split(',', 1)[1]
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
                self.assertEqual(image.size, (640, 1280))
                self.assertFalse(image.getexif())
            self.assertEqual(review.photos[0].path, path.name)
            self.assertEqual(path.read_bytes(), original)

    def test_refusal_incomplete_invalid_ids_and_api_errors(self):
        for response in (
            {'status': 'incomplete'},
            {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
            response_for([result_item(1), result_item(1)]),
            response_for([result_item(3), result_item(2)]),
            response_for([result_item(1, 101), result_item(2)]),
            response_for([result_item(True), result_item(2)]),
        ):
            with self.subTest(response=response), self.assertRaises(AdvisorError):
                parse_review(response, ['a.jpg', 'b.jpg'])
        with (patch('core.ai_advisor.image_data_url', return_value='data:image/jpeg;base64,eA=='),
              patch('core.ai_advisor.urlopen', side_effect=HTTPError('url', 401, 'SECRET', {}, None))):
            with self.assertRaisesRegex(AdvisorError, 'API key') as error:
                analyze_photos(Path.cwd(), ['a.jpg'], 'secret-key')
            self.assertNotIn('SECRET', str(error.exception))
            self.assertNotIn('secret-key', str(error.exception))
        with (patch('core.ai_advisor.image_data_url', return_value='x'),
              patch('core.ai_advisor.urlopen', side_effect=URLError('offline'))):
            with self.assertRaisesRegex(AdvisorError, 'Không kết nối'):
                analyze_photos(Path.cwd(), ['a.jpg'], 'test-key')

    def test_whole_collection_batches_stop_and_partial_failure(self):
        paths = [f'Folder {i % 3}/{i}.jpg' for i in range(26)]
        cancel = Event()
        sizes, progress = [], []

        def evaluate(root, batch, key, model, criteria):
            sizes.append(len(batch))
            return Review('Đánh giá', tuple(Recommendation(path, 90, 'Tốt', '') for path in batch))

        with patch('core.ai_advisor.analyze_photos', side_effect=evaluate):
            result = analyze_collection(Path.cwd(), paths, 'test', 'model', '', cancel, progress.append)
        self.assertEqual(sizes, [12, 12, 2])
        self.assertEqual(progress, [12, 24, 26])
        self.assertEqual({item.path for item in result.review.photos}, set(paths))
        first = Review('Đánh giá', (Recommendation(paths[0], 90, 'Tốt', ''),))
        with patch('core.ai_advisor.analyze_photos', side_effect=[first, AdvisorError('Hết hạn mức')]):
            result = analyze_collection(Path.cwd(), paths, 'test', 'model', '', Event())
        self.assertEqual(result.review.photos, first.photos)
        self.assertEqual(result.error, 'Hết hạn mức')
        with patch('core.ai_advisor.analyze_photos', side_effect=evaluate) as call:
            result = analyze_collection(Path.cwd(), paths, 'test', 'model', '', cancel, lambda _: cancel.set())
        self.assertEqual(call.call_count, 1)
        self.assertTrue(result.stopped)
        self.assertEqual(result.processed, 12)

    def test_apply_preserves_tags_and_existing_notes(self):
        project = Project()
        project.update('a.jpg', category_ids=('album',), stars=2, note='Giữ màu nền')
        recommendations = [Recommendation('a.jpg', 95, 'Tốt', 'Tăng sáng')]
        self.assertEqual(apply_recommendations(project, recommendations), [])
        apply_recommendations(project, recommendations, stars=True, favorite=True, notes=True)
        photo = project.photo('a.jpg')
        self.assertEqual(photo.category_ids, ('album',))
        self.assertEqual(photo.stars, 5)
        self.assertTrue(photo.favorite)
        self.assertEqual(photo.note, 'Giữ màu nền\nTăng sáng')
        self.assertEqual(apply_recommendations(project, recommendations, stars=True, favorite=True, notes=True), [])

    def test_apply_note_removes_legacy_prefix_and_does_not_duplicate_existing_advice(self):
        project = Project()
        project.update('a.jpg', note='Giữ màu nền\n[ChatGPT] Tăng sáng\nNội dung nhắc [ChatGPT] ở giữa dòng')
        recommendation = [Recommendation('a.jpg', 90, 'Tốt', 'Tăng sáng')]
        apply_recommendations(project, recommendation, notes=True)
        self.assertEqual(project.photo('a.jpg').note,
                         'Giữ màu nền\nTăng sáng\nNội dung nhắc [ChatGPT] ở giữa dòng')
        self.assertEqual(apply_recommendations(project, recommendation, notes=True), [])

    def test_collection_skips_broken_photos_before_network_call(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (50, 50)).save(root / 'good.jpg')
            (root / 'broken.jpg').write_bytes(b'not an image')
            raw = json.dumps(response_for([result_item(1)])).encode()
            with patch('core.ai_advisor.urlopen', return_value=io.BytesIO(raw)) as send:
                result = analyze_collection(root, ['broken.jpg', 'good.jpg'], 'test-key', 'model', '', Event())
            self.assertEqual(send.call_count, 1)
            self.assertEqual(result.processed, 2)
            self.assertEqual(result.skipped, ('broken.jpg',))
            self.assertEqual([item.path for item in result.review.photos], ['good.jpg'])


class BackupTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'Ảnh cưới'
        (self.root / 'Lễ cưới').mkdir(parents=True)
        Image.new('RGB', (80, 60), 'green').save(self.root / 'Lễ cưới' / 'Ảnh 01.jpg')
        self.entries = scan(self.root, True, Event())
        self.project = Project(customer_name='Minh và An')
        self.project.update('Lễ cưới/Ảnh 01.jpg', category_ids=('album',), stars=4, favorite=True, note='Giữ màu', ai_score=91)
        self.project.update('Ảnh tạm vắng.jpg', note='Cần giữ lại')
        save_project(self.root / 'photo_tags.json', self.project)

    def test_full_backup_restore_and_metadata_only_round_trip(self):
        backup = create_backup(self.base, self.project, self.root, self.entries)
        info = read_backup(backup)
        self.assertEqual(info.project, self.project)
        self.assertEqual(info.image_paths, ('Lễ cưới/Ảnh 01.jpg',))
        restored = restore_images(backup, self.base)
        self.assertEqual(load_project(restored / 'photo_tags.json'), self.project)
        self.assertEqual((restored / info.image_paths[0]).read_bytes(), (self.root / info.image_paths[0]).read_bytes())
        metadata = create_backup(self.base, self.project)
        self.assertEqual(read_backup(metadata).project, self.project)
        self.assertFalse(read_backup(metadata).image_paths)
        with self.assertRaises(ValueError):
            restore_images(metadata, self.base)
        self.assertFalse(list(self.base.glob('.restore-*')))
        self.assertEqual(read_backup(self.root / 'photo_tags.json').project, self.project)

    def test_restore_keeps_previous_json_and_failed_replace_keeps_source(self):
        previous = (self.root / 'photo_tags.json').read_bytes()
        replacement = Project(customer_name='Mới')
        recovery = restore_selection(self.root, replacement, self.base / 'recovery')
        self.assertEqual(recovery.read_bytes(), previous)
        self.assertEqual(load_project(self.root / 'photo_tags.json'), replacement)
        before = (self.root / 'photo_tags.json').read_bytes()
        with patch('core.data_store.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                restore_selection(self.root, self.project, self.base / 'recovery')
        self.assertEqual((self.root / 'photo_tags.json').read_bytes(), before)
        (self.root / 'photo_tags.json').write_bytes(b'broken JSON')
        recovery = restore_selection(self.root, self.project, self.base / 'recovery')
        self.assertEqual(recovery.read_bytes(), b'broken JSON')

    def test_unsafe_archives_and_crc_corruption_never_publish(self):
        for name in ('images/../escape.jpg', 'images/C:/evil.jpg', 'images/CON.jpg',
                     'images/A./evil.jpg', 'images/a.jpg/b.jpg', 'unexpected.txt'):
            with self.subTest(name=name):
                path = self.base / 'unsafe.zip'
                with ZipFile(path, 'w') as archive:
                    archive.writestr('photo_tags.json', json.dumps(project_payload(self.project)))
                    archive.writestr('backup.json', json.dumps({'backup_version': 1, 'image_count': 2, 'includes_images': True}))
                    archive.writestr('images/a.jpg', b'x')
                    archive.writestr(name, b'y')
                with self.assertRaises(ValueError):
                    read_backup(path)
        path = self.base / 'bad-crc.zip'
        marker = b'UNIQUE-IMAGE-BYTES-TO-CORRUPT'
        with ZipFile(path, 'w', compression=ZIP_STORED) as archive:
            archive.writestr('photo_tags.json', json.dumps(project_payload(self.project)))
            archive.writestr('backup.json', json.dumps({'backup_version': 1, 'image_count': 1, 'includes_images': True}))
            archive.writestr('images/a.jpg', marker)
        path.write_bytes(path.read_bytes().replace(marker, b'X' * len(marker)))
        with self.assertRaises(ValueError):
            restore_images(path, self.base)
        self.assertFalse(list(self.base.glob('Khoi-phuc-*')))
        self.assertFalse(list(self.base.glob('.restore-*')))

    def test_backup_failure_leaves_no_archive_or_temporary_file(self):
        (self.root / self.entries[0].relative).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            create_backup(self.base, self.project, self.root, self.entries)
        self.assertFalse(list(self.base.glob('Sao-luu-*')))
        self.assertFalse(list(self.base.glob('.backup-*')))
