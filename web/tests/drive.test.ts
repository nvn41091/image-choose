import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadDrive, parseDriveUrl } from '../src/drive';
import { blankProject, updatePhotos } from '../src/model';

vi.mock('../src/config', () => ({
  getConfig: () => ({ googleApiKey: 'public-key', googleClientId: '' }),
}));
afterEach(() => vi.unstubAllGlobals());
describe('Drive', () => {
  it('accepts folder, file, legacy open links and resource keys', () => {
    expect(
      parseDriveUrl('https://drive.google.com/drive/u/0/folders/folder123?resourcekey=abc-1'),
    ).toEqual({ id: 'folder123', resourceKey: 'abc-1' });
    expect(parseDriveUrl('https://drive.google.com/file/d/photo123/view').id).toBe('photo123');
    expect(parseDriveUrl('https://drive.google.com/open?id=folder123').id).toBe('folder123');
    expect(() => parseDriveUrl('https://evil.com/drive/folders/xxx')).toThrow();
    expect(() => parseDriveUrl('http://drive.google.com/drive/folders/xxx')).toThrow();
  });
  it('paginates, recurses, retains paths and forwards folder resource keys', async () => {
    const calls: URL[] = [];
    const headers: Headers[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: URL, options: RequestInit) => {
        const u = new URL(input);
        calls.push(u);
        headers.push(new Headers(options.headers));
        if (u.pathname.endsWith('/files/folder123'))
          return Response.json({
            id: 'folder123',
            name: 'Album',
            mimeType: 'application/vnd.google-apps.folder',
          });
        if (u.pathname.endsWith('/files/tags123'))
          return Response.json(
            updatePhotos(blankProject(), ['Sub/a.jpg'], () => ({ ai_score: 90 })),
          );
        if (u.searchParams.get('q')?.includes('sub123'))
          return Response.json({ files: [{ id: 'a2', name: 'a.jpg', mimeType: 'image/jpeg' }] });
        if (u.searchParams.get('pageToken') === 'next')
          return Response.json({
            files: [{ id: 'tags123', name: 'photo_tags.json', mimeType: 'application/json' }],
          });
        return Response.json({
          files: [
            { id: 'a1', name: 'a.jpg', mimeType: 'image/jpeg' },
            {
              id: 'sub123',
              name: 'Sub',
              mimeType: 'application/vnd.google-apps.folder',
              resourceKey: 'subkey',
            },
          ],
          nextPageToken: 'next',
        });
      }),
    );
    const result = await loadDrive(
      'https://drive.google.com/drive/folders/folder123?resourcekey=rootkey',
      new AbortController().signal,
      () => {},
    );
    expect(result.entries.map((e) => e.path)).toEqual(['a.jpg', 'Sub/a.jpg']);
    expect(result.project.photos['Sub/a.jpg'].ai_score).toBe(90);
    expect(calls.every((u) => u.searchParams.get('key') === 'public-key')).toBe(true);
    expect(headers.some((h) => h.get('X-Goog-Drive-Resource-Keys') === 'sub123/subkey')).toBe(true);
  });
  it('rejects duplicate Drive paths rather than tagging the wrong photo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: URL) =>
        new URL(input).pathname.endsWith('/files/folder123')
          ? Response.json({
              id: 'folder123',
              name: 'Album',
              mimeType: 'application/vnd.google-apps.folder',
            })
          : Response.json({
              files: [
                { id: 'a', name: 'a.jpg', mimeType: 'image/jpeg' },
                { id: 'b', name: 'A.jpg', mimeType: 'image/jpeg' },
              ],
            }),
      ),
    );
    await expect(
      loadDrive(
        'https://drive.google.com/drive/folders/folder123',
        new AbortController().signal,
        () => {},
      ),
    ).rejects.toThrow('trùng');
  });
});
