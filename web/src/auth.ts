import { getApps, initializeApp } from 'firebase/app';
import {
  GoogleAuthProvider,
  initializeAuth,
  indexedDBLocalPersistence,
  browserLocalPersistence,
  onAuthStateChanged,
  signInWithCredential,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth';
import { getConfig } from './config';
import { clearDriveSession, signInDrive } from './drive';
export type Account = Pick<User, 'uid' | 'email' | 'displayName'>;
export function firebaseApp() {
  const raw = getConfig().firebaseConfig;
  if (!raw.trim()) throw new Error('Chưa cấu hình Firebase để đăng nhập.');
  return getApps()[0] || initializeApp(JSON.parse(raw));
}
let client: Auth | undefined;
export function authClient() {
  return (client ||= initializeAuth(firebaseApp(), {
    persistence: [indexedDBLocalPersistence, browserLocalPersistence],
  }));
}
export const currentAccount = () => authClient().currentUser;
export const watchAccount = (next: (user: User | null) => void, error: (error: Error) => void) =>
  onAuthStateChanged(authClient(), next, error);
export async function loginGoogle() {
  const token = await signInDrive();
  return signInWithCredential(authClient(), GoogleAuthProvider.credential(null, token));
}
export async function logoutGoogle() {
  clearDriveSession();
  await signOut(authClient());
}
export async function accountReady() {
  await authClient().authStateReady();
  return currentAccount();
}
