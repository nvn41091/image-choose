import { useEffect, useRef, type Dispatch, type SetStateAction, type RefObject } from 'react';
import type { Album } from './model';
import { listAlbums, saveAlbum } from './storage';
import { albumContent, mergeAlbum, needsSync } from './sync';
import * as cloud from './cloud';

type Setter<T> = Dispatch<SetStateAction<T>>;
interface Options {
  uid: string;
  album: Album | null;
  loaded: boolean;
  writeAllowed: boolean;
  current: RefObject<Album | null>;
  saveQueue: RefObject<Promise<void>>;
  setAlbum: Setter<Album | null>;
  setAlbums: Setter<Album[]>;
  setCloudAlbums: Setter<cloud.CloudEntry[]>;
  setLoaded: Setter<boolean>;
  setSaveState: Setter<string>;
  notify: (message: string, error?: boolean) => void;
}
export function useWorkspaceSync(o: Options) {
  const latest = useRef(o);
  latest.current = o;
  const pending = useRef(new Map<string, Album>()),
    inFlight = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    alive = useRef(true);
  const lastError = useRef('');
  const rememberedWorkspace = useRef('');
  const key = 'active-album:' + o.uid;
  const upsert = (a: Album) =>
    latest.current.setAlbums((items) =>
      [a, ...items.filter((x) => x.id !== a.id)].sort((a, b) =>
        b.updatedAt.localeCompare(a.updatedAt),
      ),
    );
  const pump = async () => {
    if (inFlight.current || !alive.current || !latest.current.writeAllowed) return;
    if (!navigator.onLine) {
      latest.current.setSaveState('Đã lưu trên thiết bị · chờ kết nối');
      return;
    }
    inFlight.current = true;
    try {
      while (pending.current.size && alive.current) {
        const [id, sent] = pending.current.entries().next().value!;
        pending.current.delete(id);
        latest.current.setSaveState('Đang đồng bộ Firebase…');
        try {
          const remote = await cloud.pushCloud(sent);
          if (!alive.current) return;
          if (latest.current.current.current?.id === id && rememberedWorkspace.current !== id) {
            await cloud.rememberWorkspace(id);
            rememberedWorkspace.current = id;
          }
          lastError.current = '';
          const local =
            latest.current.current.current?.id === id
              ? latest.current.current.current
              : (await listAlbums()).find((a) => a.id === id) || sent;
          if ((local.cloudRevision || 0) > (remote.cloudRevision || 0)) continue;
          const reconciled = mergeAlbum(local, remote, albumContent(sent));
          await saveAlbum(reconciled);
          upsert(reconciled);
          if (latest.current.current.current?.id === id) latest.current.setAlbum(reconciled);
          if (needsSync(reconciled)) pending.current.set(id, reconciled);
          else if (!pending.current.size) latest.current.setSaveState('Đã đồng bộ Firebase');
        } catch (e) {
          const current = latest.current.current.current;
          pending.current.set(id, current?.id === id ? current : sent);
          latest.current.setSaveState(
            navigator.onLine
              ? 'Đã lưu thiết bị · đồng bộ lỗi'
              : 'Đã lưu trên thiết bị · chờ kết nối',
          );
          if (lastError.current !== (e as Error).message) {
            lastError.current = (e as Error).message;
            latest.current.notify(
              'Chưa đồng bộ được Firebase: ' +
                (e as Error).message +
                '. Dữ liệu vẫn được giữ trên thiết bị và sẽ thử lại.',
              true,
            );
          }
          break;
        }
      }
    } finally {
      inFlight.current = false;
    }
  };
  const retry = () => {
    const a = latest.current.current.current;
    if (a && needsSync(a)) pending.current.set(a.id, a);
    void pump();
  };
  useEffect(() => {
    alive.current = true;
    let unsubscribe = () => {};
    void (async () => {
      try {
        const items = await listAlbums();
        let chosen = items.find((a) => a.id === localStorage.getItem(key)) || items[0] || null;
        latest.current.setAlbums(items);
        try {
          const [remoteItems, active] = await Promise.all([
            cloud.listCloudAlbums(),
            cloud.activeWorkspace(),
          ]);
          rememberedWorkspace.current = active;
          latest.current.setCloudAlbums(remoteItems);
          const target =
            remoteItems.find((a) => a.id === active) ||
            [...remoteItems].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
          if (target && !(chosen && needsSync(chosen))) {
            const local = items.find((a) => a.id === target.id);
            const remote = await cloud.pullCloud(target.id);
            chosen = local ? mergeAlbum(local, remote) : remote;
          }
        } catch (e) {
          latest.current.notify('Chưa tải được workspace Firebase: ' + (e as Error).message, true);
        }
        unsubscribe = cloud.observeWorkspaces(
          (entries, changed) => {
            if (!alive.current) return;
            latest.current.setCloudAlbums(entries);
            const local = latest.current.current.current;
            const incoming = changed.find((a) => a.id === local?.id);
            if (local && incoming && (incoming.cloudRevision || 0) > (local.cloudRevision || 0))
              latest.current.setAlbum(mergeAlbum(local, incoming));
          },
          (error) => {
            if (alive.current) {
              latest.current.setSaveState('Đã lưu thiết bị · chờ Firebase');
              latest.current.notify(error.message, true);
            }
          },
        );
        if (!alive.current) return;
        latest.current.setAlbum(chosen);
        latest.current.setLoaded(true);
        latest.current.setSaveState(
          chosen && needsSync(chosen) ? 'Đang chờ đồng bộ Firebase…' : 'Đã đồng bộ Firebase',
        );
        for (const a of items) if (needsSync(a)) pending.current.set(a.id, a);
        void pump();
      } catch (e) {
        latest.current.notify((e as Error).message, true);
        latest.current.setLoaded(true);
      }
    })();
    const online = () => retry();
    const interval = setInterval(() => {
      if (pending.current.size) void pump();
    }, 15000);
    window.addEventListener('online', online);
    return () => {
      alive.current = false;
      unsubscribe();
      clearInterval(interval);
      window.removeEventListener('online', online);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [o.uid]);
  useEffect(() => {
    const a = o.album;
    if (!o.loaded || !a || !o.writeAllowed) return;
    localStorage.setItem(key, a.id);
    document.documentElement.dataset.unsaved = 'true';
    o.saveQueue.current = o.saveQueue.current
      .catch(() => {})
      .then(async () => {
        await saveAlbum(a);
        upsert(a);
        if (latest.current.current.current === a)
          document.documentElement.dataset.unsaved = 'false';
        if (needsSync(a)) {
          pending.current.set(a.id, a);
          latest.current.setSaveState(
            navigator.onLine ? 'Đang đồng bộ Firebase…' : 'Đã lưu trên thiết bị · chờ kết nối',
          );
          if (!timer.current)
            timer.current = setTimeout(() => {
              timer.current = null;
              void pump();
            }, 500);
        } else {
          pending.current.delete(a.id);
          if (!inFlight.current) latest.current.setSaveState('Đã đồng bộ Firebase');
        }
      })
      .catch((e) => {
        o.setSaveState('Chưa lưu được · tải backup ngay');
        o.notify((e as Error).message, true);
      });
  }, [o.album, o.loaded, o.writeAllowed]);
  return { retrySync: retry };
}
