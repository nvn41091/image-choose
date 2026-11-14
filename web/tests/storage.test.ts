import 'fake-indexeddb/auto';
import { expect, it } from 'vitest';
import { blankProject, type Album } from '../src/model';
import {
  deleteAlbum,
  getBlob,
  importLocalAlbum,
  listAlbums,
  saveRecovery,
  getRecovery,
} from '../src/storage';

it('atomically stores local backup images, preserves a recovery snapshot and deletes just its own blobs', async () => {
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
