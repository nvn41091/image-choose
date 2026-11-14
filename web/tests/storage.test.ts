import 'fake-indexeddb/auto';
import { expect, it } from 'vitest';
import { blankProject, type Album } from '../src/model';
import { setStorageUser } from '../src/storage';
import {
  deleteAlbum,
  getBlob,
  importLocalAlbum,
  listAlbums,
  saveRecovery,
  getRecovery,
} from '../src/storage';

it('atomically stores local backup images, preserves a recovery snapshot and deletes just its own blobs', async () => {
  setStorageUser('storage-test');
  const album: Album = {
    id: 'one',
    name: 'test',
    source: 'local',
    entries: [{ path: 'sub/a.jpg', name: 'a.jpg' }],
    project: blankProject(),
    updatedAt: '2026-01-01',
  };
  await importLocalAlbum(album, new Map([['sub/a.jpg', new Blob(['one'])]]));
  await importLocalAlbum({ ...album, id: 'two' }, new Map([['sub/a.jpg', new Blob(['two'])]]));
  await saveRecovery(album);
  expect((await getRecovery('one'))?.id).toBe('one');
  expect(await (await getBlob('one', 'sub/a.jpg'))?.text()).toBe('one');
  await deleteAlbum('one');
  expect(await getBlob('one', 'sub/a.jpg')).toBeUndefined();
  expect(await (await getBlob('two', 'sub/a.jpg'))?.text()).toBe('two');
  expect((await listAlbums()).map((a) => a.id)).toEqual(['two']);
});
it('isolates choices and image blobs by authenticated account', async () => {
  setStorageUser('owner-a');
  const a: Album = {
    id: 'same',
    name: 'Private',
    source: 'local',
    entries: [],
    project: blankProject(),
    updatedAt: '',
  };
  await importLocalAlbum(a, new Map([['a.jpg', new Blob(['private'])]]));
  setStorageUser('owner-b');
  expect(await listAlbums()).toEqual([]);
  expect(await getBlob('same', 'a.jpg')).toBeUndefined();
  setStorageUser('owner-a');
  expect((await listAlbums())[0].name).toBe('Private');
  expect(await (await getBlob('same', 'a.jpg'))?.text()).toBe('private');
});
