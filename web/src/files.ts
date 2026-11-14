import { unzip, zip, strToU8, strFromU8, type Zippable } from 'fflate';
import { isPhoto, relativeKey, parseProject, type Project, type Album, type Entry } from './model';
import { imageBlob } from './images';

export const MAX_ARCHIVE = 256 * 1024 * 1024;
const MAX_METADATA = 16 * 1024 * 1024;
export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
export const jsonBlob = (value: unknown) =>
  new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' });
export const makeZip = (files: Zippable) =>
  new Promise<Blob>((resolve, reject) =>
    zip(files, { level: 6 }, (error, data) =>
      error
        ? reject(error)
        : resolve(new Blob([new Uint8Array(data)], { type: 'application/zip' })),
    ),
  );
const decodeJSON = (bytes: Uint8Array) => JSON.parse(strFromU8(bytes).replace(/^\uFEFF/, ''));
export interface Backup {
  project: Project;
  images: Map<string, Blob>;
}
function safeImagePath(path: string) {
  if (
    relativeKey(path) !== path ||
    !isPhoto(path) ||
    path
      .split('/')
      .some((p) => /[ .]$/.test(p) || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(p))
  )
    throw new Error('Đường dẫn ảnh trong ZIP không hợp lệ.');
}
// Inspect the central directory before allocating decompressed data; reject zip bombs,
// duplicate paths, symlinks and ZIP64 instead of silently losing desktop paths.
export function inspectZip(bytes: Uint8Array) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--)
    if (
      view.getUint32(i, true) === 0x06054b50 &&
      i + 22 + view.getUint16(i + 20, true) === bytes.length
    ) {
      end = i;
      break;
    }
  if (end < 0) throw new Error('ZIP không hợp lệ.');
  const count = view.getUint16(end + 10, true);
  let offset = view.getUint32(end + 16, true),
    total = 0;
  if (
    count === 65535 ||
    offset === 0xffffffff ||
    view.getUint16(end + 4, true) !== 0 ||
    view.getUint16(end + 6, true) !== 0
  )
    throw new Error('ZIP64 hoặc ZIP nhiều phần chưa được hỗ trợ. Chia thành bản backup nhỏ hơn.');
  const names = new Set<string>();
  const records = new Map<string, { size: number; crc: number }>();
  for (let i = 0; i < count; i++) {
    if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50)
      throw new Error('Mục lục ZIP bị hỏng.');
    const size = view.getUint32(offset + 24, true),
      length = view.getUint16(offset + 28, true),
      extra = view.getUint16(offset + 30, true),
      comment = view.getUint16(offset + 32, true);
    const name = strFromU8(bytes.subarray(offset + 46, offset + 46 + length));
    const mode = view.getUint32(offset + 38, true) >>> 16;
    if (
      names.has(name.toLowerCase()) ||
      (mode & 0xf000) === 0xa000 ||
      view.getUint16(offset + 8, true) & 1
    )
      throw new Error('ZIP chứa tệp trùng, liên kết hoặc mã hóa.');
    names.add(name.toLowerCase());
    records.set(name, { size, crc: view.getUint32(offset + 16, true) });
    if (name === 'photo_tags.json' || name === 'backup.json') {
      if (size > MAX_METADATA) throw new Error('JSON trong ZIP vượt 16 MB.');
    } else if (name.startsWith('images/')) safeImagePath(name.slice(7));
    else throw new Error('ZIP chứa mục không thuộc định dạng backup của ứng dụng.');
    total += size;
    if (total > MAX_ARCHIVE)
      throw new Error(
        'Backup giải nén vượt 256 MB. Trên web hãy dùng backup dữ liệu và mở ảnh từ Drive.',
      );
    offset += 46 + length + extra + comment;
  }
  if (!names.has('photo_tags.json')) throw new Error('ZIP thiếu photo_tags.json.');
  for (const name of names) {
    const parts = name.split('/');
    for (let index = 1; index < parts.length; index++)
      if (names.has(parts.slice(0, index).join('/')))
        throw new Error('Đường dẫn ảnh trong ZIP xung đột.');
  }
  return records;
}
const crcTable = Uint32Array.from({ length: 256 }, (_, number) => {
  let c = number;
  for (let i = 0; i < 8; i++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(bytes: Uint8Array) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}
export async function readBackup(file: File): Promise<Backup> {
  if (file.size > MAX_ARCHIVE)
    throw new Error(
      'Backup web tối đa 256 MB. Hãy dùng JSON hoặc backup không kèm ảnh với bộ lớn.',
    );
  if (/\.json$/i.test(file.name)) {
    if (file.size > MAX_METADATA) throw new Error('JSON vượt 16 MB.');
    return {
      project: parseProject(JSON.parse((await file.text()).replace(/^\uFEFF/, ''))),
      images: new Map(),
    };
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  const records = inspectZip(bytes);
  const unpacked = await new Promise<Record<string, Uint8Array>>((resolve, reject) =>
    unzip(bytes, {}, (e, d) => (e ? reject(new Error('Không giải nén được backup.')) : resolve(d))),
  );
  if (Object.keys(unpacked).length !== records.size) throw new Error('Mục lục ZIP không khớp.');
  for (const [name, data] of Object.entries(unpacked)) {
    const record = records.get(name);
    if (!record || data.length !== record.size || crc32(data) !== record.crc)
      throw new Error('Backup bị hỏng hoặc không khớp checksum.');
  }
  const project = parseProject(decodeJSON(unpacked['photo_tags.json']));
  const images = new Map<string, Blob>();
  for (const [name, data] of Object.entries(unpacked))
    if (name.startsWith('images/'))
      images.set(name.slice(7), new Blob([new Uint8Array(data)], { type: mimeType(name) }));
  if (unpacked['backup.json']) {
    const m = decodeJSON(unpacked['backup.json']);
    if (
      m.backup_version !== 1 ||
      !Number.isInteger(m.image_count) ||
      m.image_count !== images.size ||
      typeof m.includes_images !== 'boolean' ||
      (images.size && !m.includes_images)
    )
      throw new Error('Thông tin backup không khớp số ảnh.');
  } else if (images.size) throw new Error('Backup kèm ảnh thiếu backup.json.');
  return { project, images };
}
const mimeType = (path: string) =>
  /\.png$/i.test(path)
    ? 'image/png'
    : /\.webp$/i.test(path)
      ? 'image/webp'
      : /\.gif$/i.test(path)
        ? 'image/gif'
        : /\.tiff?$/i.test(path)
          ? 'image/tiff'
          : /\.bmp$/i.test(path)
            ? 'image/bmp'
            : 'image/jpeg';
export async function createBackup(
  album: Album,
  includeImages: boolean,
  progress: (s: string) => void,
) {
  parseProject(album.project);
  const metadata = strToU8(JSON.stringify(album.project, null, 2));
  if (metadata.length > MAX_METADATA) throw new Error('Dữ liệu lựa chọn vượt giới hạn 16 MB.');
  const files: Zippable = {
    'photo_tags.json': metadata,
    'backup.json': strToU8(
      JSON.stringify({
        backup_version: 1,
        created_at: new Date().toISOString(),
        includes_images: includeImages,
        image_count: includeImages ? album.entries.length : 0,
      }),
    ),
  };
  let size = 0;
  if (includeImages)
    for (const [index, entry] of album.entries.entries()) {
      safeImagePath(entry.path);
      progress(`Đang sao lưu ảnh ${index + 1}/${album.entries.length}`);
      const blob = await imageBlob(album, entry, true);
      size += blob.size;
      if (size > MAX_ARCHIVE)
        throw new Error('Ảnh vượt 256 MB. Dùng backup dữ liệu và giữ ảnh trên Drive.');
      files['images/' + entry.path] = new Uint8Array(await blob.arrayBuffer());
    }
  progress('Đang tạo ZIP…');
  return makeZip(files);
}
function safeFolder(name: string) {
  return (
    name
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, '-')
      .replace(/[ .]+$/g, '')
      .slice(0, 80) || 'Loai-anh'
  );
}
export async function copyByCategory(
  album: Album,
  progress: (s: string) => void,
  raw?: { files: Map<string, File>; matches: Record<string, string> },
) {
  const files: Zippable = {};
  let size = 0;
  const used = new Set<string>();
  for (const category of album.project.categories) {
    let folder = safeFolder(category.name),
      n = 1;
    while (used.has(folder.toLowerCase())) folder = safeFolder(category.name) + '-' + ++n;
    used.add(folder.toLowerCase());
    for (const [path, photo] of Object.entries(album.project.photos)) {
      if (!photo.category_ids.includes(category.id)) continue;
      const entry = album.entries.find((e) => e.path === path),
        rawPath = raw?.matches[path];
      if (raw && !rawPath) continue;
      if (!raw && !entry)
        throw new Error(`Ảnh đang vắng: ${path}. Mở đúng bộ ảnh trước khi sao chép.`);
      progress('Đang lấy ' + path);
      const blob = raw ? raw.files.get(rawPath!)! : await imageBlob(album, entry!, true);
      size += blob.size;
      if (size > MAX_ARCHIVE)
        throw new Error('Gói ảnh vượt 256 MB. Hãy xuất từng loại hoặc dùng app PC cho bộ lớn.');
      files[folder + '/' + (rawPath || path)] = new Uint8Array(await blob.arrayBuffer());
    }
  }
  if (!Object.keys(files).length) throw new Error('Chưa có ảnh phù hợp để sao chép.');
  return makeZip(files);
}
export async function exportStudio(project: Project) {
  const { default: ExcelJS } = await import('exceljs');
  const book = new ExcelJS.Workbook();
  book.creator = 'Chọn ảnh cưới';
  const selected = Object.entries(project.photos)
    .filter(([, p]) => p.category_ids.length)
    .sort(([a], [b]) => a.localeCompare(b, 'vi', { numeric: true }));
  const sheets = [
    { name: 'Tổng hợp', id: '' },
    ...project.categories.map((c) => ({ name: c.name, id: c.id })),
  ];
  const used = new Set<string>();
  for (const spec of sheets) {
    const base = spec.name.replace(/[\[\]:*?/\\]/g, ' ').slice(0, 27) || 'Loại ảnh';
    let name = base,
      n = 1;
    while (used.has(name.toLowerCase())) name = base + ' ' + ++n;
    used.add(name.toLowerCase());
    const sheet = book.addWorksheet(name);
    sheet.columns = [
      { header: 'STT', key: 'n', width: 8 },
      { header: 'Tên ảnh', key: 'file', width: 28 },
      { header: 'Đường dẫn', key: 'path', width: 45 },
      { header: 'Loại ảnh', key: 'tags', width: 34 },
      { header: 'Sao', key: 'stars', width: 8 },
      { header: 'Yêu thích', key: 'favorite', width: 12 },
      { header: 'Điểm', key: 'score', width: 10 },
      { header: 'Ghi chú hậu kỳ', key: 'note', width: 65 },
    ];
    let index = 0;
    for (const [path, p] of selected)
      if (!spec.id || p.category_ids.includes(spec.id))
        sheet.addRow({
          n: ++index,
          file: path.split('/').pop(),
          path,
          tags: project.categories
            .filter((c) => p.category_ids.includes(c.id))
            .map((c) => c.name)
            .join(', '),
          stars: p.stars,
          favorite: p.favorite ? 'Có' : '',
          score: p.ai_score,
          note: p.note,
        });
    sheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
    sheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF183F36' } };
    sheet.views = [{ state: 'frozen', ySplit: 1 }];
    sheet.autoFilter = 'A1:H1';
    sheet.eachRow((row) => {
      row.alignment = { vertical: 'top', wrapText: true };
    });
  }
  const lightroom =
    project.categories
      .map(
        (c) =>
          `${c.name}: ${selected
            .filter(([, p]) => p.category_ids.includes(c.id))
            .map(([path]) =>
              path
                .split('/')
                .pop()!
                .replace(/\.[^.]+$/, ''),
            )
            .join(', ')}`,
      )
      .join('\n') + '\n';
  const excel = await book.xlsx.writeBuffer();
  return makeZip({
    'danh_sach_anh.xlsx': new Uint8Array(excel),
    'lightroom.txt': strToU8(lightroom),
    'photo_tags.json': strToU8(JSON.stringify(project, null, 2)),
  });
}
export function entriesFromFiles(files: FileList | File[]) {
  const input = Array.from(files);
  const blobs = new Map<string, Blob>();
  const entries: Entry[] = [];
  for (const f of input) {
    const raw = f.webkitRelativePath ? f.webkitRelativePath.split('/').slice(1).join('/') : f.name;
    const path = relativeKey(raw);
    if (isPhoto(path)) {
      if (blobs.has(path)) throw new Error('Có tên ảnh trùng. Chọn cả thư mục để giữ đường dẫn.');
      blobs.set(path, f);
      entries.push({ path, name: f.name, size: f.size, mimeType: f.type });
    }
  }
  return { entries, blobs };
}
