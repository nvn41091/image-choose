import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const config = vi.hoisted(() => ({
  googleClientId: 'test.apps.googleusercontent.com',
  googleApiKey: '',
}));
vi.mock('../src/config', () => ({ getConfig: () => config }));
beforeEach(() => {
  vi.resetModules();
  config.googleApiKey = '';
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mockGoogle(granted = true, popupError = '') {
  const oauth = {
    initTokenClient: vi.fn(
      (options: {
        callback: (r: unknown) => void;
        error_callback: (r: { type: string }) => void;
      }) => ({
        requestAccessToken: vi.fn(() =>
          popupError
            ? options.error_callback({ type: popupError })
            : options.callback({
                access_token: 'test-token',
                expires_in: 3600,
                scope: 'https://www.googleapis.com/auth/drive.readonly',
              }),
        ),
      }),
    ),
    hasGrantedAllScopes: vi.fn(() => granted),
  };
  vi.stubGlobal('window', { dispatchEvent: vi.fn(), google: { accounts: { oauth2: oauth } } });
  return oauth;
}

it('needs Google consent without an API key and retains a valid session in memory', async () => {
  const oauth = mockGoogle();
  const drive = await import('../src/drive');
  expect(drive.driveNeedsLogin()).toBe(true);
  const login = drive.signInDrive();
  expect(oauth.initTokenClient).toHaveBeenCalledOnce();
  await login;
  expect(drive.driveSignedIn()).toBe(true);
  expect(drive.driveNeedsLogin()).toBe(false);
});

it('allows the explicit public API key flow without requesting a Google session', async () => {
  config.googleApiKey = 'public-key';
  mockGoogle();
  const drive = await import('../src/drive');
  expect(drive.driveNeedsLogin()).toBe(false);
  expect(drive.driveSignedIn()).toBe(false);
});

it('requests a fresh user-driven login for an expired session, even with an API key', async () => {
  vi.useFakeTimers();
  mockGoogle();
  const drive = await import('../src/drive');
  await drive.signInDrive();
  config.googleApiKey = 'public-key';
  vi.advanceTimersByTime(3600 * 1000);
  expect(drive.driveSignedIn()).toBe(false);
  expect(drive.driveNeedsLogin()).toBe(true);
});

it('does not create a Drive session when consent is refused', async () => {
  mockGoogle(false);
  const drive = await import('../src/drive');
  await expect(drive.signInDrive()).rejects.toThrow('chưa cấp quyền đọc');
  expect(drive.driveSignedIn()).toBe(false);
  expect(drive.driveNeedsLogin()).toBe(true);
});

it('explains how to recover from a blocked popup', async () => {
  mockGoogle(true, 'popup_failed_to_open');
  await expect((await import('../src/drive')).signInDrive()).rejects.toThrow('Chrome hoặc Safari');
});
