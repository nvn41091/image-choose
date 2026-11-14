import { expect, it } from 'vitest';
import { albumContent, mergeAlbum, needsSync } from '../src/sync';
import { blankProject, updatePhotos, type Album } from '../src/model';
const album = (): Album => ({
  id: 'one',
  name: 'Workspace',
  source: 'drive',
  entries: [{ path: 'a.jpg', name: 'a.jpg' }],
  project: blankProject(),
  updatedAt: '2026-01-01',
});
it('combines concurrent changes to different fields and different photos', () => {
  const base = album();
  const local = {
    ...base,
    cloudBase: albumContent(base),
    project: updatePhotos(base.project, ['a.jpg'], () => ({ favorite: true, stars: 5 })),
  };
  let remote = {
    ...base,
    project: updatePhotos(base.project, ['a.jpg'], () => ({ note: 'giữ màu', ai_score: 0 })),
  };
  remote = {
    ...remote,
    project: updatePhotos(remote.project, ['b.jpg'], () => ({ category_ids: ['album'] })),
  };
  const result = mergeAlbum(local, remote);
  expect(result.project.photos['a.jpg']).toMatchObject({
    favorite: true,
    stars: 5,
    note: 'giữ màu',
    ai_score: 0,
  });
  expect(result.project.photos['b.jpg'].category_ids).toEqual(['album']);
});
it('merges independent category additions and preserves another device’s edit', () => {
  const base = album();
  base.project = updatePhotos(base.project, ['a.jpg'], () => ({ category_ids: ['album'] }));
  const local = {
    ...base,
    cloudBase: albumContent(base),
    project: updatePhotos(base.project, ['a.jpg'], () => ({ category_ids: ['phong_lon'] })),
  };
  const remote = {
    ...base,
    project: updatePhotos(base.project, ['a.jpg'], () => ({
      category_ids: ['album', 'chinh_sua'],
    })),
  };
  expect(mergeAlbum(local, remote).project.photos['a.jpg'].category_ids.sort()).toEqual([
    'chinh_sua',
    'phong_lon',
  ]);
});
it('keeps edits made during an in-flight save and becomes clean after its acknowledgement', () => {
  const base = album();
  const sent = {
    ...base,
    cloudBase: albumContent(base),
    project: updatePhotos(base.project, ['a.jpg'], () => ({ stars: 4 })),
  };
  const edited = {
    ...sent,
    project: updatePhotos(sent.project, ['a.jpg'], () => ({ note: 'new note' })),
  };
  const remote = { ...sent, cloudRevision: 2, cloudBase: albumContent(sent) };
  const result = mergeAlbum(edited, remote, albumContent(sent));
  expect(result.project.photos['a.jpg'].note).toBe('new note');
  expect(needsSync(result)).toBe(true);
  expect(needsSync({ ...result, cloudBase: albumContent(result) })).toBe(false);
});
it('does not treat reordered object keys as unsaved changes', () => {
  const a = album();
  a.project = updatePhotos(a.project, ['a.jpg', 'b.jpg'], () => ({ favorite: true }));
  const content = albumContent(a);
  content.project = {
    ...a.project,
    photos: Object.fromEntries(Object.entries(a.project.photos).reverse()),
  };
  expect(needsSync({ ...a, cloudBase: content })).toBe(false);
});
it('removes deleted categories from remote photos when a package is edited', () => {
  const base = album(),
    local = {
      ...base,
      cloudBase: albumContent(base),
      project: {
        ...base.project,
        categories: base.project.categories.filter((c) => c.id !== 'album'),
      },
    };
  const remote = {
    ...base,
    project: updatePhotos(base.project, ['a.jpg'], () => ({
      category_ids: ['album'],
      favorite: true,
    })),
  };
  expect(mergeAlbum(local, remote).project.photos['a.jpg']).toMatchObject({
    category_ids: [],
    favorite: true,
  });
});
