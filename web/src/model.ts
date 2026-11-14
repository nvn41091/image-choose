export interface Category {
  id: string;
  name: string;
  color: string;
  shortcut: number;
  max_count: number | null;
}
export interface Photo {
  category_ids: string[];
  stars: number;
  favorite: boolean;
  note: string;
  updated_at: string;
  ai_score: number | null;
}
export interface Project {
  schema_version: 1;
  customer_name: string;
  categories: Category[];
  photos: Record<string, Photo>;
}
export interface Entry {
  path: string;
  name: string;
  id?: string;
  resourceKey?: string;
  size?: number;
  mimeType?: string;
}
export interface Album {
  id: string;
  name: string;
  source: 'drive' | 'local';
  driveUrl?: string;
  entries: Entry[];
  project: Project;
  updatedAt: string;
  cloudRevision?: number;
  cloudUid?: string;
  cloudBase?: AlbumContent;
}
export type AlbumContent = Pick<
  Album,
  'id' | 'name' | 'source' | 'driveUrl' | 'entries' | 'project'
>;
export const defaults: Category[] = [
  { id: 'album', name: 'Album', color: '#426b59', shortcut: 1, max_count: null },
  { id: 'phong_lon', name: 'Phóng lớn', color: '#b46553', shortcut: 2, max_count: null },
  {
    id: 'anh_de_ban',
    name: 'Ảnh để bàn / ảnh nhỏ',
    color: '#b28a42',
    shortcut: 3,
    max_count: null,
  },
  { id: 'mang_xa_hoi', name: 'Đăng mạng xã hội', color: '#527899', shortcut: 4, max_count: null },
  {
    id: 'chinh_sua',
    name: 'Cần chỉnh sửa đặc biệt',
    color: '#8a6796',
    shortcut: 5,
    max_count: null,
  },
];
export const blankPhoto = (): Photo => ({
  category_ids: [],
  stars: 0,
  favorite: false,
  note: '',
  updated_at: '',
  ai_score: null,
});
export const blankProject = (): Project => ({
  schema_version: 1,
  customer_name: '',
  categories: structuredClone(defaults),
  photos: {},
});
export const photoAt = (project: Project, path: string): Photo =>
  project.photos[path] || blankPhoto();
export const isPhoto = (path: string) => /\.(jpe?g|png|webp|gif|bmp|tiff?)$/i.test(path);
export const isRaw = (path: string) => /\.(cr2|cr3|nef|arw)$/i.test(path);
export function relativeKey(path: string): string {
  const key = path.replace(/\\/g, '/');
  if (
    !key ||
    key.startsWith('/') ||
    key.split('/').some((p) => !p || p === '.' || p === '..' || /[<>:"|?*\x00-\x1f]/.test(p))
  )
    throw new Error('Đường dẫn ảnh không hợp lệ.');
  return key;
}
export function parseProject(input: unknown): Project {
  const data = input as Project;
  if (
    !data ||
    data.schema_version !== 1 ||
    typeof data.customer_name !== 'string' ||
    !Array.isArray(data.categories) ||
    !data.photos ||
    Array.isArray(data.photos) ||
    typeof data.photos !== 'object'
  )
    throw new Error('photo_tags.json không đúng định dạng phiên bản 1.');
  const ids = new Set<string>(),
    names = new Set<string>(),
    shortcuts = new Set<number>();
  const categories = data.categories.map((c) => {
    if (
      !c ||
      typeof c.id !== 'string' ||
      !c.id ||
      ids.has(c.id) ||
      typeof c.name !== 'string' ||
      !c.name.trim() ||
      /[\x00-\x1f]/.test(c.name) ||
      names.has(c.name.trim().toLowerCase()) ||
      !/^#[a-f\d]{6}$/i.test(c.color) ||
      !Number.isInteger(c.shortcut) ||
      c.shortcut < 1 ||
      c.shortcut > 9 ||
      shortcuts.has(c.shortcut) ||
      (c.max_count != null &&
        (!Number.isInteger(c.max_count) || c.max_count < 0 || c.max_count > 999999999))
    )
      throw new Error('Kiểm tra tên loại, màu, phím tắt và giới hạn gói.');
    ids.add(c.id);
    names.add(c.name.trim().toLowerCase());
    shortcuts.add(c.shortcut);
    return {
      id: c.id,
      name: c.name.trim(),
      color: c.color,
      shortcut: c.shortcut,
      max_count: c.max_count ?? null,
    };
  });
  const photos: Record<string, Photo> = Object.create(null);
  for (const [raw, v] of Object.entries(data.photos)) {
    const path = relativeKey(raw);
    if (
      Object.hasOwn(photos, path) ||
      !v ||
      !Array.isArray(v.category_ids) ||
      v.category_ids.some((t) => !ids.has(t)) ||
      !Number.isInteger(v.stars ?? 0) ||
      (v.stars ?? 0) < 0 ||
      (v.stars ?? 0) > 5 ||
      typeof (v.favorite ?? false) !== 'boolean' ||
      typeof (v.note ?? '') !== 'string' ||
      typeof (v.updated_at ?? '') !== 'string' ||
      (v.ai_score != null && (!Number.isInteger(v.ai_score) || v.ai_score < 0 || v.ai_score > 100))
    )
      throw new Error(`Dữ liệu ảnh không hợp lệ: ${path}`);
    photos[path] = {
      ...blankPhoto(),
      ...v,
      category_ids: [...new Set(v.category_ids)],
      ai_score: v.ai_score ?? null,
      note: (v.note || '').replace(/^\[ChatGPT\][ \t]?/gm, ''),
    };
  }
  return { schema_version: 1, customer_name: data.customer_name, categories, photos };
}
export function updatePhotos(
  project: Project,
  paths: string[],
  change: (p: Photo) => Partial<Photo>,
): Project {
  const photos: Record<string, Photo> = Object.assign(Object.create(null), project.photos);
  for (const path of paths)
    photos[path] = {
      ...photoAt(project, path),
      ...change(photoAt(project, path)),
      updated_at: new Date().toISOString(),
    };
  return { ...project, photos };
}
export function counts(project: Project): Record<string, number> {
  const result: Record<string, number> = Object.fromEntries(
    project.categories.map((c) => [c.id, 0]),
  );
  for (const p of Object.values(project.photos))
    for (const id of p.category_ids) result[id] = (result[id] || 0) + 1;
  return result;
}
export type Sort =
  'name_asc' | 'name_desc' | 'score_desc' | 'score_asc' | 'stars_desc' | 'stars_asc';
export function sortEntries(entries: Entry[], project: Project, mode: Sort): Entry[] {
  return [...entries].sort((a, b) => {
    if (!mode.startsWith('name')) {
      const field = mode.startsWith('score') ? 'ai_score' : 'stars';
      const av = photoAt(project, a.path)[field],
        bv = photoAt(project, b.path)[field];
      const missingA = av == null || (field === 'stars' && av === 0),
        missingB = bv == null || (field === 'stars' && bv === 0);
      if (missingA !== missingB) return missingA ? 1 : -1;
      if (!missingA && av !== bv) return ((av || 0) - (bv || 0)) * (mode.endsWith('desc') ? -1 : 1);
    }
    return (
      a.path.localeCompare(b.path, 'vi', { numeric: true, sensitivity: 'base' }) *
      (mode === 'name_desc' ? -1 : 1)
    );
  });
}
const stem = (path: string) => path.replace(/\.[^/.]+$/, '').toLowerCase();
export function matchRaw(project: Project, paths: string[]) {
  const matches: Record<string, string> = {},
    issues: string[] = [];
  const byPath = new Map<string, string[]>(),
    byName = new Map<string, string[]>();
  for (const path of paths.filter(isRaw)) {
    for (const [map, key] of [
      [byPath, stem(path)],
      [byName, stem(path.split('/').pop()!)],
    ] as const)
      map.set(key, [...(map.get(key) || []), path]);
  }
  for (const [path, p] of Object.entries(project.photos)) {
    if (!p.category_ids.length) continue;
    const candidates = byPath.get(stem(path)) || byName.get(stem(path.split('/').pop()!)) || [];
    if (candidates.length === 1) matches[path] = candidates[0];
    else
      issues.push(
        `${path} — ${candidates.length ? 'nhiều kết quả: ' + candidates.join(', ') : 'chưa tìm thấy RAW'}`,
      );
  }
  return { matches, issues };
}
export function packageProject(input: unknown): Project {
  const data = input as { customer_name?: string; limits?: Record<string, number | null> };
  const p = blankProject();
  p.customer_name = data.customer_name ?? '';
  p.categories = p.categories.map((c) => ({ ...c, max_count: data.limits?.[c.id] ?? null }));
  if (data.limits && Object.keys(data.limits).some((id) => !p.categories.some((c) => c.id === id)))
    throw new Error('Mã loại trong goi_chup.json không hợp lệ.');
  return parseProject(p);
}
