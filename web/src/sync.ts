import {
  blankProject,
  photoAt,
  parseProject,
  type Album,
  type AlbumContent,
  type Photo,
} from './model';
const canonical = (value: unknown): unknown =>
  Array.isArray(value)
    ? value.map(canonical)
    : value && typeof value === 'object'
      ? Object.fromEntries(
          Object.entries(value)
            .filter(([, v]) => v !== undefined)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([k, v]) => [k, canonical(v)]),
        )
      : value;
const same = (a: unknown, b: unknown) =>
  JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
export function albumContent(a: Album): AlbumContent {
  return {
    id: a.id,
    name: a.name,
    source: a.source,
    driveUrl: a.driveUrl,
    entries: a.entries,
    project: a.project,
  };
}
export const needsSync = (a: Album) => !a.cloudBase || !same(albumContent(a), a.cloudBase);
export function mergeAlbum(local: Album, remote: Album, base = local.cloudBase): Album {
  const original = base?.project || blankProject();
  const categories = same(local.project.categories, original.categories)
    ? remote.project.categories
    : local.project.categories;
  const photos: Record<string, Photo> = Object.assign(Object.create(null), remote.project.photos);
  const fields = ['stars', 'favorite', 'note', 'ai_score'] as const;
  for (const path of new Set([
    ...Object.keys(original.photos),
    ...Object.keys(local.project.photos),
  ])) {
    const before = photoAt(original, path),
      edited = photoAt(local.project, path),
      result = { ...photoAt(remote.project, path) };
    let changed = false;
    for (const field of fields)
      if (!same(before[field], edited[field])) {
        Object.assign(result, { [field]: edited[field] });
        changed = true;
      }
    const added = edited.category_ids.filter((id) => !before.category_ids.includes(id));
    const removed = before.category_ids.filter((id) => !edited.category_ids.includes(id));
    if (added.length || removed.length) {
      result.category_ids = [
        ...new Set([...result.category_ids.filter((id) => !removed.includes(id)), ...added]),
      ];
      changed = true;
    }
    if (changed) {
      result.updated_at = edited.updated_at;
      photos[path] = result;
    }
  }
  const allowed = new Set(categories.map((c) => c.id));
  for (const [path, p] of Object.entries(photos))
    photos[path] = { ...p, category_ids: p.category_ids.filter((id) => allowed.has(id)) };
  const project = parseProject({
    schema_version: 1,
    categories,
    customer_name:
      local.project.customer_name === original.customer_name
        ? remote.project.customer_name
        : local.project.customer_name,
    photos,
  });
  return {
    ...remote,
    name: !base || local.name !== base.name ? local.name : remote.name,
    source: !base || local.source !== base.source ? local.source : remote.source,
    driveUrl: !base || local.driveUrl !== base.driveUrl ? local.driveUrl : remote.driveUrl,
    entries: !base || !same(local.entries, base.entries) ? local.entries : remote.entries,
    project,
    updatedAt: local.updatedAt > remote.updatedAt ? local.updatedAt : remote.updatedAt,
    cloudBase: albumContent(remote),
  };
}
