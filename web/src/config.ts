export interface Config {
  googleClientId: string;
  googleApiKey: string;
  firebaseConfig: string;
  region: string;
}
export function getConfig(): Config {
  let local: Partial<Config> = {};
  try {
    local = JSON.parse(localStorage.getItem('web-config') || '{}');
  } catch {
    /* defaults */
  }
  return {
    googleClientId:
      local.googleClientId ??
      (import.meta.env.VITE_GOOGLE_CLIENT_ID ||
        '40087392130-d9qquuudeqt0dfc715u0sg8tllh91lvt.apps.googleusercontent.com'),
    googleApiKey: local.googleApiKey?.trim() || import.meta.env.VITE_GOOGLE_API_KEY || '',
    firebaseConfig:
      local.firebaseConfig ??
      (import.meta.env.VITE_FIREBASE_CONFIG ||
        JSON.stringify({
          apiKey: 'AIzaSyAb7uQB_K7G64QCt-CWse2-ySpLaaWSU4c',
          authDomain: 'image-choose.firebaseapp.com',
          projectId: 'image-choose',
          storageBucket: 'image-choose.firebasestorage.app',
          messagingSenderId: '40087392130',
          appId: '1:40087392130:web:235c5c23f1f39e7421c99b',
        })),
    region: local.region ?? import.meta.env.VITE_FIREBASE_REGION ?? 'asia-southeast1',
  };
}
export function saveConfig(config: Config) {
  if (config.firebaseConfig.trim()) {
    const value = JSON.parse(config.firebaseConfig);
    if (!value.projectId || !value.apiKey || !value.authDomain || !value.appId)
      throw new Error('Firebase config cần projectId, apiKey, authDomain và appId.');
  }
  localStorage.setItem('web-config', JSON.stringify(config));
}
