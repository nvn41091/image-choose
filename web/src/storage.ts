import { openDB } from 'idb';
import type { Album } from './model';

const db = openDB('chon-anh-cuoi-v1', 1, {
  upgrade(database) {
    database.createObjectStore('albums', { keyPath: 'id' });
    database.createObjectStore('blobs');
    database.createObjectStore('recovery');
  },
});
export const listAlbums = async (): Promise<Album[]> =>
  (await (await db).getAll('albums')).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
export const saveAlbum = async (album: Album) => {
  await (await db).put('albums', album);
};
export const getBlob = async (album: string, path: string): Promise<Blob | undefined> =>
  (await db).get('blobs', [album, path]);
export const putBlob = async (album: string, path: string, blob: Blob) => {
  await (await db).put('blobs', blob, [album, path]);
};
export const saveRecovery = async (album: Album) => {
  await (await db).put('recovery', album, album.id);
};
export const getRecovery = async (id: string): Promise<Album | undefined> =>
  (await db).get('recovery', id);
export async function importLocalAlbum(album: Album, blobs: Map<string, Blob>) {
  const tx = (await db).transaction(['albums', 'blobs'], 'readwrite');
  for (const [path, blob] of blobs) await tx.objectStore('blobs').put(blob, [album.id, path]);
  await tx.objectStore('albums').put(album);
  await tx.done;
}
export async function deleteAlbum(id: string) {
  const tx = (await db).transaction(['albums', 'blobs', 'recovery'], 'readwrite');
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
