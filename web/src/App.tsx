import { useEffect, useRef, useState, type CSSProperties, type ChangeEvent } from 'react';
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronRight,
  Cloud,
  Download,
  Expand,
  Folder,
  FolderOpen,
  Grid2X2,
  Heart,
  Image,
  Info,
  LayoutGrid,
  LoaderCircle,
  Maximize2,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Star,
  Sun,
  Moon,
  Upload,
  X,
} from 'lucide-react';
import {
  blankProject,
  counts,
  isRaw,
  packageProject,
  parseProject,
  photoAt,
  sortEntries,
  updatePhotos,
  matchRaw,
  type Album,
  type Entry,
  type Photo,
  type Project,
  type Sort,
} from './model';
import {
  deleteAlbum,
  getRecovery,
  importLocalAlbum,
  listAlbums,
  saveAlbum,
  saveRecovery,
} from './storage';
import {
  driveNeedsLogin,
  driveSignedIn,
  loadDrive,
  parseDriveUrl,
  prepareDriveLogin,
  signInDrive,
  signOutDrive,
} from './drive';
import {
  copyByCategory,
  createBackup,
  download,
  entriesFromFiles,
  exportStudio,
  jsonBlob,
  readBackup,
  type Backup,
} from './files';
import { getConfig, saveConfig } from './config';
import { imageBlob, resizeImage, blobDataUrl } from './images';
import type { CloudEntry, Recommendation } from './cloud';
import { BusyContext, Modal } from './Modal';
import { Viewer } from './Viewer';
import { PhotoImage } from './PhotoImage';

type Dialog =
  | ''
  | 'drive'
  | 'settings'
  | 'package'
  | 'export'
  | 'backup'
  | 'restore'
  | 'cloud'
  | 'ai'
  | 'help'
  | 'raw';
const sortOptions: [Sort, string][] = [
  ['name_asc', 'Tên ảnh A → Z'],
  ['name_desc', 'Tên ảnh Z → A'],
  ['score_desc', 'Điểm cao → thấp'],
  ['score_asc', 'Điểm thấp → cao'],
  ['stars_desc', 'Sao nhiều → ít'],
  ['stars_asc', 'Sao ít → nhiều'],
];
const errorText = (e: unknown) =>
  e instanceof Error ? e.message : 'Có lỗi xảy ra. Vui lòng thử lại.';
function App() {
  const [albums, setAlbums] = useState<Album[]>([]),
    [album, setAlbum] = useState<Album | null>(null),
    [loaded, setLoaded] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(''),
    [selection, setSelection] = useState<string[]>([]),
    [tab, setTab] = useState<'all' | 'selected' | 'favorite'>('all');
  const [folder, setFolder] = useState(''),
    [recursive, setRecursive] = useState(false),
    [query, setQuery] = useState(''),
    [categoryFilter, setCategoryFilter] = useState(''),
    [minStars, setMinStars] = useState(0);
  const [sort, setSort] = useState<Sort>(
      () => (localStorage.getItem('sort') as Sort) || 'name_asc',
    ),
    [columns, setColumns] = useState(() => Number(localStorage.getItem('columns')) || 4);
  const [dark, setDark] = useState(() => localStorage.getItem('dark') === 'true'),
    [focusMode, setFocusMode] = useState(false),
    [filtersOpen, setFiltersOpen] = useState(false),
    [inspectorOpen, setInspectorOpen] = useState(false),
    [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(''),
    [toast, setToast] = useState<{ message: string; error: boolean } | null>(null),
    [saveState, setSaveState] = useState('Đang tải dữ liệu…');
  const [viewer, setViewer] = useState<{
    entries: Entry[];
    index: number;
    compare: boolean;
    returnToAi?: boolean;
  } | null>(null);
  const [writeAllowed, setWriteAllowed] = useState(!navigator.locks),
    [otherTab, setOtherTab] = useState(false);
  const [driveUrl, setDriveUrl] = useState(''),
    [googleConnected, setGoogleConnected] = useState(driveSignedIn()),
    [attach, setAttach] = useState(false);
  const [config, setConfig] = useState(getConfig),
    [draftProject, setDraftProject] = useState<Project>(blankProject);
  const [backupImages, setBackupImages] = useState(false),
    [incoming, setIncoming] = useState<Backup | null>(null),
    [restoreMode, setRestoreMode] = useState('data');
  const [cloudAccount, setCloudAccount] = useState(''),
    [cloudAlbums, setCloudAlbums] = useState<CloudEntry[]>([]);
  const [aiScope, setAiScope] = useState('selection'),
    [criteria, setCriteria] = useState(
      'Biểu cảm tự nhiên, khoảnh khắc đẹp, ánh sáng và bố cục hài hòa.',
    ),
    [aiConsent, setAiConsent] = useState(false),
    [aiRunning, setAiRunning] = useState(false),
    [aiProgress, setAiProgress] = useState(''),
    [reviews, setReviews] = useState<Recommendation[]>([]),
    [reviewChecked, setReviewChecked] = useState<string[]>([]),
    [topCount, setTopCount] = useState(20),
    [aiCategory, setAiCategory] = useState('album'),
    [aiStars, setAiStars] = useState(false),
    [aiFavorite, setAiFavorite] = useState(false),
    [aiNotes, setAiNotes] = useState(true);
  const stopAi = useRef(false),
    abort = useRef<AbortController | null>(null),
    current = useRef(album),
    saveQueue = useRef(Promise.resolve());
  const [rawFiles, setRawFiles] = useState<Map<string, File>>(new Map()),
    [rawReport, setRawReport] = useState<ReturnType<typeof matchRaw> | null>(null);
  const localInput = useRef<HTMLInputElement>(null),
    photoInput = useRef<HTMLInputElement>(null),
    backupInput = useRef<HTMLInputElement>(null),
    rawInput = useRef<HTMLInputElement>(null),
    anchor = useRef('');
  current.current = album;
  const notify = (message: string, error = false) => setToast({ message, error });
  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(null), toast.error ? 14000 : 5500);
    return () => clearTimeout(timeout);
  }, [toast]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('dark', String(dark));
  }, [dark]);
  useEffect(() => {
    localStorage.setItem('sort', sort);
  }, [sort]);
  useEffect(() => {
    localStorage.setItem('columns', String(columns));
  }, [columns]);
  useEffect(() => {
    if (!navigator.locks) return;
    let release: () => void = () => {};
    let mounted = true;
    void navigator.locks.request('chon-anh-cuoi-editor', { ifAvailable: true }, async (lock) => {
      if (!mounted) return;
      if (!lock) {
        setOtherTab(true);
        return;
      }
      setWriteAllowed(true);
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    });
    return () => {
      mounted = false;
      release();
    };
  }, []);
  useEffect(() => {
    listAlbums()
      .then((items) => {
        setAlbums(items);
        setAlbum(
          items.find((a) => a.id === localStorage.getItem('active-album')) || items[0] || null,
        );
        setLoaded(true);
        setSaveState('Đã lưu trên thiết bị');
      })
      .catch((e) => {
        notify('Không mở được lưu trữ trình duyệt: ' + errorText(e), true);
        setLoaded(true);
      });
    prepareDriveLogin().catch(() => {});
    const unload = (e: BeforeUnloadEvent) => {
      if (document.documentElement.dataset.unsaved === 'true') {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', unload);
    return () => window.removeEventListener('beforeunload', unload);
  }, []);
  useEffect(() => {
    if (!loaded || !album || !writeAllowed) return;
    localStorage.setItem('active-album', album.id);
    document.documentElement.dataset.unsaved = 'true';
    setSaveState('Đang lưu…');
    const value = album;
    saveQueue.current = saveQueue.current
      .catch(() => {})
      .then(async () => {
        await saveAlbum(value);
        if (current.current === value) {
          setSaveState('Đã lưu trên thiết bị');
          document.documentElement.dataset.unsaved = 'false';
        }
      })
      .catch((e) => {
        setSaveState('Chưa lưu được · tải backup ngay');
        notify('Không lưu được trên thiết bị (có thể hết dung lượng): ' + errorText(e), true);
      });
    setAlbums((items) =>
      [album, ...items.filter((a) => a.id !== album.id)].sort((a, b) =>
        b.updatedAt.localeCompare(a.updatedAt),
      ),
    );
  }, [album, loaded, writeAllowed]);
  const run = async (label: string, work: () => Promise<void>) => {
    setBusy(label);
    try {
      await work();
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) notify(errorText(e), true);
    } finally {
      setBusy('');
    }
  };
  const changeProject = (fn: (p: Project) => Project) =>
    setAlbum((a) =>
      a ? { ...a, project: fn(a.project), updatedAt: new Date().toISOString() } : a,
    );
  const edit = (paths: string[], changes: Partial<Photo>) =>
    changeProject((p) => updatePhotos(p, paths, () => changes));
  const totals = album ? counts(album.project) : {};
  const selectedCount = album
    ? Object.values(album.project.photos).filter((p) => p.category_ids.length).length
    : 0;
  const favoriteCount = album
    ? Object.values(album.project.photos).filter((p) => p.favorite).length
    : 0;
  const categoryChange = (id: string, paths = selection) => {
    const a = current.current;
    if (!a || !paths.length) return;
    const category = a.project.categories.find((c) => c.id === id);
    if (!category) return;
    const missing = paths.filter((path) => !photoAt(a.project, path).category_ids.includes(id));
    if (
      missing.length &&
      category.max_count !== null &&
      counts(a.project)[id] + missing.length > category.max_count &&
      !window.confirm(
        `“${category.name}” sẽ có ${counts(a.project)[id] + missing.length}/${category.max_count} ảnh. Studio có thể tính thêm phí. Bạn muốn chọn thêm?`,
      )
    )
      return;
    changeProject((p) =>
      updatePhotos(p, missing.length ? missing : paths, (photo) => ({
        category_ids: missing.length
          ? [...photo.category_ids, id]
          : photo.category_ids.filter((t) => t !== id),
      })),
    );
  };
  const switchAlbum = (id: string) => {
    const found = albums.find((a) => a.id === id);
    if (found) {
      setAlbum(found);
      setSelection([]);
      setFolder('');
      setTab('all');
      setQuery('');
      setCategoryFilter('');
      setReviews([]);
      setReviewChecked([]);
    }
  };
  const openPackage = () => {
    if (album) {
      setDraftProject(structuredClone(album.project));
      setDialog('package');
    }
  };
  const openDrive = () => {
    setGoogleConnected(driveSignedIn());
    setDriveUrl(album?.driveUrl || '');
    setAttach(false);
    setDialog('drive');
  };
  const openViewer = (entry: Entry) => {
    setViewer({
      entries: visible,
      index: visible.findIndex((e) => e.path === entry.path),
      compare: false,
    });
  };
  const compare = () => {
    if (!album) return;
    const entries = selection
      .map((path) => album.entries.find((e) => e.path === path))
      .filter((e): e is Entry => !!e);
    if (entries.length < 2 || entries.length > 4) {
      notify('Tích từ 2 đến 4 ảnh để so sánh.', true);
      return;
    }
    setViewer({ entries, index: 0, compare: true });
  };
  const filtered = album
    ? album.entries.filter((e) => {
        const p = photoAt(album.project, e.path);
        if ((tab === 'selected' && !p.category_ids.length) || (tab === 'favorite' && !p.favorite))
          return false;
        if (tab === 'all' && folder && !e.path.startsWith(folder + '/')) return false;
        if (
          tab === 'all' &&
          !recursive &&
          e.path.slice(folder ? folder.length + 1 : 0).includes('/')
        )
          return false;
        return (
          (!query ||
            e.path.toLowerCase().includes(query.toLowerCase()) ||
            p.note.toLowerCase().includes(query.toLowerCase())) &&
          (!categoryFilter || p.category_ids.includes(categoryFilter)) &&
          p.stars >= minStars
        );
      })
    : [];
  const visible = album ? sortEntries(filtered, album.project, sort) : [];
  const [page, setPage] = useState(1);
  const pageSize = 60;
  useEffect(() => {
    setPage(1);
  }, [folder, query, categoryFilter, minStars, tab, album?.id, recursive, sort]);
  const shown = visible.slice((page - 1) * pageSize, page * pageSize);
  const folders =
    album && tab === 'all' && !recursive
      ? [
          ...new Set(
            album.entries
              .map((e) => e.path)
              .filter((p) => !folder || p.startsWith(folder + '/'))
              .map((p) => p.slice(folder ? folder.length + 1 : 0))
              .filter((p) => p.includes('/'))
              .map((p) => p.split('/')[0]),
          ),
        ].sort((a, b) => a.localeCompare(b, 'vi'))
      : [];
  const pick = (
    path: string,
    event?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
    toggle = false,
  ) => {
    if (event?.shiftKey && anchor.current) {
      const a = visible.findIndex((e) => e.path === anchor.current),
        b = visible.findIndex((e) => e.path === path);
      if (a >= 0 && b >= 0) {
        setSelection([
          ...new Set([
            ...selection,
            ...visible.slice(Math.min(a, b), Math.max(a, b) + 1).map((e) => e.path),
          ]),
        ]);
        return;
      }
    }
    anchor.current = path;
    setSelection((previous) =>
      toggle || event?.ctrlKey || event?.metaKey
        ? previous.includes(path)
          ? previous.filter((p) => p !== path)
          : [...previous, path]
        : [path],
    );
  };
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (
        dialog ||
        viewer ||
        busy ||
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      )
        return;
      const key = event.key.toLowerCase();
      if (event.ctrlKey && event.shiftKey && key === 'f') {
        event.preventDefault();
        setFocusMode((v) => !v);
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (key === 'f' && album && selection.length)
        changeProject((p) =>
          updatePhotos(p, selection, (photo) => ({ favorite: !photo.favorite })),
        );
      if (key === 'c') compare();
      if (key === 'delete' || key === '0') edit(selection, { category_ids: [] });
      if (event.shiftKey && /^[!@#$%]$/.test(event.key)) {
        const n = '!@#$%'.indexOf(event.key) + 1;
        changeProject((p) =>
          updatePhotos(p, selection, (photo) => ({ stars: photo.stars === n ? 0 : n })),
        );
      } else if (/^[1-9]$/.test(key)) {
        const c = album?.project.categories.find((c) => c.shortcut === Number(key));
        if (c) categoryChange(c.id);
      }
      if (event.key === 'F1') {
        event.preventDefault();
        setDialog('help');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selection, album, dialog, viewer, busy, visible]);
  const importFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    await run('Đang nhập ảnh trên thiết bị…', async () => {
      const { entries, blobs } = entriesFromFiles(files);
      if (!entries.length) throw new Error('Thư mục không có ảnh được hỗ trợ.');
      const tags = files.find(
        (f) =>
          (f.webkitRelativePath ? f.webkitRelativePath.split('/').slice(1).join('/') : f.name) ===
          'photo_tags.json',
      );
      const pack = files.find(
        (f) =>
          (f.webkitRelativePath ? f.webkitRelativePath.split('/').slice(1).join('/') : f.name) ===
          'goi_chup.json',
      );
      const p = tags
        ? parseProject(JSON.parse((await tags.text()).replace(/^\uFEFF/, '')))
        : pack
          ? packageProject(JSON.parse((await pack.text()).replace(/^\uFEFF/, '')))
          : blankProject();
      const next: Album = {
        id: crypto.randomUUID(),
        name: files[0].webkitRelativePath.split('/')[0] || 'Ảnh trên thiết bị',
        source: 'local',
        entries,
        project: p,
        updatedAt: new Date().toISOString(),
      };
      await importLocalAlbum(next, blobs);
      setAlbum(next);
      setSelection([]);
      setFolder('');
      setTab('all');
      notify(`Đã nhập ${entries.length} ảnh. Ảnh được lưu trên trình duyệt này.`);
    });
  };
  const restore = async () => {
    if (!incoming) return;
    await run('Đang khôi phục backup…', async () => {
      if (restoreMode === 'data' && album) {
        await saveRecovery(album);
        const next = { ...album, project: incoming.project, updatedAt: new Date().toISOString() };
        await saveAlbum(next);
        setAlbum(next);
      } else {
        const id = crypto.randomUUID();
        const next: Album = {
          id,
          name: incoming.project.customer_name || 'Backup từ PC',
          source: 'local',
          entries: [...incoming.images].map(([path, b]) => ({
            path,
            name: path.split('/').pop()!,
            size: b.size,
          })),
          project: incoming.project,
          updatedAt: new Date().toISOString(),
        };
        await importLocalAlbum(next, incoming.images);
        setAlbum(next);
      }
      setSelection([]);
      setFolder('');
      setTab('all');
      setDialog('');
      setIncoming(null);
      notify('Đã khôi phục lựa chọn, sao, ghi chú và điểm ảnh.');
    });
  };
  const startAi = async () => {
    if (!album || !aiConsent) return;
    const snapshot = album;
    const paths =
      aiScope === 'all'
        ? album.entries
        : aiScope === 'folder'
          ? album.entries.filter((e) => !folder || e.path.startsWith(folder + '/'))
          : album.entries.filter((e) => selection.includes(e.path));
    if (!paths.length) {
      notify('Phạm vi này chưa có ảnh.', true);
      return;
    }
    setAiRunning(true);
    stopAi.current = false;
    setReviews([]);
    setReviewChecked([]);
    const results: Recommendation[] = [];
    let processed = 0;
    let skipped = 0;
    try {
      const cloud = await import('./cloud');
      if (!(await cloud.cloudReady()))
        throw new Error('Đăng nhập Firebase trong mục Đồng bộ trước khi dùng AI.');
      for (let i = 0; i < paths.length; i += 12) {
        if (stopAi.current) break;
        const batch: { path: string; data: string }[] = [];
        for (const entry of paths.slice(i, i + 12)) {
          setAiProgress(`Đang chuẩn bị ảnh ${processed + batch.length + 1}/${paths.length}`);
          try {
            const blob = await imageBlob(snapshot, entry, true);
            batch.push({
              path: entry.path,
              data: await blobDataUrl(await resizeImage(blob, 1280)),
            });
          } catch {
            skipped++;
            processed++;
          }
        }
        if (!batch.length) continue;
        if (stopAi.current) break;
        setAiProgress(`Đang đánh giá ${batch.length} ảnh · ${processed}/${paths.length} đã xong`);
        const response = await cloud.reviewImages(batch, criteria);
        processed += batch.length;
        results.push(...response.photos);
        setReviews([...results].sort((a, b) => b.score - a.score));
        changeProject((p) => {
          let next = p;
          for (const item of response.photos)
            next = updatePhotos(next, [item.path], () => ({ ai_score: item.score }));
          return next;
        });
      }
      setAiProgress(
        `${stopAi.current ? 'Đã dừng' : 'Hoàn tất'} · ${results.length} ảnh đã đánh giá${skipped ? ' · ' + skipped + ' ảnh lỗi đã bỏ qua' : ''}. Kết quả đã lưu; chưa tự gán loại.`,
      );
    } catch (e) {
      setAiProgress(
        `${errorText(e)} Đã giữ ${results.length} kết quả hoàn tất; không tự gửi lại yêu cầu.`,
      );
    } finally {
      setAiRunning(false);
    }
  };
  const applyAi = () => {
    if (!album) return;
    const items = reviews.filter((r) => reviewChecked.includes(r.path));
    if (!items.length) return;
    if (aiCategory) {
      const c = album.project.categories.find((c) => c.id === aiCategory);
      const extra = items.filter(
        (r) => !photoAt(album.project, r.path).category_ids.includes(aiCategory),
      ).length;
      if (
        c &&
        extra &&
        c.max_count !== null &&
        totals[c.id] + extra > c.max_count &&
        !confirm(`Vượt giới hạn ${c.name}: ${totals[c.id] + extra}/${c.max_count}. Áp dụng?`)
      )
        return;
    }
    changeProject((p) => {
      let next = p;
      for (const item of items)
        next = updatePhotos(next, [item.path], (old) => ({
          ...(aiCategory ? { category_ids: [...new Set([...old.category_ids, aiCategory])] } : {}),
          ...(aiStars ? { stars: Math.max(1, Math.ceil(item.score / 20)) } : {}),
          ...(aiFavorite ? { favorite: true } : {}),
          ...(aiNotes && item.editing_note && !old.note.includes(item.editing_note)
            ? { note: [old.note, item.editing_note].filter(Boolean).join('\n') }
            : {}),
        }));
      return next;
    });
    notify(`Đã áp dụng cho ${items.length} ảnh.`);
  };
  const focused =
    album && selection.length === 1
      ? album.entries.find((e) => e.path === selection[0])
      : undefined;
  const focusedPhoto = album && focused ? photoAt(album.project, focused.path) : null;
  const previewReview = (path: string) => {
    if (aiRunning) return;
    const entry = album?.entries.find((e) => e.path === path);
    if (entry) {
      setDialog('');
      setViewer({ entries: [entry], index: 0, compare: false, returnToAi: true });
    }
  };
  const selectedLabel = selection.length
    ? `${selection.length} ảnh đang chọn`
    : 'Chọn một ảnh để bắt đầu';
  return (
    <BusyContext.Provider
      value={{ message: busy, cancel: abort.current ? () => abort.current?.abort() : undefined }}
    >
      <div className={'app ' + (focusMode ? 'focus-mode' : '')}>
        <input
          ref={localInput}
          type="file"
          className="hidden-input"
          {...{ webkitdirectory: '', directory: '' }}
          multiple
          onChange={importFiles}
        />
        <input
          ref={photoInput}
          type="file"
          className="hidden-input"
          accept="image/*"
          multiple
          onChange={importFiles}
        />
        <input
          ref={backupInput}
          type="file"
          className="hidden-input"
          accept=".zip,.json"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file)
              void run('Đang kiểm tra backup…', async () => {
                const result = await readBackup(file);
                setIncoming(result);
                setRestoreMode(result.images.size || !album ? 'new' : 'data');
                setDialog('restore');
              });
          }}
        />
        <input
          ref={rawInput}
          type="file"
          className="hidden-input"
          {...{ webkitdirectory: '', directory: '' }}
          multiple
          onChange={(e) => {
            if (!album) return;
            const files = new Map<string, File>();
            for (const f of Array.from(e.target.files || [])) {
              const path = f.webkitRelativePath.split('/').slice(1).join('/') || f.name;
              if (isRaw(path)) files.set(path, f);
            }
            setRawFiles(files);
            setRawReport(matchRaw(album.project, [...files.keys()]));
            e.target.value = '';
          }}
        />
        <header className="app-header">
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setTab('all');
              setFolder('');
            }}
          >
            <span className="brand-mark">
              <Heart size={21} />
            </span>
            <span>
              khoảnh khắc<small>CHỌN ẢNH CƯỚI</small>
            </span>
          </a>
          <div className="header-divider" />
          <span className="workspace-label">Không gian của bạn</span>
          <div className="header-actions">
            <button
              className="text-button cloud-header"
              aria-label="Đồng bộ"
              onClick={() => {
                setDialog('cloud');
                void run('Đang mở đồng bộ…', async () => {
                  const c = await import('./cloud');
                  const u = await c.cloudReady();
                  setCloudAccount(u?.email || '');
                  if (u) setCloudAlbums(await c.listCloudAlbums());
                });
              }}
            >
              <Cloud size={17} />
              <span>Đồng bộ</span>
            </button>
            <button
              className="icon-button"
              aria-label={dark ? 'Giao diện sáng' : 'Giao diện tối'}
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <button
              className="icon-button"
              aria-label="Cấu hình"
              onClick={() => {
                setConfig(getConfig());
                setDialog('settings');
              }}
            >
              <Settings2 size={19} />
            </button>
            <button
              className="avatar"
              aria-label="Hướng dẫn sử dụng"
              onClick={() => setDialog('help')}
            >
              KK
            </button>
          </div>
        </header>
        <div className="workspace">
          <aside className="sidebar">
            <div className="sidebar-title">
              THƯ VIỆN ẢNH{' '}
              <button className="icon-button" aria-label="Thêm album Drive" onClick={openDrive}>
                <Plus size={17} />
              </button>
            </div>
            <nav>
              <button
                className={tab === 'all' ? 'nav-item active' : 'nav-item'}
                onClick={() => {
                  setTab('all');
                  setSelection([]);
                }}
              >
                <LayoutGrid size={18} />
                Tất cả ảnh<span>{album?.entries.length || 0}</span>
              </button>
              <button
                className={tab === 'selected' ? 'nav-item active' : 'nav-item'}
                onClick={() => {
                  setTab('selected');
                  setSelection([]);
                }}
              >
                <CheckCheck size={18} />
                Ảnh đã chọn<span>{selectedCount}</span>
              </button>
              <button
                className={tab === 'favorite' ? 'nav-item active' : 'nav-item'}
                onClick={() => {
                  setTab('favorite');
                  setSelection([]);
                }}
              >
                <Heart size={18} />
                Yêu thích<span>{favoriteCount}</span>
              </button>
            </nav>
            <div className="sidebar-section">
              <div className="sidebar-title">BỘ ẢNH CỦA BẠN</div>
              {albums.map((a) => (
                <div key={a.id} className={'album-row ' + (a.id === album?.id ? 'current' : '')}>
                  <button onClick={() => switchAlbum(a.id)} title={a.name}>
                    <Folder size={16} />
                    <span>{a.name}</span>
                  </button>
                  <button
                    className="delete-album"
                    aria-label={'Xóa bộ ảnh ' + a.name}
                    onClick={() => {
                      if (
                        confirm(
                          'Xóa bộ ảnh và dữ liệu lưu trên trình duyệt này? Hãy tải backup trước nếu cần.',
                        )
                      )
                        void run('Đang xóa bộ ảnh…', async () => {
                          await saveQueue.current;
                          await deleteAlbum(a.id);
                          setAlbums((items) => items.filter((x) => x.id !== a.id));
                          if (a.id === album?.id) {
                            setAlbum(albums.find((x) => x.id !== a.id) || null);
                            setSelection([]);
                          }
                          notify('Đã xóa bộ ảnh trên thiết bị.');
                        });
                    }}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
              <button className="add-album" onClick={openDrive}>
                <Plus size={16} /> Mở link Google Drive
              </button>
            </div>
            <div className="sidebar-section">
              <div className="sidebar-title">CÔNG CỤ</div>
              <button className="nav-item" onClick={() => backupInput.current?.click()}>
                <Upload size={17} />
                Nhập backup từ PC
              </button>
              <button className="nav-item" onClick={() => localInput.current?.click()}>
                <FolderOpen size={17} />
                Mở thư mục máy tính
              </button>
              <button className="nav-item" onClick={() => photoInput.current?.click()}>
                <Image size={17} />
                Chọn ảnh từ thiết bị
              </button>
              <button
                className="nav-item"
                disabled={!album}
                onClick={() => {
                  setDialog('raw');
                  setRawReport(null);
                  setRawFiles(new Map());
                }}
              >
                <Grid2X2 size={17} />
                Đối chiếu RAW
              </button>
            </div>
            <div className="sidebar-tip">
              <Heart size={21} />
              <p>
                Giữ lại những khoảnh khắc
                <br />
                bạn muốn nhớ mãi.
              </p>
              <button onClick={() => setDialog('help')}>
                Hướng dẫn chọn ảnh <ArrowRight size={13} />
              </button>
            </div>
            <div className="sidebar-footer">
              <span className="status-dot" /> {saveState}
            </div>
          </aside>
          <main className="main">
            <div className="page-heading">
              <div>
                <div className="eyebrow">MỖI BỨC ẢNH, MỘT KỶ NIỆM</div>
                <h1>
                  {tab === 'selected'
                    ? 'Những ảnh bạn đã chọn'
                    : tab === 'favorite'
                      ? 'Khoảnh khắc yêu thích'
                      : album?.project.customer_name || 'Bộ ảnh của bạn'}
                  <span className="title-dot">.</span>
                </h1>
                <p>
                  {album
                    ? `${album.name} · ${album.entries.length.toLocaleString('vi')} ảnh để cùng xem lại`
                    : 'Cùng xem, cùng chọn những khoảnh khắc đẹp nhất.'}
                </p>
              </div>
              <div className="heading-actions">
                <button className="button subtle" onClick={openDrive}>
                  <Plus size={17} />
                  <span>Mở Google Drive</span>
                </button>
                <button
                  className="button primary"
                  disabled={!album}
                  onClick={() => setDialog('export')}
                >
                  <ArrowDownToLine size={17} />
                  <span>Hoàn tất & xuất</span>
                </button>
              </div>
            </div>
            {album && (
              <>
                {album.source === 'drive' && !googleConnected && driveNeedsLogin() && (
                  <div className="connection-card drive-reconnect">
                    <Cloud size={24} />
                    <div>
                      <strong>Kết nối Google Drive để tải ảnh</strong>
                      <small>
                        Lựa chọn đã lưu vẫn được giữ. Kết nối lại để tiếp tục xem ảnh trên thiết bị
                        này.
                      </small>
                    </div>
                    <button
                      className="button primary"
                      onClick={() =>
                        void run('Đang kết nối Google Drive…', async () => {
                          await signInDrive();
                          setGoogleConnected(driveSignedIn());
                        })
                      }
                    >
                      Kết nối lại Google Drive
                    </button>
                  </div>
                )}
                <section className="package-bar">
                  <div className="package-label">
                    <span className="tiny-icon">
                      <Check size={16} />
                    </span>
                    <div>
                      <strong>Gói ảnh của bạn</strong>
                      <small>{selectedCount} khoảnh khắc đã chọn</small>
                    </div>
                  </div>
                  <div className="package-items">
                    {album.project.categories.map((c) => (
                      <button
                        key={c.id}
                        className={
                          'package-item ' +
                          (c.max_count !== null && totals[c.id] > c.max_count ? 'over' : '')
                        }
                        onClick={() => setCategoryFilter(categoryFilter === c.id ? '' : c.id)}
                      >
                        <span>
                          <i style={{ background: c.color }} />
                          {c.name}
                        </span>
                        <strong>
                          {totals[c.id] || 0}
                          <small> / {c.max_count ?? '∞'}</small>
                        </strong>
                        <div className="progress-track">
                          <i
                            style={{
                              width: `${c.max_count === null ? (totals[c.id] ? 28 : 0) : Math.min(100, ((totals[c.id] || 0) / (c.max_count || 1)) * 100)}%`,
                              background: c.color,
                            }}
                          />
                        </div>
                      </button>
                    ))}
                  </div>
                  <button
                    className="icon-button"
                    aria-label="Sửa loại ảnh và gói cưới"
                    onClick={openPackage}
                  >
                    <SlidersHorizontal size={17} />
                  </button>
                </section>
                <div className="mobile-tabs">
                  <button className={tab === 'all' ? 'active' : ''} onClick={() => setTab('all')}>
                    Tất cả ({album.entries.length})
                  </button>
                  <button
                    className={tab === 'selected' ? 'active' : ''}
                    onClick={() => setTab('selected')}
                  >
                    Đã chọn ({selectedCount})
                  </button>
                  <button
                    className={tab === 'favorite' ? 'active' : ''}
                    onClick={() => setTab('favorite')}
                  >
                    Yêu thích
                  </button>
                  <select
                    aria-label="Đổi bộ ảnh"
                    value={album.id}
                    onChange={(e) => switchAlbum(e.target.value)}
                  >
                    {albums.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="gallery-toolbar">
                  <div className="gallery-title">
                    <strong>
                      {tab === 'all'
                        ? 'Tất cả ảnh'
                        : tab === 'selected'
                          ? 'Ảnh đã chọn'
                          : 'Yêu thích'}
                    </strong>
                    <span>{visible.length}</span>
                  </div>
                  <div className="gallery-controls">
                    <label className="search-field">
                      <Search size={16} />
                      <input
                        placeholder="Tìm tên ảnh, ghi chú…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <select
                      aria-label="Sắp xếp ảnh"
                      value={sort}
                      onChange={(e) => setSort(e.target.value as Sort)}
                    >
                      {sortOptions.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <button
                      className={'icon-button ' + (filtersOpen ? 'active' : '')}
                      aria-label="Bộ lọc"
                      onClick={() => setFiltersOpen(!filtersOpen)}
                    >
                      <SlidersHorizontal size={18} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Chế độ tập trung"
                      onClick={() => setFocusMode(!focusMode)}
                    >
                      <Expand size={18} />
                    </button>
                    <div className="menu-anchor">
                      <button
                        className="icon-button"
                        aria-label="Tác vụ khác"
                        onClick={() => setMenu(!menu)}
                      >
                        <MoreHorizontal size={20} />
                      </button>
                      {menu && (
                        <div className="dropdown" onClick={() => setMenu(false)}>
                          <button onClick={openPackage}>Loại ảnh và gói cưới</button>
                          <button onClick={() => setDialog('backup')}>
                            Sao lưu dữ liệu và ảnh
                          </button>
                          <button onClick={() => backupInput.current?.click()}>
                            Khôi phục ZIP / JSON từ PC
                          </button>
                          <button onClick={() => localInput.current?.click()}>
                            Mở thư mục máy tính
                          </button>
                          <button onClick={() => photoInput.current?.click()}>
                            Chọn ảnh từ thiết bị
                          </button>
                          <button
                            onClick={() => {
                              setRawReport(null);
                              setDialog('raw');
                            }}
                          >
                            Đối chiếu và xuất RAW
                          </button>
                          <button
                            onClick={() => {
                              setDialog('cloud');
                              void run('Đang mở đồng bộ…', async () => {
                                const c = await import('./cloud');
                                const u = await c.cloudReady();
                                setCloudAccount(u?.email || '');
                                if (u) setCloudAlbums(await c.listCloudAlbums());
                              });
                            }}
                          >
                            Đồng bộ Firebase
                          </button>
                          <button onClick={() => setDark(!dark)}>Đổi giao diện sáng / tối</button>
                          <button onClick={() => setDialog('help')}>Hướng dẫn và phím tắt</button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                {filtersOpen && (
                  <div className="filters">
                    <label>
                      Loại ảnh
                      <select
                        value={categoryFilter}
                        onChange={(e) => setCategoryFilter(e.target.value)}
                      >
                        <option value="">Tất cả loại</option>
                        {album.project.categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Số sao
                      <select
                        value={minStars}
                        onChange={(e) => setMinStars(Number(e.target.value))}
                      >
                        <option value={0}>Tất cả</option>
                        {[1, 2, 3, 4, 5].map((n) => (
                          <option key={n} value={n}>
                            Từ {n} sao
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Ảnh mỗi hàng
                      <input
                        type="range"
                        min={2}
                        max={10}
                        value={columns}
                        onChange={(e) => setColumns(Number(e.target.value))}
                      />
                      {columns}
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={recursive}
                        onChange={(e) => setRecursive(e.target.checked)}
                      />
                      Kèm thư mục con
                    </label>
                    <button
                      className="text-button"
                      onClick={() => {
                        setQuery('');
                        setCategoryFilter('');
                        setMinStars(0);
                      }}
                    >
                      Xóa bộ lọc
                    </button>
                  </div>
                )}
                <div className="selection-toolbar">
                  <div className="breadcrumbs">
                    <button onClick={() => setFolder('')}>
                      <Folder size={14} />
                      {album.name}
                    </button>
                    {folder
                      .split('/')
                      .filter(Boolean)
                      .map((part, i) => (
                        <span key={i}>
                          <ChevronRight size={13} />
                          <button
                            onClick={() =>
                              setFolder(
                                folder
                                  .split('/')
                                  .slice(0, i + 1)
                                  .join('/'),
                              )
                            }
                          >
                            {part}
                          </button>
                        </span>
                      ))}
                  </div>
                  <div>
                    <button
                      className="text-button"
                      onClick={() =>
                        setSelection([...new Set([...selection, ...shown.map((e) => e.path)])])
                      }
                    >
                      Chọn trang
                    </button>
                    <button
                      className="text-button"
                      disabled={!selection.length}
                      onClick={() => setSelection([])}
                    >
                      Bỏ chọn
                    </button>
                    <button
                      className="text-button ai-button"
                      onClick={() => {
                        setAiScope(selection.length ? 'selection' : 'folder');
                        setDialog('ai');
                      }}
                    >
                      <Sparkles size={14} /> Đánh giá ảnh
                    </button>
                  </div>
                </div>
                <div className="photo-grid" style={{ '--columns': columns } as CSSProperties}>
                  {folders.map((name) => (
                    <button
                      key={'folder/' + name}
                      className="folder-card"
                      onClick={() => {
                        setFolder(folder ? folder + '/' + name : name);
                        setSelection([]);
                      }}
                    >
                      <Folder size={37} />
                      <strong>{name}</strong>
                      <span>
                        Mở thư mục <ChevronRight size={13} />
                      </span>
                    </button>
                  ))}
                  {shown.map((entry) => {
                    const p = photoAt(album.project, entry.path),
                      picked = selection.includes(entry.path);
                    return (
                      <article
                        key={entry.path}
                        className={'photo-card ' + (picked ? 'picked' : '')}
                      >
                        <div
                          className="photo-frame"
                          onClick={(e) => pick(entry.path, e)}
                          onDoubleClick={() => openViewer(entry)}
                        >
                          <PhotoImage album={album} entry={entry} />
                          <button
                            className={'pick-photo ' + (picked ? 'checked' : '')}
                            aria-label={'Chọn ' + entry.name}
                            aria-pressed={picked}
                            onClick={(e) => {
                              e.stopPropagation();
                              pick(entry.path, undefined, true);
                            }}
                          >
                            {picked && <Check size={13} />}
                          </button>
                          <button
                            className={'favorite-photo ' + (p.favorite ? 'is-favorite' : '')}
                            aria-label={'Yêu thích ' + entry.name}
                            aria-pressed={p.favorite}
                            onClick={(e) => {
                              e.stopPropagation();
                              edit([entry.path], { favorite: !p.favorite });
                            }}
                          >
                            <Heart size={17} fill={p.favorite ? 'currentColor' : 'none'} />
                          </button>
                          <button
                            className="open-photo"
                            aria-label={'Xem lớn ' + entry.name}
                            onClick={(e) => {
                              e.stopPropagation();
                              openViewer(entry);
                            }}
                          >
                            <Maximize2 size={17} />
                          </button>
                          {p.ai_score !== null && (
                            <span className="score-badge">
                              {p.ai_score}
                              <small>/100</small>
                            </span>
                          )}
                          {!!p.stars && <span className="card-stars">{'★'.repeat(p.stars)}</span>}
                        </div>
                        <div className="photo-details">
                          <div className="photo-name">
                            <span title={entry.path}>{entry.name}</span>
                            {p.note && <span title={p.note} className="note-dot" />}
                          </div>
                          <div className="card-tags">
                            {p.category_ids.length ? (
                              p.category_ids.map((id) => {
                                const c = album.project.categories.find((c) => c.id === id);
                                return (
                                  c && (
                                    <span
                                      key={id}
                                      style={{ color: c.color, background: c.color + '16' }}
                                    >
                                      {c.name}
                                    </span>
                                  )
                                );
                              })
                            ) : (
                              <button
                                onClick={() =>
                                  categoryChange(album.project.categories[0]?.id, [entry.path])
                                }
                              >
                                <Plus size={11} /> Chọn loại ảnh
                              </button>
                            )}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
                {!visible.length && !folders.length && (
                  <div className="empty-results">
                    <Image size={36} />
                    <h3>
                      {album.entries.length
                        ? 'Chưa có ảnh phù hợp'
                        : 'Backup này chỉ có dữ liệu lựa chọn'}
                    </h3>
                    <p>
                      {album.entries.length
                        ? 'Thử đổi thư mục hoặc xóa bộ lọc.'
                        : 'Mở link Drive rồi tích dùng lựa chọn hiện tại để nối lại ảnh theo đường dẫn.'}
                    </p>
                    <button
                      className="button subtle"
                      onClick={
                        album.entries.length
                          ? () => {
                              setQuery('');
                              setCategoryFilter('');
                              setMinStars(0);
                              setTab('all');
                              setFolder('');
                            }
                          : openDrive
                      }
                    >
                      {album.entries.length ? 'Xem tất cả ảnh' : 'Mở Google Drive'}
                    </button>
                  </div>
                )}
                {visible.length > pageSize && (
                  <div className="pagination">
                    <button
                      className="button subtle"
                      disabled={page === 1}
                      onClick={() => {
                        setPage(page - 1);
                        window.scrollTo({ top: 0 });
                      }}
                    >
                      <ArrowLeft size={16} />
                      Trước
                    </button>
                    <span>
                      Trang {page} / {Math.ceil(visible.length / pageSize)}
                    </span>
                    <button
                      className="button subtle"
                      disabled={page * pageSize >= visible.length}
                      onClick={() => {
                        setPage(page + 1);
                        window.scrollTo({ top: 0 });
                      }}
                    >
                      Sau
                      <ArrowRight size={16} />
                    </button>
                  </div>
                )}
                <div className="gallery-footer">
                  <span>
                    {saveState} ·{' '}
                    {album.source === 'drive' ? 'Nguồn Google Drive' : 'Ảnh trên thiết bị'}
                  </span>
                  <span>Tích ảnh để chọn · Nhấp đúp để xem lớn</span>
                </div>
              </>
            )}
            {!album && loaded && (
              <section className="welcome">
                <div className="welcome-art">
                  <div className="art-frame back">
                    <Heart size={66} strokeWidth={1} />
                  </div>
                  <div className="art-frame front">
                    <Image size={70} strokeWidth={1} />
                    <span>Our favorite moments</span>
                  </div>
                  <span className="art-spark">✧</span>
                </div>
                <span className="eyebrow">BẮT ĐẦU MỘT BỘ ẢNH</span>
                <h2>
                  Những kỷ niệm đẹp,
                  <br />
                  được chọn cùng nhau.
                </h2>
                <p>
                  Dán link Google Drive để mở bộ ảnh của bạn.
                  <br />
                  Hoặc tiếp tục những lựa chọn đã lưu từ app PC.
                </p>
                <button className="button primary" onClick={openDrive}>
                  <FolderOpen size={18} />
                  Mở link Google Drive
                </button>
                <div className="welcome-links">
                  <button onClick={() => backupInput.current?.click()}>
                    <Upload size={15} />
                    Nhập backup từ PC
                  </button>
                  <span>·</span>
                  <button onClick={() => photoInput.current?.click()}>
                    <Image size={15} />
                    Chọn ảnh trên thiết bị
                  </button>
                </div>
                <div className="welcome-features">
                  <span>
                    <Check size={14} />
                    Tự lưu lựa chọn
                  </span>
                  <span>
                    <Check size={14} />
                    Điện thoại & máy tính
                  </span>
                  <span>
                    <Check size={14} />
                    Xuất cho studio
                  </span>
                </div>
              </section>
            )}
          </main>
          {album && (
            <aside className={'inspector ' + (inspectorOpen ? 'mobile-open' : '')}>
              <div className="inspector-heading">
                <h3>Chọn & ghi chú</h3>
                <button
                  className="icon-button mobile-only"
                  aria-label="Đóng bảng chỉnh ảnh"
                  onClick={() => setInspectorOpen(false)}
                >
                  <X size={18} />
                </button>
                <SlidersHorizontal size={16} />
              </div>
              <div className="inspector-content">
                {focused ? (
                  <div className="inspector-preview" onDoubleClick={() => openViewer(focused)}>
                    <PhotoImage album={album} entry={focused} />
                    <button aria-label="Xem ảnh đang chọn" onClick={() => openViewer(focused)}>
                      <Maximize2 size={15} />
                    </button>
                  </div>
                ) : (
                  <div className="inspector-placeholder">
                    <Image size={32} strokeWidth={1} />
                    <p>
                      {selection.length ? 'Chỉnh nhiều ảnh cùng lúc' : 'Chọn ảnh trong bộ sưu tập'}
                    </p>
                  </div>
                )}
                <strong className="focused-name">{focused?.name || selectedLabel}</strong>
                <p className="focused-path">
                  {focused?.path || 'Các thay đổi sẽ tự lưu trên thiết bị'}
                </p>
                <div className="inspector-section">
                  <label className="field-title">
                    LOẠI ẢNH <span>{selection.length ? `${selection.length} ảnh` : ''}</span>
                  </label>
                  <div className="category-choices">
                    {album.project.categories.map((c) => {
                      const all =
                        !!selection.length &&
                        selection.every((path) =>
                          photoAt(album.project, path).category_ids.includes(c.id),
                        );
                      return (
                        <button
                          key={c.id}
                          disabled={!selection.length}
                          className={all ? 'category-choice checked' : 'category-choice'}
                          onClick={() => categoryChange(c.id)}
                        >
                          <i style={{ background: c.color }} />
                          <span>{c.name}</span>
                          <kbd>{c.shortcut}</kbd>
                          <span className="category-check">{all && <Check size={12} />}</span>
                        </button>
                      );
                    })}
                  </div>
                  <button
                    className="text-button muted"
                    disabled={!selection.length}
                    onClick={() => edit(selection, { category_ids: [] })}
                  >
                    Bỏ tất cả loại
                  </button>
                </div>
                <div className="inspector-section">
                  <label className="field-title">ĐÁNH GIÁ & YÊU THÍCH</label>
                  <div className="rating-line">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button
                        disabled={!selection.length}
                        key={n}
                        aria-label={'Đánh giá ' + n + ' sao'}
                        className={'star ' + (focusedPhoto && focusedPhoto.stars >= n ? 'on' : '')}
                        onClick={() =>
                          changeProject((p) =>
                            updatePhotos(p, selection, (old) => ({
                              stars: old.stars === n ? 0 : n,
                            })),
                          )
                        }
                      >
                        ★
                      </button>
                    ))}
                    <button
                      className={'inspector-heart ' + (focusedPhoto?.favorite ? 'is-favorite' : '')}
                      disabled={!selection.length}
                      aria-label="Đánh dấu yêu thích"
                      onClick={() =>
                        changeProject((p) =>
                          updatePhotos(p, selection, (old) => ({ favorite: !old.favorite })),
                        )
                      }
                    >
                      <Heart size={20} fill={focusedPhoto?.favorite ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                  <label className="score-field">
                    Điểm ảnh
                    <input
                      aria-label="Điểm ảnh"
                      type="number"
                      min={0}
                      max={100}
                      placeholder="Chưa chấm"
                      disabled={!focused}
                      value={focusedPhoto?.ai_score ?? ''}
                      onChange={(e) => {
                        const n = e.target.value === '' ? null : Number(e.target.value);
                        if (n === null || (Number.isInteger(n) && n >= 0 && n <= 100))
                          edit(selection, { ai_score: n });
                      }}
                    />
                    <small>/ 100</small>
                  </label>
                </div>
                <div className="inspector-section">
                  <label className="field-title" htmlFor="notes">
                    GHI CHÚ HẬU KỲ
                  </label>
                  <textarea
                    id="notes"
                    rows={4}
                    disabled={!focused}
                    placeholder={
                      selection.length > 1
                        ? 'Chọn một ảnh để viết ghi chú'
                        : 'Ví dụ: làm sáng nhẹ, giữ màu tự nhiên…'
                    }
                    value={focusedPhoto?.note || ''}
                    onChange={(e) => edit(selection, { note: e.target.value })}
                  />
                  <small className="hint">Studio sẽ nhận ghi chú khi bạn xuất danh sách.</small>
                </div>
                <button
                  className="button subtle full-width"
                  disabled={!selection.length}
                  onClick={() => {
                    setAiScope('selection');
                    setDialog('ai');
                  }}
                >
                  <Sparkles size={16} />
                  Đánh giá và đề xuất ảnh
                </button>
              </div>
              <div className="inspector-bottom">
                <span className="status-dot" />
                {saveState}
              </div>
            </aside>
          )}
        </div>
        {selection.length > 0 && album && !viewer && (
          <div className="bulk-bar">
            <button aria-label="Bỏ chọn ảnh" onClick={() => setSelection([])}>
              <X size={17} />
            </button>
            <strong>{selection.length} ảnh đang chọn</strong>
            <span className="bulk-divider" />
            <button disabled={selection.length < 2 || selection.length > 4} onClick={compare}>
              <Grid2X2 size={16} />
              <span>So sánh</span>
            </button>
            <button onClick={() => setInspectorOpen(true)}>
              <SlidersHorizontal size={16} />
              <span>Loại & ghi chú</span>
            </button>
            <button
              onClick={() =>
                changeProject((p) =>
                  updatePhotos(p, selection, (old) => ({ favorite: !old.favorite })),
                )
              }
            >
              <Heart size={16} />
            </button>
          </div>
        )}
        {focusMode && (
          <button className="exit-focus button" onClick={() => setFocusMode(false)}>
            <X size={16} />
            Thoát tập trung
          </button>
        )}
        {toast && (
          <div
            className={'toast ' + (toast.error ? 'error' : '')}
            role={toast.error ? 'alert' : 'status'}
          >
            <Info size={18} />
            <span>{toast.message}</span>
            <button aria-label="Ẩn thông báo" onClick={() => setToast(null)}>
              <X size={16} />
            </button>
          </div>
        )}
        {busy && (
          <div className="busy-overlay" role="status">
            <LoaderCircle className="spinner" />
            <p>{busy}</p>
            {abort.current && (
              <button className="button subtle" onClick={() => abort.current?.abort()}>
                Hủy mở Drive
              </button>
            )}
          </div>
        )}
        {otherTab && (
          <div className="busy-overlay" role="alert">
            <Info size={30} />
            <p>
              Bộ chọn ảnh đang mở ở một tab khác. Đóng tab đó rồi tải lại trang này để tránh ghi đè
              dữ liệu.
            </p>
            <button className="button primary" onClick={() => window.location.reload()}>
              Tải lại trang
            </button>
          </div>
        )}
        {viewer && album && (
          <Viewer
            album={album}
            entries={viewer.entries}
            initial={viewer.index}
            compare={viewer.compare}
            onClose={() => {
              if (viewer.returnToAi) setDialog('ai');
              setViewer(null);
            }}
            onEdit={edit}
            onCategory={categoryChange}
          />
        )}
        {dialog === 'drive' && (
          <Modal title="Mở bộ ảnh từ Google Drive" onClose={() => setDialog('')}>
            <p className="dialog-intro">
              Link thư mục hoặc ảnh. Các thư mục con được đọc tự động và giữ đường dẫn để khớp dữ
              liệu từ PC.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run('Đang đọc Google Drive…', async () => {
                  parseDriveUrl(driveUrl);
                  if (driveNeedsLogin()) {
                    setBusy('Đang kết nối Google để đọc bộ ảnh…');
                    await signInDrive();
                    setGoogleConnected(driveSignedIn());
                    setBusy('Đang đọc Google Drive…');
                  }
                  abort.current = new AbortController();
                  try {
                    const result = await loadDrive(driveUrl, abort.current.signal, setBusy);
                    const existing = albums.find((a) => a.id === result.id);
                    const p = attach && album ? album.project : existing?.project || result.project;
                    setAlbum({
                      ...result,
                      project: p,
                      cloudRevision: existing?.cloudRevision,
                      cloudUid: existing?.cloudUid,
                    });
                    setFolder('');
                    setSelection([]);
                    setTab('all');
                    setDialog('');
                    notify(`Đã mở ${result.entries.length} ảnh từ Drive.`);
                  } finally {
                    abort.current = null;
                  }
                });
              }}
            >
              <label className="field">
                Link Google Drive
                <input
                  autoFocus
                  type="url"
                  placeholder="https://drive.google.com/drive/folders/…"
                  required
                  value={driveUrl}
                  onChange={(e) => setDriveUrl(e.target.value)}
                />
              </label>
              {album && (
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={attach}
                    onChange={(e) => setAttach(e.target.checked)}
                  />
                  Dùng lựa chọn của bộ ảnh hiện tại (khớp bằng đường dẫn)
                </label>
              )}
              <div className="connection-card">
                <Cloud size={24} />
                <div>
                  <strong>
                    {googleConnected ? 'Đã kết nối Google Drive' : 'Đăng nhập Google để mở bộ ảnh'}
                  </strong>
                  <small>Chỉ xin quyền đọc. Không đổi tên, sửa hoặc xóa ảnh trên Drive.</small>
                </div>
                <button
                  className="button subtle"
                  type="button"
                  onClick={() =>
                    void run(
                      googleConnected ? 'Đang ngắt kết nối…' : 'Đang đăng nhập Google…',
                      async () => {
                        if (googleConnected) {
                          await signOutDrive();
                          setGoogleConnected(false);
                        } else {
                          await signInDrive();
                          setGoogleConnected(true);
                        }
                      },
                    )
                  }
                >
                  {googleConnected ? 'Ngắt kết nối' : 'Kết nối Google'}
                </button>
              </div>
              <p className="hint">
                Nút mở ảnh sẽ yêu cầu kết nối Google nếu bạn chưa cấp quyền Drive. Đăng nhập ở mục
                Đồng bộ Firebase chỉ đồng bộ lựa chọn, chưa cấp quyền đọc ảnh. Thư mục công khai
                cũng có thể mở bằng API key trong Cấu hình.
              </p>
              <p className="hint">
                Nếu Google chặn đăng nhập trong trình duyệt nhúng của ứng dụng, hãy mở website này
                bằng Chrome hoặc Safari. Tài khoản Google cần có quyền đọc thư mục.
              </p>
              <div className="dialog-actions">
                <button
                  className="text-button"
                  type="button"
                  onClick={() => {
                    setConfig(getConfig());
                    setDialog('settings');
                  }}
                >
                  Cấu hình Google
                </button>
                <button className="button primary" type="submit">
                  <FolderOpen size={16} />
                  {driveNeedsLogin() ? 'Kết nối Google & mở ảnh' : 'Mở bộ ảnh'}
                </button>
              </div>
            </form>
          </Modal>
        )}
        {dialog === 'settings' && (
          <Modal title="Cấu hình kết nối" onClose={() => setDialog('')}>
            <p className="dialog-intro">
              Chỉ nhập cấu hình công khai. Không nhập Client Secret, Service Account hoặc OpenAI API
              key ở đây.
            </p>
            <label className="field">
              Google OAuth Client ID
              <input
                value={config.googleClientId}
                onChange={(e) => setConfig({ ...config, googleClientId: e.target.value })}
                placeholder="….apps.googleusercontent.com"
              />
            </label>
            <label className="field">
              Google API key (tùy chọn, thư mục công khai)
              <input
                value={config.googleApiKey}
                onChange={(e) => setConfig({ ...config, googleApiKey: e.target.value })}
              />
            </label>
            <label className="field">
              Firebase web config (JSON)
              <textarea
                rows={6}
                value={config.firebaseConfig}
                onChange={(e) => setConfig({ ...config, firebaseConfig: e.target.value })}
              />
            </label>
            <label className="field">
              Khu vực Cloud Functions
              <input
                value={config.region}
                onChange={(e) => setConfig({ ...config, region: e.target.value })}
              />
            </label>
            <p className="hint">
              Thêm <code>{window.location.origin}</code> vào JavaScript origins của Google OAuth và
              Authorized domains của Firebase Auth. Khóa API công khai nên giới hạn theo domain và
              API.
            </p>
            <div className="dialog-actions">
              <button
                className="button primary"
                onClick={() =>
                  void run('Đang lưu cấu hình…', async () => {
                    saveConfig(config);
                    await saveQueue.current;
                    window.location.reload();
                  })
                }
              >
                Lưu & tải lại trang
              </button>
            </div>
          </Modal>
        )}
        {dialog === 'package' && album && (
          <Modal title="Loại ảnh và gói cưới" wide onClose={() => setDialog('')}>
            <label className="field">
              Tên khách hàng
              <input
                value={draftProject.customer_name}
                onChange={(e) =>
                  setDraftProject({ ...draftProject, customer_name: e.target.value })
                }
              />
            </label>
            <p className="hint">
              Bỏ trống giới hạn nghĩa là không giới hạn. Số 0 là gói không có ảnh thuộc loại đó.
            </p>
            <div className="category-editor">
              {draftProject.categories.map((c, index) => (
                <div className="category-editor-row" key={c.id}>
                  <input
                    aria-label={'Màu ' + c.name}
                    type="color"
                    value={c.color}
                    onChange={(e) =>
                      setDraftProject((p) => ({
                        ...p,
                        categories: p.categories.map((x, i) =>
                          i === index ? { ...x, color: e.target.value } : x,
                        ),
                      }))
                    }
                  />
                  <input
                    aria-label="Tên loại ảnh"
                    value={c.name}
                    onChange={(e) =>
                      setDraftProject((p) => ({
                        ...p,
                        categories: p.categories.map((x, i) =>
                          i === index ? { ...x, name: e.target.value } : x,
                        ),
                      }))
                    }
                  />
                  <label>
                    Phím
                    <input
                      type="number"
                      min={1}
                      max={9}
                      value={c.shortcut}
                      onChange={(e) =>
                        setDraftProject((p) => ({
                          ...p,
                          categories: p.categories.map((x, i) =>
                            i === index ? { ...x, shortcut: Number(e.target.value) } : x,
                          ),
                        }))
                      }
                    />
                  </label>
                  <label>
                    Tối đa
                    <input
                      placeholder="∞"
                      type="number"
                      min={0}
                      value={c.max_count ?? ''}
                      onChange={(e) =>
                        setDraftProject((p) => ({
                          ...p,
                          categories: p.categories.map((x, i) =>
                            i === index
                              ? {
                                  ...x,
                                  max_count: e.target.value === '' ? null : Number(e.target.value),
                                }
                              : x,
                          ),
                        }))
                      }
                    />
                  </label>
                  <button
                    className="icon-button"
                    aria-label={'Xóa loại ' + c.name}
                    onClick={() => {
                      if (confirm(`Xóa loại “${c.name}” khỏi gói và các ảnh đang gán?`))
                        setDraftProject((p) => ({
                          ...p,
                          categories: p.categories.filter((x) => x.id !== c.id),
                          photos: Object.fromEntries(
                            Object.entries(p.photos).map(([path, photo]) => [
                              path,
                              {
                                ...photo,
                                category_ids: photo.category_ids.filter((id) => id !== c.id),
                              },
                            ]),
                          ),
                        }));
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              ))}
            </div>
            <button
              className="text-button"
              disabled={draftProject.categories.length >= 9}
              onClick={() =>
                setDraftProject((p) => ({
                  ...p,
                  categories: [
                    ...p.categories,
                    {
                      id: crypto.randomUUID(),
                      name: 'Loại mới',
                      color: '#527899',
                      shortcut: [1, 2, 3, 4, 5, 6, 7, 8, 9].find(
                        (n) => !p.categories.some((c) => c.shortcut === n),
                      )!,
                      max_count: null,
                    },
                  ],
                }))
              }
            >
              <Plus size={16} />
              Thêm loại ảnh
            </button>
            <div className="dialog-actions">
              <button
                className="button primary"
                onClick={() => {
                  try {
                    const project = parseProject(draftProject);
                    changeProject(() => project);
                    setDialog('');
                  } catch (e) {
                    notify(errorText(e), true);
                  }
                }}
              >
                Lưu gói ảnh
              </button>
            </div>
          </Modal>
        )}
        {dialog === 'export' && album && (
          <Modal title="Gửi những lựa chọn cho studio" onClose={() => setDialog('')}>
            <div className="export-summary">
              <CheckCheck size={30} />
              <strong>{selectedCount}</strong>
              <span>ảnh đã gán loại · gồm cả ảnh ở thư mục khác và ảnh đang ẩn</span>
            </div>
            {album.project.categories.map((c) => (
              <div className="summary-row" key={c.id}>
                <span>
                  <i style={{ background: c.color }} />
                  {c.name}
                </span>
                <strong>
                  {totals[c.id] || 0}
                  {c.max_count !== null ? ` / ${c.max_count}` : ''}
                </strong>
              </div>
            ))}
            <p className="hint">
              ZIP gồm Excel tổng hợp và từng loại, lightroom.txt và photo_tags.json tương thích app
              PC. Ảnh tạm vắng vẫn có trong danh sách.
            </p>
            <div className="dialog-actions">
              <button
                className="button subtle"
                onClick={() => download(jsonBlob(album.project), 'photo_tags.json')}
              >
                Chỉ tải JSON
              </button>
              <button
                className="button primary"
                onClick={() =>
                  void run('Đang xuất gói studio…', async () => {
                    download(await exportStudio(album.project), 'Lua-chon-studio.zip');
                    notify('Đã tạo gói gửi studio.');
                  })
                }
              >
                <Download size={16} />
                Tải gói studio
              </button>
            </div>
          </Modal>
        )}
        {dialog === 'backup' && album && (
          <Modal title="Sao lưu dữ liệu và ảnh" onClose={() => setDialog('')}>
            <p className="dialog-intro">
              Backup giữ nguyên tên khách hàng, loại ảnh, giới hạn, sao, yêu thích, ghi chú, điểm và
              bản ghi ảnh tạm vắng. Có thể khôi phục trên app PC.
            </p>
            <label className="check-label">
              <input
                type="checkbox"
                checked={backupImages}
                onChange={(e) => setBackupImages(e.target.checked)}
              />
              Kèm toàn bộ {album.entries.length} ảnh gốc
            </label>
            <p className="hint">
              ZIP kèm ảnh tối đa 256 MB để dùng ổn định trên điện thoại. Với bộ lớn, sao lưu dữ liệu
              và giữ ảnh trên Drive. Đóng trang hoặc ngắt mạng sẽ dừng tải.
            </p>
            <div className="dialog-actions">
              <button
                className="button subtle"
                onClick={() =>
                  void run('Đang chuẩn bị ảnh theo loại…', async () =>
                    download(await copyByCategory(album, setBusy), 'Anh-theo-loai.zip'),
                  )
                }
              >
                Tải ảnh theo loại
              </button>
              <button
                className="button primary"
                onClick={() =>
                  void run('Đang sao lưu…', async () => {
                    download(
                      await createBackup(album, backupImages, setBusy),
                      `Sao-luu-${new Date().toISOString().slice(0, 10)}.zip`,
                    );
                    notify('Đã tạo bản sao lưu tương thích PC.');
                  })
                }
              >
                <Download size={16} />
                Tải backup ZIP
              </button>
            </div>
            <button
              className="text-button"
              onClick={() =>
                void run('Đang đọc dữ liệu trước khôi phục…', async () => {
                  const previous = await getRecovery(album.id);
                  if (!previous) throw new Error('Chưa có dữ liệu trước khôi phục.');
                  download(jsonBlob(previous.project), 'Truoc-khoi-phuc.json');
                })
              }
            >
              Tải dữ liệu trước lần khôi phục gần nhất
            </button>
          </Modal>
        )}
        {dialog === 'restore' && incoming && (
          <Modal
            title="Kiểm tra bản khôi phục"
            onClose={() => {
              setDialog('');
              setIncoming(null);
            }}
          >
            <p className="dialog-intro">
              Khách hàng: <strong>{incoming.project.customer_name || 'Chưa đặt tên'}</strong>
            </p>
            <div className="summary-row">
              <span>Bản ghi lựa chọn</span>
              <strong>{Object.keys(incoming.project.photos).length}</strong>
            </div>
            <div className="summary-row">
              <span>Ảnh trong backup</span>
              <strong>{incoming.images.size}</strong>
            </div>
            {album && (
              <label className="radio-choice">
                <input
                  type="radio"
                  name="restore"
                  value="data"
                  checked={restoreMode === 'data'}
                  onChange={() => setRestoreMode('data')}
                />
                <div>
                  <strong>Thay dữ liệu bộ ảnh hiện tại</strong>
                  <small>
                    Khớp{' '}
                    {
                      Object.keys(incoming.project.photos).filter((path) =>
                        album.entries.some((e) => e.path === path),
                      ).length
                    }{' '}
                    bản ghi; bản ghi chưa khớp vẫn được giữ. Tự lưu bản dữ liệu trước khôi phục trên
                    thiết bị.
                  </small>
                </div>
              </label>
            )}
            <label className="radio-choice">
              <input
                type="radio"
                name="restore"
                value="new"
                checked={restoreMode === 'new'}
                onChange={() => setRestoreMode('new')}
              />
              <div>
                <strong>Mở thành bộ ảnh mới</strong>
                <small>
                  {incoming.images.size
                    ? 'Nhập cả ảnh vào lưu trữ trình duyệt.'
                    : 'Chỉ nhập dữ liệu; mở Drive sau và tích dùng lựa chọn hiện tại.'}
                </small>
              </div>
            </label>
            <div className="dialog-actions">
              <button className="button primary" onClick={restore}>
                Khôi phục lựa chọn
              </button>
            </div>
          </Modal>
        )}
        {dialog === 'cloud' && (
          <Modal title="Tiếp tục trên mọi thiết bị" onClose={() => setDialog('')}>
            <p className="dialog-intro">
              Đồng bộ lựa chọn qua Firebase theo tài khoản Google của bạn. Ảnh gốc vẫn ở Drive;
              backup ảnh trên thiết bị cần nhập lại nếu chuyển máy.
            </p>
            {cloudAccount ? (
              <div className="signed-in">
                <span className="status-dot" />
                {cloudAccount}
                <button
                  className="text-button"
                  onClick={() =>
                    void run('Đang đăng xuất…', async () => {
                      await (await import('./cloud')).cloudLogout();
                      setCloudAccount('');
                      setCloudAlbums([]);
                    })
                  }
                >
                  Đăng xuất
                </button>
              </div>
            ) : (
              <button
                className="button primary full-width"
                onClick={() =>
                  void run('Đang đăng nhập đồng bộ…', async () => {
                    const c = await import('./cloud');
                    const result = await c.cloudLogin();
                    setCloudAccount(result.user.email || result.user.uid);
                    setCloudAlbums(await c.listCloudAlbums());
                  })
                }
              >
                Đăng nhập Google để đồng bộ
              </button>
            )}
            {cloudAccount && (
              <>
                <button
                  className="button primary full-width"
                  disabled={!album}
                  onClick={() =>
                    void run('Đang lưu lên Firebase…', async () => {
                      const c = await import('./cloud');
                      const next = await c.pushCloud(album!);
                      setAlbum(next);
                      setCloudAlbums(await c.listCloudAlbums());
                      notify('Đã lưu lựa chọn lên Firebase.');
                    })
                  }
                >
                  <Cloud size={16} />
                  Lưu bộ ảnh hiện tại lên Firebase
                </button>
                <div className="section-heading">
                  Bộ ảnh trên Firebase
                  <button
                    className="text-button"
                    onClick={() =>
                      void run('Đang tải danh sách…', async () =>
                        setCloudAlbums(await (await import('./cloud')).listCloudAlbums()),
                      )
                    }
                  >
                    Tải lại
                  </button>
                </div>
                {cloudAlbums.map((item) => (
                  <div className="cloud-album" key={item.id}>
                    <Folder size={22} />
                    <div>
                      <strong>{item.name}</strong>
                      <small>
                        {new Date(item.updatedAt).toLocaleString('vi')} · bản {item.revision}
                      </small>
                    </div>
                    <button
                      className="button subtle"
                      onClick={() => {
                        if (
                          !confirm(
                            'Tải bản Firebase về? Dữ liệu cùng bộ ảnh trên thiết bị sẽ được thay thế và giữ một bản trước khôi phục.',
                          )
                        )
                          return;
                        void run('Đang tải bản Firebase…', async () => {
                          const next = await (await import('./cloud')).pullCloud(item.id);
                          const previous = albums.find((a) => a.id === next.id);
                          if (previous) await saveRecovery(previous);
                          setAlbum(next);
                          setSelection([]);
                          setFolder('');
                          setTab('all');
                          setDialog('');
                          notify('Đã tải lựa chọn. Kết nối Google Drive để xem ảnh riêng tư.');
                        });
                      }}
                    >
                      Tải về
                    </button>
                  </div>
                ))}
              </>
            )}
            <p className="hint">
              Lưu và tải là thao tác chủ động. Nếu thiết bị khác đã cập nhật, web sẽ yêu cầu tải bản
              cloud trước để tránh ghi đè. Đây là bản lưu riêng của tài khoản, không phải album chia
              sẻ cộng tác.
            </p>
          </Modal>
        )}
        {dialog === 'ai' && album && (
          <Modal
            title="Đánh giá và đề xuất ảnh"
            wide
            locked={aiRunning}
            onClose={() => setDialog('')}
          >
            <div className="ai-intro">
              <Sparkles size={24} />
              <p>
                Đánh giá biểu cảm, khoảnh khắc, bố cục và ánh sáng. Điểm giữa các nhóm chỉ để tham
                khảo; kiểm tra lại độ nét và ảnh trùng trước khi chốt.
              </p>
            </div>
            <div className="form-row">
              <label className="field">
                Phạm vi
                <select
                  disabled={aiRunning}
                  value={aiScope}
                  onChange={(e) => setAiScope(e.target.value)}
                >
                  <option value="selection">Ảnh đang chọn ({selection.length})</option>
                  <option value="folder">
                    Thư mục hiện tại, kèm thư mục con (
                    {album.entries.filter((e) => !folder || e.path.startsWith(folder + '/')).length}
                    )
                  </option>
                  <option value="all">Toàn bộ bộ ảnh ({album.entries.length})</option>
                </select>
              </label>
            </div>
            <label className="field">
              Tiêu chí
              <textarea
                disabled={aiRunning}
                maxLength={2000}
                rows={2}
                value={criteria}
                onChange={(e) => setCriteria(e.target.value)}
              />
            </label>
            <p className="hint">
              Cần triển khai Firebase Function reviewPhotos và cho phép UID tài khoản. Dùng OpenAI
              API riêng, tính phí API; không dùng gói ChatGPT của app PC. Chỉ gửi ảnh JPEG thu nhỏ
              tối đa 1280 px, đã bỏ EXIF/GPS, cùng tiêu chí. Không gửi tên tệp, đường dẫn hoặc ghi
              chú. Khóa OpenAI nằm ở Firebase Secret.
            </p>
            <label className="check-label">
              <input
                type="checkbox"
                checked={aiConsent}
                disabled={aiRunning}
                onChange={(e) => setAiConsent(e.target.checked)}
              />
              Tôi đồng ý gửi ảnh cho OpenAI và sử dụng hạn mức API đã cấu hình.
            </label>
            <div className="dialog-actions">
              {aiRunning ? (
                <button
                  className="button subtle"
                  onClick={() => {
                    stopAi.current = true;
                    setAiProgress('Đang dừng sau nhóm hiện tại…');
                  }}
                >
                  Dừng sau nhóm hiện tại
                </button>
              ) : (
                <button className="button primary" disabled={!aiConsent} onClick={startAi}>
                  <Sparkles size={16} />
                  Đánh giá ảnh
                </button>
              )}
            </div>
            {aiProgress && (
              <p className="ai-progress" role="status">
                {aiRunning && <LoaderCircle className="spinner" size={15} />} {aiProgress}
              </p>
            )}
            {reviews.length > 0 && (
              <>
                <div className="review-tools">
                  <label>
                    Số ảnh đề xuất{' '}
                    <input
                      type="number"
                      min={1}
                      max={reviews.length}
                      value={topCount}
                      onChange={(e) => setTopCount(Math.max(1, Number(e.target.value)))}
                    />
                  </label>
                  <button
                    className="button subtle"
                    onClick={() =>
                      setReviewChecked(
                        [...reviews]
                          .sort((a, b) => b.score - a.score)
                          .slice(0, topCount)
                          .map((r) => r.path),
                      )
                    }
                  >
                    Chọn ảnh điểm cao nhất
                  </button>
                  <button className="text-button" onClick={() => setReviewChecked([])}>
                    Bỏ tích
                  </button>
                </div>
                <div className="review-table">
                  <table>
                    <thead>
                      <tr>
                        <th />
                        <th>Ảnh</th>
                        <th>
                          <button
                            onClick={() =>
                              setReviews([...reviews].sort((a, b) => b.score - a.score))
                            }
                          >
                            Điểm ↓
                          </button>
                        </th>
                        <th>
                          <button
                            onClick={() =>
                              setReviews(
                                [...reviews].sort(
                                  (a, b) =>
                                    photoAt(album.project, b.path).stars -
                                    photoAt(album.project, a.path).stars,
                                ),
                              )
                            }
                          >
                            Sao ↓
                          </button>
                        </th>
                        <th>Nhận xét & hậu kỳ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reviews.map((r) => (
                        <tr key={r.path}>
                          <td>
                            <input
                              type="checkbox"
                              checked={reviewChecked.includes(r.path)}
                              onChange={(e) =>
                                setReviewChecked(
                                  e.target.checked
                                    ? [...reviewChecked, r.path]
                                    : reviewChecked.filter((p) => p !== r.path),
                                )
                              }
                            />
                          </td>
                          <td>
                            <button
                              className="text-button"
                              disabled={aiRunning}
                              onClick={() => previewReview(r.path)}
                            >
                              {r.path}
                            </button>
                          </td>
                          <td>{r.score}</td>
                          <td>{photoAt(album.project, r.path).stars || '—'}</td>
                          <td>
                            {r.reason}
                            <small>{r.editing_note}</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="ai-apply">
                  <label>
                    Gán loại
                    <select value={aiCategory} onChange={(e) => setAiCategory(e.target.value)}>
                      <option value="">Không gán loại</option>
                      {album.project.categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={aiStars}
                      onChange={(e) => setAiStars(e.target.checked)}
                    />
                    Ghi đè sao
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={aiFavorite}
                      onChange={(e) => setAiFavorite(e.target.checked)}
                    />
                    Yêu thích
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={aiNotes}
                      onChange={(e) => setAiNotes(e.target.checked)}
                    />
                    Thêm gợi ý vào ghi chú
                  </label>
                  <button
                    className="button primary"
                    disabled={aiRunning || !reviewChecked.length}
                    onClick={applyAi}
                  >
                    Áp dụng cho {reviewChecked.length} ảnh đã tích
                  </button>
                </div>
              </>
            )}
          </Modal>
        )}
        {dialog === 'raw' && album && (
          <Modal title="Đối chiếu và sao chép RAW" wide onClose={() => setDialog('')}>
            <p className="dialog-intro">
              Chọn thư mục RAW trên máy tính. Web tìm CR2, CR3, NEF, ARW theo đường dẫn cùng tên
              trước, sau đó theo tên duy nhất. Ảnh nguồn giữ nguyên; kết quả tải thành ZIP chia thư
              mục theo loại.
            </p>
            <button className="button subtle" onClick={() => rawInput.current?.click()}>
              <FolderOpen size={16} />
              Chọn thư mục RAW
            </button>
            {rawReport && (
              <>
                <div className="export-summary">
                  <strong>{Object.keys(rawReport.matches).length}</strong>
                  <span>ảnh đã khớp / {rawFiles.size} tệp RAW</span>
                </div>
                {rawReport.issues.length > 0 && (
                  <div className="raw-issues">
                    {rawReport.issues.map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </div>
                )}
                <p className="hint">
                  Ảnh thiếu hoặc có nhiều kết quả sẽ được bỏ qua. Gói ZIP tối đa 256 MB; dùng app PC
                  để sao chép bộ RAW lớn.
                </p>
                <div className="dialog-actions">
                  <button
                    className="button primary"
                    disabled={!Object.keys(rawReport.matches).length}
                    onClick={() =>
                      void run('Đang tạo gói RAW…', async () =>
                        download(
                          await copyByCategory(album, setBusy, {
                            files: rawFiles,
                            matches: rawReport.matches,
                          }),
                          'RAW-theo-loai.zip',
                        ),
                      )
                    }
                  >
                    Tải RAW đã khớp
                  </button>
                </div>
              </>
            )}
          </Modal>
        )}
        {dialog === 'help' && (
          <Modal title="Chọn những khoảnh khắc của bạn" onClose={() => setDialog('')}>
            <ol className="help-steps">
              <li>
                Mở link Google Drive và kết nối Google nếu thư mục riêng tư. Hoặc nhập backup ZIP /
                photo_tags.json từ app PC.
              </li>
              <li>
                Tích ảnh, gán loại trong bảng Chọn & ghi chú. Bạn có thể đánh sao, yêu thích, ghi
                điểm và yêu cầu hậu kỳ.
              </li>
              <li>
                Tích 2–4 ảnh rồi bấm So sánh. Dùng con lăn, kéo hoặc chụm hai ngón tay để phóng to
                đồng bộ.
              </li>
              <li>Bấm Hoàn tất & xuất để tải Excel, Lightroom và JSON gửi studio.</li>
              <li>
                Dùng Đồng bộ để lưu lựa chọn lên Firebase và tải về trên thiết bị khác. Tải backup
                định kỳ; xóa dữ liệu trình duyệt sẽ xóa bản lưu trên thiết bị.
              </li>
            </ol>
            <div className="shortcut-list">
              <span>
                <kbd>1–9</kbd>Gán / bỏ loại
              </span>
              <span>
                <kbd>Shift + 1–5</kbd>Đánh sao
              </span>
              <span>
                <kbd>F</kbd>Yêu thích
              </span>
              <span>
                <kbd>C</kbd>So sánh
              </span>
              <span>
                <kbd>0 / Delete</kbd>Bỏ loại
              </span>
              <span>
                <kbd>Ctrl + Shift + F</kbd>Tập trung
              </span>
              <span>
                <kbd>← →</kbd>Chuyển ảnh trong trình xem
              </span>
              <span>
                <kbd>Esc</kbd>Đóng trình xem
              </span>
            </div>
            <p className="hint">
              Điện thoại: dùng nút tích ở góc ảnh, nút mở lớn ở góc dưới, và thanh “Loại & ghi chú”
              khi đã chọn ảnh. Trình duyệt hỗ trợ tốt JPG, PNG và WebP; TIFF có thể cần chuyển sang
              JPG trước.
            </p>
          </Modal>
        )}
      </div>
    </BusyContext.Provider>
  );
}
export default App;
