import {
  firebaseApp as app,
  currentAccount,
  accountReady,
  loginGoogle,
  logoutGoogle,
} from './auth';
import {
  collection,
  doc,
  getDoc,
  getDocs,
  getFirestore,
  runTransaction,
  serverTimestamp,
  setDoc,
  onSnapshot,
} from 'firebase/firestore';
import { getFunctions, httpsCallable } from 'firebase/functions';
import { gzipSync, gunzipSync, strToU8, strFromU8 } from 'fflate';
import { getConfig } from './config';
import { parseProject, relativeKey, type Album } from './model';
import { albumContent, mergeAlbum } from './sync';

export const cloudUser = currentAccount;
export const cloudLogin = loginGoogle;
export const cloudLogout = logoutGoogle;
export const cloudReady = accountReady;
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
    strToU8(JSON.stringify({ ...albumContent(album), updatedAt: album.updatedAt })),
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
  const ref = doc(getFirestore(app()), 'users', user.uid, 'albums', album.id);
  const saved = await runTransaction(getFirestore(app()), async (tx) => {
    const current = await tx.get(ref);
    const latest = current.exists() ? current.data().revision : 0;
    const merged = current.exists()
      ? mergeAlbum(album, decodeAlbum(album.id, current.data(), user.uid))
      : album;
    const payload = encode(merged);
    tx.set(ref, {
      name: merged.name,
      payload,
      revision: latest + 1,
      updatedAt: new Date().toISOString(),
      savedAt: serverTimestamp(),
    });
    return {
      ...merged,
      cloudRevision: latest + 1,
      cloudUid: user.uid,
      cloudBase: albumContent(merged),
    };
  });
  return saved;
}
export async function pullCloud(id: string): Promise<Album> {
  const user = cloudUser();
  if (!user) throw new Error('Đăng nhập đồng bộ trước.');
  const result = await getDoc(doc(getFirestore(app()), 'users', user.uid, 'albums', id));
  if (!result.exists()) throw new Error('Không tìm thấy album trên Firebase.');
  return decodeAlbum(id, result.data(), user.uid);
}
function decodeAlbum(id: string, data: Record<string, unknown>, uid: string): Album {
  const bytes = Uint8Array.from(atob(String(data.payload)), (c) => c.charCodeAt(0));
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
  const result: Album = {
    ...album,
    project: parseProject(album.project),
    cloudRevision: Number(data.revision),
    cloudUid: uid,
  };
  result.cloudBase = albumContent(result);
  return result;
}
export async function activeWorkspace() {
  const user = cloudUser();
  if (!user) return '';
  const snapshot = await getDoc(
    doc(getFirestore(app()), 'users', user.uid, 'settings', 'workspace'),
  );
  return snapshot.exists() ? String(snapshot.data().activeAlbumId || '') : '';
}
export async function rememberWorkspace(id: string) {
  const user = cloudUser();
  if (!user) throw new Error('Cần đăng nhập.');
  await setDoc(doc(getFirestore(app()), 'users', user.uid, 'settings', 'workspace'), {
    activeAlbumId: id,
    updatedAt: serverTimestamp(),
  });
}
export function observeWorkspaces(
  next: (items: CloudEntry[], changed: Album[]) => void,
  error: (error: Error) => void,
) {
  const user = cloudUser();
  if (!user) throw new Error('Cần đăng nhập.');
  return onSnapshot(
    collection(getFirestore(app()), 'users', user.uid, 'albums'),
    (snapshot) => {
      try {
        next(
          snapshot.docs.map((d) => ({
            id: d.id,
            name: d.data().name,
            updatedAt: d.data().updatedAt,
            revision: d.data().revision,
          })),
          snapshot
            .docChanges()
            .filter((c) => c.type !== 'removed')
            .map((c) => decodeAlbum(c.doc.id, c.doc.data(), user.uid)),
        );
      } catch (e) {
        error(e as Error);
      }
    },
    error,
  );
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
