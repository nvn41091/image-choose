import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { LoaderCircle, X } from 'lucide-react';

export const BusyContext = createContext<{ message: string; cancel?: () => void }>({ message: '' });

export function Modal({
  title,
  children,
  onClose,
  wide = false,
  locked = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  locked?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const busy = useContext(BusyContext);
  const blocked = locked || !!busy.message;
  useEffect(() => {
    const el = dialog.current!;
    el.showModal();
    return () => el.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={'modal ' + (wide ? 'wide' : '')}
      onCancel={(e) => {
        e.preventDefault();
        if (!blocked) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !blocked) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Đóng" disabled={blocked} onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="modal-body" inert={!!busy.message}>
        {children}
      </div>
      {busy.message && (
        <div className="modal-busy" role="status">
          <LoaderCircle className="spinner" size={19} />
          <span>{busy.message}</span>
          {busy.cancel && (
            <button className="button subtle" onClick={busy.cancel}>
              Hủy
            </button>
          )}
        </div>
      )}
    </dialog>
  );
}
