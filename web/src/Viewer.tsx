import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Heart, Minus, Plus, RotateCcw, X } from 'lucide-react';
import { PhotoImage } from './PhotoImage';
import { photoAt, type Album, type Entry, type Photo } from './model';

export function Viewer({
  album,
  entries,
  initial,
  compare,
  onClose,
  onEdit,
  onCategory,
}: {
  album: Album;
  entries: Entry[];
  initial: number;
  compare: boolean;
  onClose: () => void;
  onEdit: (paths: string[], change: Partial<Photo>) => void;
  onCategory: (id: string, paths: string[]) => void;
}) {
  const [index, setIndex] = useState(initial),
    [active, setActive] = useState(0);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const points = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ distance: number; scale: number } | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const current = compare ? entries : entries.slice(index, index + 1),
    focus = current[active] || current[0];
  const p = photoAt(album.project, focus.path);
  const step = (amount: number) => {
    setIndex((i) => (i + amount + entries.length) % entries.length);
    setView({ scale: 1, x: 0, y: 0 });
  };
  useEffect(() => {
    const el = host.current!;
    const wheel = (event: WheelEvent) => {
      if ((event.target as HTMLElement).closest('.viewer-pane')) {
        event.preventDefault();
        zoom(event.deltaY < 0 ? 1.12 : 1 / 1.12);
      }
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  }, []);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    host.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopImmediatePropagation();
        onClose();
      }
      if (
        (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) &&
        e.key !== 'Tab'
      )
        return;
      if (!compare && e.key === 'ArrowRight') step(1);
      if (!compare && e.key === 'ArrowLeft') step(-1);
      if (e.key.toLowerCase() === 'f')
        onEdit([focus.path], { favorite: !photoAt(album.project, focus.path).favorite });
      const n = Number(e.code.replace('Digit', ''));
      if (e.shiftKey && n >= 1 && n <= 5) {
        onEdit([focus.path], { stars: p.stars === n ? 0 : n });
      } else if (!e.shiftKey && n >= 1 && n <= 9) {
        const c = album.project.categories.find((c) => c.shortcut === n);
        if (c) onCategory(c.id, [focus.path]);
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const controls = host.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),textarea,input',
        );
        if (controls?.length) {
          let at = Array.from(controls).indexOf(document.activeElement as HTMLElement);
          at = (at + (e.shiftKey ? -1 : 1) + controls.length) % controls.length;
          controls[at].focus();
        }
      }
    };
    window.addEventListener('keydown', handler, true);
    return () => {
      window.removeEventListener('keydown', handler, true);
      previous?.focus();
    };
  }, [index, active, album.project]);
  const zoom = (factor: number) =>
    setView((v) => ({
      ...v,
      scale: Math.max(1, Math.min(8, v.scale * factor)),
      ...(v.scale * factor <= 1 ? { x: 0, y: 0 } : {}),
    }));
  return (
    <div
      ref={host}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label={compare ? 'So sánh ảnh' : 'Xem ảnh lớn'}
      className="viewer"
    >
      <header className="viewer-header">
        <div>
          <strong>{compare ? `So sánh ${entries.length} ảnh` : focus.name}</strong>
          <small>
            {compare
              ? 'Phóng to và di chuyển đồng bộ · chạm ảnh để chỉnh lựa chọn'
              : `${index + 1} / ${entries.length} · ${focus.path}`}
          </small>
        </div>
        <div className="viewer-tools">
          <button aria-label="Thu nhỏ" onClick={() => zoom(1 / 1.3)}>
            <Minus size={19} />
          </button>
          <span>{Math.round(view.scale * 100)}%</span>
          <button aria-label="Phóng to" onClick={() => zoom(1.3)}>
            <Plus size={19} />
          </button>
          <button aria-label="Đặt lại góc nhìn" onClick={() => setView({ scale: 1, x: 0, y: 0 })}>
            <RotateCcw size={19} />
          </button>
          <button aria-label="Đóng trình xem" onClick={onClose}>
            <X size={23} />
          </button>
        </div>
      </header>
      <div className={'viewer-images count-' + current.length}>
        {current.map((e, i) => (
          <div
            key={e.path}
            className={'viewer-pane ' + (i === active ? 'active' : '')}
            onPointerDown={(event) => {
              if (event.button !== 0) return;
              setActive(i);
              event.currentTarget.setPointerCapture(event.pointerId);
              points.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
              if (points.current.size === 2) {
                const [a, b] = [...points.current.values()];
                gesture.current = { distance: Math.hypot(a.x - b.x, a.y - b.y), scale: view.scale };
              }
            }}
            onPointerMove={(event) => {
              const old = points.current.get(event.pointerId);
              if (!old) return;
              points.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
              if (points.current.size === 2 && gesture.current) {
                const [a, b] = [...points.current.values()];
                setView((v) => ({
                  ...v,
                  scale: Math.max(
                    1,
                    Math.min(
                      8,
                      (gesture.current!.scale * Math.hypot(a.x - b.x, a.y - b.y)) /
                        gesture.current!.distance,
                    ),
                  ),
                }));
              } else if (view.scale > 1) {
                const rect = event.currentTarget.getBoundingClientRect();
                setView((v) => ({
                  ...v,
                  x: v.x + ((event.clientX - old.x) / rect.width) * 100,
                  y: v.y + ((event.clientY - old.y) / rect.height) * 100,
                }));
              }
            }}
            onPointerUp={(event) => {
              points.current.delete(event.pointerId);
              gesture.current = null;
            }}
            onPointerCancel={(event) => {
              points.current.delete(event.pointerId);
              gesture.current = null;
            }}
          >
            <div
              className="transformed-image"
              style={{ transform: `translate(${view.x}%,${view.y}%) scale(${view.scale})` }}
            >
              <PhotoImage album={album} entry={e} full />
            </div>
            <span className="pane-caption">{e.name}</span>
          </div>
        ))}
        {!compare && entries.length > 1 && (
          <>
            <button className="viewer-prev" aria-label="Ảnh trước" onClick={() => step(-1)}>
              <ChevronLeft />
            </button>
            <button className="viewer-next" aria-label="Ảnh tiếp theo" onClick={() => step(1)}>
              <ChevronRight />
            </button>
          </>
        )}
      </div>
      <footer className="viewer-footer">
        <div className="viewer-tags">
          {album.project.categories.map((c) => (
            <button
              key={c.id}
              className={p.category_ids.includes(c.id) ? 'tag active' : 'tag'}
              style={{ '--tag-color': c.color } as React.CSSProperties}
              onClick={() => onCategory(c.id, [focus.path])}
            >
              {c.name}
            </button>
          ))}
        </div>
        <div className="viewer-rating">
          <button
            aria-label="Yêu thích ảnh"
            className={p.favorite ? 'is-favorite' : ''}
            onClick={() => onEdit([focus.path], { favorite: !p.favorite })}
          >
            <Heart size={20} fill={p.favorite ? 'currentColor' : 'none'} />
          </button>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              aria-label={`${n} sao`}
              className={p.stars >= n ? 'star on' : 'star'}
              onClick={() => onEdit([focus.path], { stars: p.stars === n ? 0 : n })}
            >
              ★
            </button>
          ))}
        </div>
        <input
          aria-label="Ghi chú trong trình xem"
          placeholder="Ghi chú hậu kỳ cho ảnh…"
          value={p.note}
          onChange={(e) => onEdit([focus.path], { note: e.target.value })}
        />
      </footer>
    </div>
  );
}
