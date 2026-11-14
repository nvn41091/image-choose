import type { Page } from '@playwright/test';

// Test-only dev module routes. The production bundle has no auth bypass or test flag.
export async function mockSession(page: Page) {
  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `window.google={accounts:{oauth2:{initTokenClient(options){window.testRequestedScopes=options.scope;return {requestAccessToken(){options.callback({access_token:'fixture-token',expires_in:3600,scope:options.scope});}}},hasGrantedAllScopes(){return true;}}}};`,
    }),
  );
  await page.route('**/src/auth.ts', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
    import {signInDrive,clearDriveSession} from '/src/drive.ts';
    const uid=new URL(location.href).searchParams.get('account')||'test-user';
    let user=new URL(location.href).searchParams.has('signedOut')||localStorage.getItem('e2e-signed-out')==='true'?null:{uid,email:uid+'@example.com',displayName:'Test Account'};
    const listeners=new Set();
    export const currentAccount=()=>user;
    export const accountReady=async()=>user;
    export const watchAccount=(next)=>{listeners.add(next);queueMicrotask(()=>next(user));return()=>listeners.delete(next);};
    export async function loginGoogle(){await signInDrive();localStorage.removeItem('e2e-signed-out');user={uid,email:uid+'@example.com',displayName:'Test Account'};listeners.forEach(fn=>fn(user));return {user};}
    export async function logoutGoogle(){clearDriveSession();localStorage.setItem('e2e-signed-out','true');user=null;listeners.forEach(fn=>fn(user));}
  `,
    }),
  );
  await page.route('**/src/cloud.ts', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
    import {currentAccount,accountReady,loginGoogle,logoutGoogle} from '/src/auth.ts';
    import {albumContent,mergeAlbum} from '/src/sync.ts';
    export const cloudUser=currentAccount,cloudReady=accountReady,cloudLogin=loginGoogle,cloudLogout=logoutGoogle;
    const key=()=> 'e2e-cloud:'+currentAccount().uid;
    const read=()=>JSON.parse(localStorage.getItem(key())||'{}');
    const listeners=new Set();
    const notify=()=>{const albums=Object.values(read());listeners.forEach(fn=>fn(albums.map(a=>({id:a.id,name:a.name,revision:a.cloudRevision,updatedAt:a.updatedAt})),albums));};
    export const listCloudAlbums=async()=>Object.values(read()).map(a=>({id:a.id,name:a.name,revision:a.cloudRevision,updatedAt:a.updatedAt}));
    export const activeWorkspace=async()=>localStorage.getItem(key()+':active')||'';
    export const rememberWorkspace=async(id)=>{localStorage.setItem(key()+':active',id);};
    export const pullCloud=async(id)=>{const value=read()[id];return {...value,cloudBase:albumContent(value)};};
    export async function pushCloud(local){
      if(!navigator.onLine)throw new Error('offline');
      const albums=read();const remote=albums[local.id];const merged=remote?mergeAlbum(local,remote):local;
      const saved={...albumContent(merged),updatedAt:local.updatedAt,cloudRevision:(remote?.cloudRevision||0)+1,cloudUid:currentAccount().uid};
      albums[local.id]=saved;localStorage.setItem(key(),JSON.stringify(albums));notify();return {...saved,cloudBase:albumContent(saved)};
    }
    export function observeWorkspaces(next){listeners.add(next);queueMicrotask(notify);const listener=e=>{if(e.key===key())notify();};window.addEventListener('storage',listener);return()=>{listeners.delete(next);window.removeEventListener('storage',listener);};}
    export async function reviewImages(){throw new Error('AI is not part of this fixture');}
  `,
    }),
  );
}
