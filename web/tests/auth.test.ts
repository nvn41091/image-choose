import { beforeEach, expect, it, vi } from 'vitest';
const mocked = vi.hoisted(() => ({
  drive: vi.fn(),
  credential: vi.fn((id, token) => ({ id, token })),
  signIn: vi.fn(),
  clear: vi.fn(),
  signOut: vi.fn(),
  client: { currentUser: null, authStateReady: async () => {} },
}));
vi.mock('firebase/app', () => ({ getApps: () => [{}], initializeApp: () => ({}) }));
vi.mock('firebase/auth', () => ({
  GoogleAuthProvider: { credential: mocked.credential },
  initializeAuth: () => mocked.client,
  indexedDBLocalPersistence: {},
  browserLocalPersistence: {},
  onAuthStateChanged: vi.fn(),
  signInWithCredential: mocked.signIn,
  signOut: mocked.signOut,
}));
vi.mock('../src/config', () => ({ getConfig: () => ({ firebaseConfig: '{}' }) }));
vi.mock('../src/drive', () => ({ signInDrive: mocked.drive, clearDriveSession: mocked.clear }));
beforeEach(() => {
  vi.clearAllMocks();
  mocked.drive.mockResolvedValue('google-access-token');
  mocked.signIn.mockResolvedValue({ user: { uid: 'verified-user' } });
});
it('requires Firebase to verify the Google credential before completing sign-in', async () => {
  const { loginGoogle } = await import('../src/auth');
  const result = await loginGoogle();
  expect(mocked.credential).toHaveBeenCalledWith(null, 'google-access-token');
  expect(mocked.signIn).toHaveBeenCalledWith(mocked.client, {
    id: null,
    token: 'google-access-token',
  });
  expect(result.user.uid).toBe('verified-user');
});
it('does not attempt Firebase sign-in when Drive consent fails', async () => {
  mocked.drive.mockRejectedValueOnce(new Error('consent denied'));
  await expect((await import('../src/auth')).loginGoogle()).rejects.toThrow('consent denied');
  expect(mocked.signIn).not.toHaveBeenCalled();
});
it('does not treat an unverified Google token as an authenticated app session', async () => {
  mocked.signIn.mockRejectedValueOnce(new Error('invalid credential'));
  await expect((await import('../src/auth')).loginGoogle()).rejects.toThrow('invalid credential');
});
