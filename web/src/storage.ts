import { openDB } from 'idb';
import type { Album } from './model';
const open = (name: string) =>
  openDB(name, 1, {
    upgrade(db) {
      db.createObjectStore('albums', { keyPath: 'id' });
      db.createObjectStore('blobs');
      db.createObjectStore('recovery');
    },
  });
let owner = '';
const databases = new Map<string, ReturnType<typeof open>>();
export function setStorageUser(uid: string) {
  owner = uid;
}
function database() {
  if (!owner) throw new Error('Cần đăng nhập trước khi đọc workspace trên thiết bị.');
  if (!databases.has(owner)) databases.set(owner, open('chon-anh-cuoi-user-' + owner));
  return databases.get(owner)!;
}
export const listAlbums = async (): Promise<Album[]> =>
  (await (await database()).getAll('albums')).sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
export const saveAlbum = async (album: Album) => {
  await (await database()).put('albums', album);
};
export const getBlob = async (album: string, path: string): Promise<Blob | undefined> =>
  (await database()).get('blobs', [album, path]);
export const putBlob = async (album: string, path: string, blob: Blob) => {
  await (await database()).put('blobs', blob, [album, path]);
};
export const saveRecovery = async (album: Album) => {
  await (await database()).put('recovery', album, album.id);
};
export const getRecovery = async (id: string): Promise<Album | undefined> =>
  (await database()).get('recovery', id);
export async function importLocalAlbum(album: Album, blobs: Map<string, Blob>) {
  const tx = (await database()).transaction(['albums', 'blobs'], 'readwrite');
  for (const [path, blob] of blobs) await tx.objectStore('blobs').put(blob, [album.id, path]);
  await tx.objectStore('albums').put(album);
  await tx.done;
}
export async function deleteAlbum(id: string) {
  const tx = (await database()).transaction(['albums', 'blobs', 'recovery'], 'readwrite');
  await tx.objectStore('albums').delete(id);
  await tx.objectStore('recovery').delete(id);
  let cursor = await tx
    .objectStore('blobs')
    .openCursor(IDBKeyRange.bound([id, ''], [id, '\uffff']));
  while (cursor) {
    await cursor.delete();
    cursor = await cursor.continue();
  }
  await tx.done;
}
export async function legacyCount() {
  return (await open('chon-anh-cuoi-v1')).count('albums');
}
export async function importLegacy() {
  const legacy = await open('chon-anh-cuoi-v1'),
    target = await database();
  const albums: Album[] = await legacy.getAll('albums');
  for (const album of albums) {
    if (await target.get('albums', album.id)) continue;
    const blobs = new Map<string, Blob>();
    let cursor = await legacy
      .transaction('blobs')
      .store.openCursor(IDBKeyRange.bound([album.id, ''], [album.id, '\uffff']));
    while (cursor) {
      blobs.set((cursor.key as string[])[1], cursor.value);
      cursor = await cursor.continue();
    }
    await importLocalAlbum(
      { ...album, cloudBase: undefined, cloudRevision: undefined, cloudUid: undefined },
      blobs,
    );
  }
  return listAlbums();
}
