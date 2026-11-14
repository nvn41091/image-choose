import { describe, it, expect } from 'vitest';
import {
  blankProject,
  counts,
  matchRaw,
  packageProject,
  parseProject,
  photoAt,
  relativeKey,
  sortEntries,
  updatePhotos,
} from '../src/model';
import { createBackup, inspectZip, readBackup, exportStudio } from '../src/files';
import { zipSync, strToU8, unzipSync, strFromU8 } from 'fflate';

describe('desktop compatibility', () => {
  it('keeps duplicate filenames by relative path, score zero and absent records', () => {
    let p = blankProject();
    p = updatePhotos(p, ['studio/IMG_1.jpg'], () => ({
      category_ids: ['album'],
      ai_score: 0,
      note: '[ChatGPT] Sáng hơn\nNhắc [ChatGPT] ở giữa',
    }));
    p = updatePhotos(p, ['ngoai-canh/IMG_1.jpg', 'missing.jpg'], () => ({
      stars: 5,
      favorite: true,
    }));
    const restored = parseProject(JSON.parse(JSON.stringify(p)));
    expect(photoAt(restored, 'studio/IMG_1.jpg').ai_score).toBe(0);
    expect(photoAt(restored, 'studio/IMG_1.jpg').note).toBe('Sáng hơn\nNhắc [ChatGPT] ở giữa');
    expect(Object.keys(restored.photos)).toHaveLength(3);
    expect(counts(restored).album).toBe(1);
    expect(photoAt(restored, 'ngoai-canh/IMG_1.jpg').category_ids).toEqual([]);
  });
  it.each(['../a.jpg', '/a.jpg', 'C:\\a.jpg', 'a/../../b.jpg', 'a//b.jpg', 'a\u0000.jpg'])(
    'rejects unsafe relative path %s',
    (path) => expect(() => relativeKey(path)).toThrow(),
  );
  it('accepts backslashes from desktop and rejects duplicate normalized paths', () => {
    const p = updatePhotos(blankProject(), ['sub/a.jpg'], () => ({ favorite: true }));
    p.photos['sub\\a.jpg'] = p.photos['sub/a.jpg'];
    expect(() => parseProject(p)).toThrow();
  });
  it('rejects future schema, duplicate shortcuts, invalid ratings', () => {
    expect(() => parseProject({ ...blankProject(), schema_version: 2 })).toThrow();
    const p = blankProject();
    p.categories[1].shortcut = 1;
    expect(() => parseProject(p)).toThrow();
    expect(() =>
      parseProject(updatePhotos(blankProject(), ['a.jpg'], () => ({ ai_score: 101 }))),
    ).toThrow();
    expect(() =>
      parseProject(updatePhotos(blankProject(), ['a.jpg'], () => ({ stars: 1.5 }))),
    ).toThrow();
  });
  it('initializes package including an exact zero limit', () => {
    const p = packageProject({ customer_name: 'An & Minh', limits: { album: 60, phong_lon: 0 } });
    expect(p.categories[0].max_count).toBe(60);
    expect(p.categories[1].max_count).toBe(0);
    expect(p.categories[2].max_count).toBeNull();
  });
  it('places unrated photos last for either direction and handles zero scores', () => {
    const entries = ['b.jpg', 'a.jpg', 'c.jpg'].map((path) => ({ path, name: path }));
    const p = updatePhotos(
      updatePhotos(blankProject(), ['b.jpg'], () => ({ ai_score: 0, stars: 3 })),
      ['a.jpg'],
      () => ({ ai_score: 50, stars: 5 }),
    );
    expect(sortEntries(entries, p, 'score_asc').map((e) => e.path)).toEqual([
      'b.jpg',
      'a.jpg',
      'c.jpg',
    ]);
    expect(sortEntries(entries, p, 'score_desc').map((e) => e.path)).toEqual([
      'a.jpg',
      'b.jpg',
      'c.jpg',
    ]);
    expect(sortEntries(entries, p, 'stars_asc').map((e) => e.path)).toEqual([
      'b.jpg',
      'a.jpg',
      'c.jpg',
    ]);
  });
  it('matches RAW by full path first, refuses ambiguous names', () => {
    const p = updatePhotos(
      blankProject(),
      ['a/one.jpg', 'b/one.jpg', 'two.jpg', 'lost.jpg'],
      () => ({ category_ids: ['album'] }),
    );
    const result = matchRaw(p, ['a/one.CR3', 'x/one.NEF', 'x/two.ARW']);
    expect(result.matches).toEqual({ 'a/one.jpg': 'a/one.CR3', 'two.jpg': 'x/two.ARW' });
    expect(result.issues).toHaveLength(2);
  });
});
describe('backups and exports', () => {
  it('rejects a damaged ZIP even when its JSON parses', async () => {
    const bytes = zipSync(
      { 'photo_tags.json': strToU8(JSON.stringify(blankProject())) },
      { level: 0 },
    );
    const marker = strToU8('Album');
    let found = false;
    for (let i = 30; i < bytes.length - marker.length; i++) {
      if (marker.every((value, j) => bytes[i + j] === value)) {
        bytes[i] = 'B'.charCodeAt(0);
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
    await expect(readBackup(new File([bytes], 'broken.zip'))).rejects.toThrow('checksum');
  });
  it('imports a desktop ZIP with photos, note and score', async () => {
    const p = updatePhotos(blankProject(), ['Thư mục/a.jpg'], () => ({
      note: 'giữ màu',
      ai_score: 95,
      stars: 4,
      category_ids: ['album'],
    }));
    const bytes = zipSync({
      'photo_tags.json': strToU8(JSON.stringify(p)),
      'backup.json': strToU8(
        JSON.stringify({ backup_version: 1, image_count: 1, includes_images: true }),
      ),
      'images/Thư mục/a.jpg': new Uint8Array([255, 216, 255, 217]),
    });
    const result = await readBackup(new File([bytes], 'desktop.zip'));
    expect(result.project).toEqual(p);
    expect(result.images.size).toBe(1);
  });
  it('exports metadata backup identical to desktop schema', async () => {
    const p = updatePhotos(blankProject(), ['absent.jpg'], () => ({ ai_score: 0 }));
    const blob = await createBackup(
      { id: 'test', source: 'local', name: 'Test', entries: [], project: p, updatedAt: '' },
      false,
      () => {},
    );
    const restored = await readBackup(new File([blob], 'backup.zip'));
    expect(restored.project).toEqual(p);
    expect(restored.images.size).toBe(0);
  });
  it('rejects zip traversal, unsupported entries and manifest mismatch', async () => {
    const meta = strToU8(JSON.stringify(blankProject()));
    expect(() =>
      inspectZip(zipSync({ 'photo_tags.json': meta, 'images/../evil.jpg': new Uint8Array() })),
    ).toThrow();
    expect(() =>
      inspectZip(zipSync({ 'photo_tags.json': meta, 'evil.exe': new Uint8Array() })),
    ).toThrow();
    const wrong = zipSync({
      'photo_tags.json': meta,
      'backup.json': strToU8(
        JSON.stringify({ backup_version: 1, image_count: 3, includes_images: true }),
      ),
    });
    await expect(readBackup(new File([wrong], 'backup.zip'))).rejects.toThrow();
  });
  it('rejects a zip bomb before decompression', () => {
    const bytes = zipSync({ 'photo_tags.json': strToU8(JSON.stringify(blankProject())) });
    const view = new DataView(bytes.buffer);
    let offset = 0;
    while (view.getUint32(offset, true) !== 0x02014b50) offset++;
    view.setUint32(offset + 24, 300 * 1024 * 1024, true);
    expect(() => inspectZip(bytes)).toThrow();
  });
  it('creates Excel, Lightroom and JSON including selected photos hidden from gallery', async () => {
    const p = updatePhotos(blankProject(), ['sub/a.jpg', 'hidden/b.jpg'], () => ({
      category_ids: ['album'],
      stars: 4,
      note: '=1+1',
    }));
    const output = unzipSync(new Uint8Array(await (await exportStudio(p)).arrayBuffer()));
    expect(Object.keys(output).sort()).toEqual([
      'danh_sach_anh.xlsx',
      'lightroom.txt',
      'photo_tags.json',
    ]);
    expect(strFromU8(output['lightroom.txt'])).toContain('Album: b, a');
    const { default: ExcelJS } = await import('exceljs');
    const book = new ExcelJS.Workbook();
    await book.xlsx.load(output['danh_sach_anh.xlsx'] as never);
    expect(book.worksheets[0].rowCount).toBe(3);
    expect(book.worksheets[0].getCell('H2').value).toBe('=1+1');
  });
});
