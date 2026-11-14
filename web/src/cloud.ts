import { initializeApp, getApps } from 'firebase/app';
import { GoogleAuthProvider, getAuth, signInWithPopup, signOut, type User } from 'firebase/auth';
import {
  collection,
  doc,
  getDoc,
  getDocs,
  getFirestore,
  runTransaction,
  serverTimestamp,
} from 'firebase/firestore';
import { getFunctions, httpsCallable } from 'firebase/functions';
import { gzipSync, gunzipSync, strToU8, strFromU8 } from 'fflate';
import { getConfig } from './config';
import { parseProject, relativeKey, type Album } from './model';

function app() {
  const config = getConfig();
  if (!config.firebaseConfig.trim())
    throw new Error('Chưa cấu hình Firebase. Bạn vẫn có thể dùng backup và lưu trên thiết bị.');
  return getApps()[0] || initializeApp(JSON.parse(config.firebaseConfig));
}
export function cloudUser(): User | null {
  return getAuth(app()).currentUser;
}
export function cloudLogin() {
  return signInWithPopup(getAuth(app()), new GoogleAuthProvider());
}
export function cloudLogout() {
  return signOut(getAuth(app()));
}
export async function cloudReady() {
  await getAuth(app()).authStateReady();
  return cloudUser();
}
export interface CloudEntry {
  id: string;
  name: string;
  updatedAt: string;
  revision: number;
}
export async function listCloudAlbums(): Promise<CloudEntry[]> {
  const user = cloudUser();
  if (!user) throw new Error('Đăng nhập đồng bộ bằng Google trước.');
  return (await getDocs(collection(getFirestore(app()), 'users', user.uid, 'albums'))).docs.map(
    (d) => ({ id: d.id, ...d.data() }) as CloudEntry,
  );
}
function encode(album: Album) {
  // Only metadata and Drive references are synced. No image bytes or OAuth tokens.
  const bytes = gzipSync(
    strToU8(JSON.stringify({ ...album, cloudRevision: undefined, cloudUid: undefined })),
  );
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  const data = btoa(binary);
  if (data.length > 900000)
    throw new Error('Dữ liệu album quá lớn cho đồng bộ. Hãy tải backup JSON.');
  return data;
}
export async function pushCloud(album: Album): Promise<Album> {
  const user = cloudUser();
  if (!user) throw new Error('Đăng nhập đồng bộ bằng Google trước.');
  const payload = encode(album),
    ref = doc(getFirestore(app()), 'users', user.uid, 'albums', album.id);
  const revision = await runTransaction(getFirestore(app()), async (tx) => {
    const current = await tx.get(ref);
    const latest = current.exists() ? current.data().revision : 0;
    const expected = album.cloudUid === user.uid ? album.cloudRevision || 0 : 0;
    if (latest !== expected)
      throw new Error(
        'Bản trên Firebase đã thay đổi. Tải bản cloud về trước để tránh ghi đè lựa chọn từ thiết bị khác.',
      );
    tx.set(ref, {
      name: album.name,
      payload,
      revision: latest + 1,
      updatedAt: new Date().toISOString(),
      savedAt: serverTimestamp(),
    });
    return latest + 1;
  });
  return { ...album, cloudRevision: revision, cloudUid: user.uid };
}
export async function pullCloud(id: string): Promise<Album> {
  const user = cloudUser();
  if (!user) throw new Error('Đăng nhập đồng bộ trước.');
  const result = await getDoc(doc(getFirestore(app()), 'users', user.uid, 'albums', id));
  if (!result.exists()) throw new Error('Không tìm thấy album trên Firebase.');
  const data = result.data(),
    bytes = Uint8Array.from(atob(data.payload), (c) => c.charCodeAt(0));
  // Bound decompression before gunzip to avoid oversized data in a browser.
  const declared = new DataView(bytes.buffer).getUint32(bytes.length - 4, true);
  if (declared > 16 * 1024 * 1024) throw new Error('Dữ liệu cloud vượt giới hạn 16 MB.');
  const album = JSON.parse(strFromU8(gunzipSync(bytes))) as Album;
  if (
    album.id !== id ||
    typeof album.name !== 'string' ||
    !['drive', 'local'].includes(album.source) ||
    !Array.isArray(album.entries)
  )
    throw new Error('Album cloud không hợp lệ.');
  for (const e of album.entries) {
    relativeKey(e.path);
    if (typeof e.name !== 'string' || (e.id !== undefined && !/^[\w-]{1,200}$/.test(e.id)))
      throw new Error('Danh sách ảnh cloud không hợp lệ.');
  }
  return {
    ...album,
    project: parseProject(album.project),
    cloudRevision: data.revision,
    cloudUid: user.uid,
  };
}
export interface Recommendation {
  path: string;
  score: number;
  reason: string;
  editing_note: string;
}
export async function reviewImages(
  images: { path: string; data: string }[],
  criteria: string,
): Promise<{ summary: string; photos: Recommendation[] }> {
  if (!cloudUser()) throw new Error('Đăng nhập Firebase trong mục Đồng bộ trước khi dùng AI.');
  const invoke = httpsCallable(getFunctions(app(), getConfig().region), 'reviewPhotos', {
    timeout: 75000,
  });
  const response = await invoke({
    images: images.map((i, index) => ({ id: index + 1, data: i.data })),
    criteria,
  });
  const result = response.data as {
    summary: string;
    photos: { id: number; score: number; reason: string; editing_note: string }[];
  };
  if (
    !Array.isArray(result.photos) ||
    result.photos.length !== images.length ||
    new Set(result.photos.map((p) => p.id)).size !== images.length
  )
    throw new Error('Kết quả AI không đầy đủ.');
  return {
    summary: result.summary,
    photos: result.photos.map((p) => {
      if (
        !Number.isInteger(p.id) ||
        !images[p.id - 1] ||
        !Number.isInteger(p.score) ||
        p.score < 0 ||
        p.score > 100 ||
        typeof p.reason !== 'string' ||
        typeof p.editing_note !== 'string'
      )
        throw new Error('Kết quả AI không hợp lệ.');
      return { ...p, path: images[p.id - 1].path };
    }),
  };
}
