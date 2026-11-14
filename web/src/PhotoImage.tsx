import { useEffect, useRef, useState } from 'react';
import { ImageOff, LoaderCircle, RotateCw } from 'lucide-react';
import { imageBlob } from './images';
import { DRIVE_SESSION_EVENT } from './drive';
import type { Album, Entry } from './model';

export function PhotoImage({
  album,
  entry,
  full = false,
}: {
  album: Album;
  entry: Entry;
  full?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(full);
  const [src, setSrc] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (album.source !== 'drive') return;
    const reconnect = () => setRetry((value) => value + 1);
    window.addEventListener(DRIVE_SESSION_EVENT, reconnect);
    return () => window.removeEventListener(DRIVE_SESSION_EVENT, reconnect);
  }, [album.id, album.source]);
  useEffect(() => {
    if (full) return;
    const observer = new IntersectionObserver(
      (items) => {
        if (items.some((i) => i.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '180px' },
    );
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, [full]);
  useEffect(() => {
    if (!visible) return;
    let alive = true,
      url = '';
    setSrc('');
    setError('');
    imageBlob(album, entry, full)
      .then((blob) => {
        if (alive) {
          url = URL.createObjectURL(blob);
          setSrc(url);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [album.id, entry.path, full, visible, retry]);
  return (
    <div ref={host} className="photo-image">
      {src ? (
        <img
          src={src}
          alt={entry.name}
          draggable={false}
          onError={() => {
            setSrc('');
            setError('Trình duyệt không đọc được ảnh. Thử ảnh JPG/PNG/WebP.');
          }}
        />
      ) : error ? (
        <div className="image-error" title={error}>
          <ImageOff size={23} />
          <small>{error}</small>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setRetry(retry + 1);
            }}
          >
            <RotateCw size={13} /> Thử lại
          </button>
        </div>
      ) : (
        <LoaderCircle className="spinner" size={20} />
      )}
    </div>
  );
}
