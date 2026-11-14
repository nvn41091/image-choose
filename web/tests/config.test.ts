import { afterEach, expect, it, vi } from 'vitest';
import { getConfig } from '../src/config';
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it('uses the centrally deployed Drive key when an old device configuration saved an empty value', () => {
  vi.stubEnv('VITE_GOOGLE_API_KEY', 'deployed-drive-key');
  vi.stubGlobal('localStorage', { getItem: () => JSON.stringify({ googleApiKey: '' }) });
  expect(getConfig().googleApiKey).toBe('deployed-drive-key');
});
it('keeps an explicit device key override and trims it', () => {
  vi.stubEnv('VITE_GOOGLE_API_KEY', 'deployed-drive-key');
  vi.stubGlobal('localStorage', {
    getItem: () => JSON.stringify({ googleApiKey: '  device-key  ' }),
  });
  expect(getConfig().googleApiKey).toBe('device-key');
});
