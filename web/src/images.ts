import { getBlob, putBlob } from './storage';
import { driveBlob } from './drive';
import type { Album, Entry } from './model';

const pending = new Map<string, Promise<Blob>>();
export async function imageBlob(album: Album, entry: Entry, full = false): Promise<Blob> {
  const original = await getBlob(album.id, entry.path);
  if (original) return original;
  if (album.source !== 'drive')
    throw new Error('Ảnh chưa có trên thiết bị. Nhập backup kèm ảnh hoặc mở lại thư mục nguồn.');
  const cachePath = '@preview/' + entry.path;
  if (!full) {
    const cached = await getBlob(album.id, cachePath);
    if (cached) return cached;
  }
  const key = album.id + '/' + entry.path + '/' + full;
  if (pending.has(key)) return pending.get(key)!;
  const work = (async () => {
    const original = await driveBlob(entry);
    if (full) return original;
    const preview = await resizeImage(original, 640, 'image/webp', 0.8);
    try {
      await putBlob(album.id, cachePath, preview);
    } catch {
      /* Cache failure must not prevent viewing. */
    }
    return preview;
  })();
  pending.set(key, work);
  try {
    return await work;
  } finally {
    pending.delete(key);
  }
}
export async function resizeImage(
  blob: Blob,
  max: number,
  type = 'image/jpeg',
  quality = 0.85,
): Promise<Blob> {
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error('Không tạo được ảnh xem trước.'))),
        type,
        quality,
      ),
    );
  } catch {
    throw new Error(
      'Trình duyệt không đọc được ảnh này. Dùng JPG/PNG/WebP thay TIFF hoặc kiểm tra ảnh nguồn.',
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}
export const blobDataUrl = (blob: Blob) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Không đọc được ảnh.'));
    reader.readAsDataURL(blob);
  });
