import {
  blankProject,
  isPhoto,
  packageProject,
  parseProject,
  relativeKey,
  type Album,
  type Entry,
} from './model';
import { getConfig } from './config';

const scope = 'https://www.googleapis.com/auth/drive.readonly';
export const DRIVE_SESSION_EVENT = 'drive-session-connected';
let accessToken = '',
  expiresAt = 0;
let gis: Promise<void> | undefined;
interface TokenReply {
  access_token: string;
  expires_in: number;
  error?: string;
  scope: string;
}
interface GoogleOAuth {
  initTokenClient(config: {
    client_id: string;
    scope: string;
    callback: (r: TokenReply) => void;
    error_callback: (error: { type: string }) => void;
  }): { requestAccessToken(config: { prompt: string }): void };
  hasGrantedAllScopes(reply: TokenReply, scope: string): boolean;
  revoke(token: string, callback: () => void): void;
}
const googleOAuth = () =>
  (window as unknown as { google?: { accounts: { oauth2: GoogleOAuth } } }).google?.accounts.oauth2;
export function prepareDriveLogin() {
  if (googleOAuth()) return Promise.resolve();
  if (!gis)
    gis = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        gis = undefined;
        script.remove();
        reject(
          new Error('Không tải được đăng nhập Google. Kiểm tra mạng hoặc trình chặn nội dung.'),
        );
      };
      document.head.append(script);
    });
  return gis;
}
export function driveSignedIn() {
  return !!accessToken && Date.now() < expiresAt;
}
export function driveNeedsLogin() {
  return !driveSignedIn() && (!!accessToken || !getConfig().googleApiKey.trim());
}
export function signInDrive(): Promise<void> {
  const id = getConfig().googleClientId.trim();
  if (!id) return Promise.reject(new Error('Mở Cấu hình để nhập Google OAuth Client ID.'));
  const oauth = googleOAuth();
  if (!oauth)
    return prepareDriveLogin().then(() => {
      throw new Error(
        'Đã tải đăng nhập Google. Bấm Kết nối Google thêm một lần để mở cửa sổ đăng nhập.',
      );
    });
  // requestAccessToken must run in the original click event on mobile browsers.
  return new Promise((resolve, reject) => {
    oauth
      .initTokenClient({
        client_id: id,
        scope,
        callback: (reply) => {
          if (reply.error || !oauth.hasGrantedAllScopes(reply, scope)) {
            accessToken = '';
            expiresAt = 0;
            return reject(
              new Error(
                'Bạn chưa cấp quyền đọc Google Drive. Kết nối lại và đồng ý quyền xem các tệp Drive.',
              ),
            );
          }
          if (
            !reply.access_token ||
            !Number.isFinite(Number(reply.expires_in)) ||
            Number(reply.expires_in) <= 30
          )
            return reject(new Error('Google chưa trả về phiên Drive hợp lệ. Hãy kết nối lại.'));
          accessToken = reply.access_token;
          expiresAt = Date.now() + Number(reply.expires_in) * 1000 - 30000;
          window.dispatchEvent(new Event(DRIVE_SESSION_EVENT));
          resolve();
        },
        error_callback: (error) =>
          reject(
            new Error(
              error.type === 'popup_closed'
                ? 'Bạn đã đóng cửa sổ đăng nhập. Bấm kết nối Google khi muốn tiếp tục.'
                : 'Không mở được đăng nhập Google. Hãy cho phép popup; nếu đang dùng trình duyệt trong ứng dụng, mở website bằng Chrome hoặc Safari rồi thử lại.',
            ),
          ),
      })
      .requestAccessToken({ prompt: '' });
  });
}
export async function signOutDrive() {
  const token = accessToken;
  accessToken = '';
  expiresAt = 0;
  if (token && googleOAuth())
    await new Promise<void>((resolve) => googleOAuth()!.revoke(token, resolve));
}
export function parseDriveUrl(input: string) {
  let url: URL;
  try {
    url = new URL(input.trim());
  } catch {
    throw new Error('Dán link thư mục hoặc ảnh Google Drive hợp lệ.');
  }
  if (
    url.protocol !== 'https:' ||
    !['drive.google.com', 'www.drive.google.com'].includes(url.hostname)
  )
    throw new Error('Chỉ nhận link https://drive.google.com.');
  const match = url.pathname.match(/\/(folders|d)\/([a-zA-Z0-9_-]+)/);
  const id = match?.[2] || url.searchParams.get('id');
  const resourceKey = url.searchParams.get('resourcekey') || '';
  if (!id || !/^[\w-]{5,200}$/.test(id) || (resourceKey && !/^[\w-]{1,200}$/.test(resourceKey)))
    throw new Error('Link Drive thiếu ID hoặc resource key không hợp lệ.');
  return { id, resourceKey };
}
async function driveRequest(
  path: string,
  params: Record<string, string>,
  keys: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<Response> {
  if (accessToken && !driveSignedIn())
    throw new Error(
      'Phiên Google Drive hết hạn. Bấm Kết nối Google rồi thử lại; lựa chọn đã lưu vẫn được giữ.',
    );
  const url = new URL('https://www.googleapis.com/drive/v3/' + path);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  if (!accessToken) {
    const key = getConfig().googleApiKey.trim();
    if (!key)
      throw new Error(
        'Kết nối Google để mở Drive riêng tư, hoặc cấu hình API key để đọc Drive công khai.',
      );
    url.searchParams.set('key', key);
  }
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const resource = Object.entries(keys)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}/${v}`)
    .join(',');
  if (resource) headers['X-Goog-Drive-Resource-Keys'] = resource;
  const response = await fetch(url, { headers, signal: signal || AbortSignal.timeout(60000) });
  if (!response.ok) {
    if (response.status === 401) {
      accessToken = '';
      expiresAt = 0;
      throw new Error('Phiên Google đã hết hạn. Hãy kết nối lại Google.');
    }
    if (response.status === 403 || response.status === 404)
      throw new Error(
        'Không đọc được Drive. Kiểm tra quyền chia sẻ, tài khoản, Drive API và hạn mức API.',
      );
    throw new Error(`Google Drive báo HTTP ${response.status}. Hãy thử lại sau.`);
  }
  return response;
}
interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  resourceKey?: string;
}
export async function loadDrive(
  url: string,
  signal: AbortSignal,
  progress: (message: string) => void,
): Promise<Album> {
  const root = parseDriveUrl(url),
    keys: Record<string, string> = { [root.id]: root.resourceKey };
  const info: DriveFile = await (
    await driveRequest(
      'files/' + root.id,
      { fields: 'id,name,mimeType,resourceKey', supportsAllDrives: 'true' },
      keys,
      signal,
    )
  ).json();
  const entries: Entry[] = [];
  let project = blankProject();
  const pending = [{ file: info, prefix: '' }];
  const visited = new Set<string>();
  let tags: DriveFile | undefined, pack: DriveFile | undefined;
  while (pending.length) {
    signal.throwIfAborted();
    const { file, prefix } = pending.shift()!;
    if (file.resourceKey) keys[file.id] = file.resourceKey;
    if (file.mimeType !== 'application/vnd.google-apps.folder') {
      if (isPhoto(file.name))
        entries.push({
          path: relativeKey(prefix + file.name),
          name: file.name,
          id: file.id,
          resourceKey: file.resourceKey,
          size: Number(file.size) || 0,
          mimeType: file.mimeType,
        });
      continue;
    }
    if (visited.has(file.id)) continue;
    visited.add(file.id);
    let pageToken = '';
    do {
      const data = (await (
        await driveRequest(
          'files',
          {
            q: `'${file.id}' in parents and trashed = false`,
            fields: 'nextPageToken,incompleteSearch,files(id,name,mimeType,size,resourceKey)',
            pageSize: '1000',
            pageToken,
            supportsAllDrives: 'true',
            includeItemsFromAllDrives: 'true',
          },
          { [file.id]: keys[file.id] || '' },
          signal,
        )
      ).json()) as { files: DriveFile[]; nextPageToken?: string; incompleteSearch?: boolean };
      if (data.incompleteSearch)
        throw new Error(
          'Drive trả kết quả chưa đầy đủ. Chưa mở album; hãy thử lại với thư mục nhỏ hơn.',
        );
      for (const child of data.files) {
        if (!prefix && child.name === 'photo_tags.json') tags = child;
        if (!prefix && child.name === 'goi_chup.json') pack = child;
        if (child.resourceKey) keys[child.id] = child.resourceKey;
        if (child.mimeType === 'application/vnd.google-apps.folder')
          pending.push({ file: child, prefix: relativeKey(prefix + child.name) + '/' });
        else if (isPhoto(child.name))
          entries.push({
            path: relativeKey(prefix + child.name),
            name: child.name,
            id: child.id,
            resourceKey: child.resourceKey,
            size: Number(child.size) || 0,
            mimeType: child.mimeType,
          });
      }
      progress(`Đã tìm thấy ${entries.length.toLocaleString('vi')} ảnh · ${visited.size} thư mục`);
      pageToken = data.nextPageToken || '';
    } while (pageToken);
  }
  if (new Set(entries.map((e) => e.path.toLowerCase())).size !== entries.length)
    throw new Error(
      'Drive có tên ảnh hoặc thư mục trùng đường dẫn. Đổi tên trên Drive trước khi mở để khớp đúng backup PC.',
    );
  const metadata = tags || pack;
  if (metadata) {
    if (Number(metadata.size) > 16 * 1024 * 1024)
      throw new Error('Dữ liệu lựa chọn trên Drive vượt 16 MB.');
    const data = await (
      await driveRequest(
        'files/' + metadata.id,
        { alt: 'media', supportsAllDrives: 'true' },
        { [metadata.id]: keys[metadata.id] || '' },
        signal,
      )
    ).json();
    project = tags ? parseProject(data) : packageProject(data);
  }
  if (!entries.length)
    throw new Error('Không tìm thấy ảnh JPG, PNG, WebP, GIF, BMP hoặc TIFF trong link này.');
  return {
    id: 'drive-' + root.id,
    name: info.name,
    source: 'drive',
    driveUrl: url,
    entries,
    project,
    updatedAt: new Date().toISOString(),
  };
}
let active = 0;
const waiters: (() => void)[] = [];
export async function driveBlob(entry: Entry, signal?: AbortSignal): Promise<Blob> {
  if (active >= 4) await new Promise<void>((resolve) => waiters.push(resolve));
  active++;
  try {
    signal?.throwIfAborted();
    if (!entry.id) throw new Error('Ảnh thiếu ID Drive.');
    return await (
      await driveRequest(
        'files/' + entry.id,
        { alt: 'media', supportsAllDrives: 'true' },
        { [entry.id]: entry.resourceKey || '' },
        signal,
      )
    ).blob();
  } finally {
    active--;
    waiters.shift()?.();
  }
}
