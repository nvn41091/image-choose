import { useEffect, useRef, useState } from 'react';
import { Heart, LoaderCircle, LogIn } from 'lucide-react';
import { loginGoogle, watchAccount, type Account } from './auth';
import { prepareDriveLogin } from './drive';
import { setStorageUser } from './storage';
import App from './App';
export default function AuthGate() {
  const [account, setAccount] = useState<Account | null>(null),
    [loading, setLoading] = useState(true),
    [signing, setSigning] = useState(false),
    [error, setError] = useState('');
  const previous = useRef('');
  useEffect(() => {
    prepareDriveLogin().catch((e) => setError(e.message));
    try {
      return watchAccount(
        (user) => {
          if (previous.current && previous.current !== user?.uid) {
            window.location.reload();
            return;
          }
          if (user) {
            previous.current = user.uid;
            setStorageUser(user.uid);
          }
          setAccount(user);
          setLoading(false);
        },
        (e) => {
          setError(e.message);
          setLoading(false);
        },
      );
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  }, []);
  if (account) return <App key={account.uid} account={account} />;
  return (
    <main className="auth-page">
      <section className="auth-card">
        <span className="brand-mark">
          <Heart size={27} />
        </span>
        <div className="eyebrow">KHOẢNH KHẮC · CHỌN ẢNH CƯỚI</div>
        <h1>
          Không gian ảnh
          <br />
          của riêng bạn.
        </h1>
        <p>
          Đăng nhập Google để mở workspace, xem ảnh Drive và tự động đồng bộ mọi lựa chọn giữa điện
          thoại với máy tính.
        </p>
        {loading ? (
          <div role="status" className="auth-loading">
            <LoaderCircle className="spinner" size={20} />
            Đang kiểm tra đăng nhập…
          </div>
        ) : (
          <button
            className="button primary full-width"
            disabled={signing}
            onClick={() => {
              setError('');
              setSigning(true);
              void loginGoogle()
                .catch((e) => setError(e.message))
                .finally(() => setSigning(false));
            }}
          >
            {signing ? <LoaderCircle className="spinner" size={18} /> : <LogIn size={18} />}Đăng
            nhập bằng Google
          </button>
        )}
        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}
        <p className="hint">
          Chỉ xin quyền xem Drive để đọc ảnh. Lựa chọn được lưu riêng theo tài khoản Google của bạn.
          Nếu Google chặn trình duyệt trong ứng dụng, mở trang bằng Chrome hoặc Safari.
        </p>
      </section>
    </main>
  );
}
