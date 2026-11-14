from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, RLock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import jwt
from PySide6.QtCore import QLockFile

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
AUTHORIZE = ISSUER + '/api/accounts/authorize'
TOKEN_ENDPOINT = ISSUER + '/api/accounts/oauth/token'
DISCOVERY = ISSUER + '/.well-known/openid-configuration'
DIRECT_SCOPE = 'chatgpt.tokens.use.direct'
SCOPES = 'openid profile email offline_access resource.invoke ' + DIRECT_SCOPE
MODEL_ID = re.compile(r'[a-zA-Z0-9._:-]{1,120}')
TERMINAL_REFRESH = {'invalid_grant', 'invalid_refresh_token', 'token_expired',
                    'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'}


class AuthError(ValueError):
    def __init__(self, message, *, status=None, code='', param='', request_id='', body_shape='', reason=''):
        super().__init__(message)
        self.status = status
        self.code = code
        self.param = param
        self.request_id = request_id
        self.body_shape = body_shape
        self.reason = reason

    @property
    def diagnostic(self):
        parts = []
        if type(self.status) is int:
            parts.append(f'HTTP {self.status}')
        for label, value in (('code', self.code), ('reason', self.reason), ('request', self.request_id)):
            if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,160}', value):
                parts.append(f'{label}={value}')
        return ' · '.join(parts)


class AuthorizationCodeRejected(AuthError):
    def __init__(self, client_id, original):
        message = ('OpenAI chưa chấp nhận mã đăng nhập. Cần một lượt xác thực mới với mã ứng dụng đã được cấp; '
                   'không tải lại thẻ callback cũ.')
        if original.diagnostic:
            message += '\n' + original.diagnostic
        super().__init__(message, status=original.status, code=original.code, param=original.param,
                         request_id=original.request_id, body_shape=original.body_shape, reason=original.reason)
        self.client_id = client_id


class LoginCancelled(AuthError):
    def __init__(self):
        super().__init__('Đã hủy đăng nhập ChatGPT.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def open_secure(request):
    # Không chuyển tiếp credential tới URL chuyển hướng.
    return build_opener(NoRedirect()).open(request, timeout=60)


def service_error(data, status=None, request_id='') -> AuthError:
    error = data.get('error', {}) if isinstance(data, dict) else {}
    if isinstance(error, str):
        error = {'code': error}
    if not isinstance(error, dict):
        error = {}
    code, param = error.get('code', ''), error.get('param', '')
    code = code if isinstance(code, str) else ''
    param = param if isinstance(param, str) else ''
    messages = {
        'subscription_sharing_user_not_eligible': 'Tài khoản hoặc workspace này chưa được phép dùng gói ChatGPT trong ứng dụng.',
        'subscription_sharing_usage_limit_exceeded': 'Đã chạm giới hạn dùng gói ChatGPT. Mở “Quản lý hạn mức” để kiểm tra.',
        'subscription_sharing_usage_unavailable': 'Chưa kiểm tra được hạn mức ChatGPT. Hãy thử lại sau.',
        'subscription_sharing_user_unavailable': 'Tài khoản ChatGPT tạm thời không khả dụng. Hãy thử lại sau.',
        'subscription_sharing_unsupported_capability': 'Model hoặc tính năng này chưa được hỗ trợ qua gói ChatGPT. Hãy chọn model khác.',
        'subscription_sharing_route_not_supported': 'Kết nối này chưa được cấp quyền dùng gói ChatGPT cho tác vụ này.',
        'subscription_sharing_invalid_user': 'Không xác nhận được tài khoản ChatGPT. Hãy đăng nhập lại.',
        'chatpass_v2_scope_not_authorized': 'Chưa có quyền dùng gói ChatGPT. Bấm đăng nhập để cấp quyền lại.',
        'chatpass_v2_invalid_authorization_context': 'Quyền dùng gói ChatGPT không hợp lệ. Hãy đăng nhập lại.',
    }
    message = messages.get(code)
    if code in TERMINAL_REFRESH:
        message = 'Phiên ChatGPT đã hết hạn hoặc bị thu hồi. Hãy đăng nhập lại.'
    if not message:
        message = {
            400: 'Yêu cầu đăng nhập hoặc model chưa được hỗ trợ. Kiểm tra quyền và thử lại.',
            401: 'Phiên ChatGPT không được chấp nhận. Hãy đăng nhập lại và kiểm tra quyền dùng gói.',
            403: 'Tài khoản, khu vực hoặc ứng dụng chưa được cấp quyền dùng gói ChatGPT.',
            429: 'Đã chạm giới hạn ChatGPT. Mở “Quản lý hạn mức” và thử lại sau.',
            503: 'Kết nối dùng gói ChatGPT chưa khả dụng hoặc chưa được bật. Hãy thử lại sau.',
        }.get(status, 'Dịch vụ ChatGPT chưa hoàn tất yêu cầu. Hãy thử lại sau.')
    shape = 'error' if isinstance(data, dict) and 'error' in data else 'detail' if isinstance(data, dict) and 'detail' in data else 'other'
    description = error.get('message') or error.get('error_description') or (
        data.get('error_description', '') if isinstance(data, dict) else '')
    description = description.casefold() if isinstance(description, str) else ''
    # Chỉ giữ nhãn chẩn đoán cố định; không log nội dung dịch vụ có thể chứa code/token.
    reason = ''
    if 'pkce' in description or 'code_verifier' in description:
        reason = 'pkce_verification_failed'
    elif 'redirect' in description and ('mismatch' in description or 'match' in description):
        reason = 'redirect_uri_mismatch'
    elif ('code' in description or 'grant' in description) and 'expir' in description:
        reason = 'authorization_code_expired'
    elif ('code' in description or 'grant' in description) and ('already' in description or 'reused' in description):
        reason = 'authorization_code_reused'
    return AuthError(message, status=status, code=code, param=param, request_id=request_id,
                     body_shape=shape, reason=reason)


def request_json(url, *, form=None, access_token=None):
    headers = {'Accept': 'application/json'}
    body = None
    if form is not None:
        body = urlencode(form).encode('ascii')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if access_token:
        headers['Authorization'] = 'Bearer ' + access_token
    request = Request(url, data=body, headers=headers)
    try:
        with open_secure(request) as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            raise AuthError('Phản hồi đăng nhập quá lớn.')
        result = json.loads(raw) if raw else {}
        if not isinstance(result, dict):
            raise AuthError('Phản hồi ChatGPT không hợp lệ.')
        return result
    except HTTPError as error:
        try:
            data = json.loads(error.read(65536))
        except (ValueError, OSError):
            data = {}
        raise service_error(data, error.code, error.headers.get('x-request-id', '') if error.headers else '') from None
    except (URLError, TimeoutError, OSError):
        raise AuthError('Không kết nối được ChatGPT. Kiểm tra mạng rồi thử lại.') from None
    except (ValueError, UnicodeError):
        raise AuthError('Phản hồi đăng nhập ChatGPT không hợp lệ.') from None


def protect(data: bytes, *, decrypt=False) -> bytes:
    """DPAPI của Windows: chỉ tài khoản Windows hiện tại giải mã được."""
    if os.name != 'nt':
        raise AuthError('Lưu phiên ChatGPT được hỗ trợ trên Windows.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        description = None
    else:
        function = crypt.CryptProtectData
        description = 'ChonAnhCuoi ChatGPT'
    function.restype = ctypes.c_int
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else ctypes.c_wchar_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_ulong, ctypes.POINTER(Blob)]
    if not function(ctypes.byref(source), description, None, None, None, 1, ctypes.byref(target)):
        raise AuthError('Windows không mã hóa/đọc được phiên ChatGPT. Hãy dùng đúng tài khoản Windows đã đăng nhập.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


@dataclass(frozen=True)
class Account:
    client_id: str
    email: str
    subject: str
    signed_in: bool
    plan_enabled: bool
    welcomed: bool = False

    @property
    def label(self):
        return f'{self.email or "Tài khoản ChatGPT"} · {self.client_id[-8:]}' + ('' if self.signed_in else ' (đã đăng xuất)')


@dataclass(repr=False)
class LoginAttempt:
    server: HTTPServer
    url: str = field(repr=False)
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    client_id: str
    redirect_uri: str
    host_id: str
    subject: str = ''
    callback: dict | None = field(default=None, repr=False)

    def wait(self, cancel: Event, timeout=180):
        deadline = time.monotonic() + timeout
        self.server.timeout = 0.2
        try:
            while self.callback is None:
                if cancel.is_set():
                    raise LoginCancelled()
                if time.monotonic() >= deadline:
                    raise AuthError('Hết thời gian chờ đăng nhập. Bấm Continue with ChatGPT để thử lại.')
                self.server.handle_request()
            if cancel.is_set():
                raise LoginCancelled()
            return self.callback
        finally:
            self.server.server_close()


class CallbackServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def handle_error(self, request, client_address):
        pass  # Không log URL callback có authorization code.


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        attempt = self.server.attempt
        parsed = urlsplit(self.path)
        expected_host = '127.0.0.1:' + str(self.server.server_port)
        if (self.client_address[0] != '127.0.0.1' or self.headers.get('Host') != expected_host
                or parsed.path != '/auth/callback' or len(parsed.query) > 16384):
            self.reply(400, 'Invalid callback.')
            return
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
        except ValueError:
            self.reply(400, 'Invalid callback.')
            return
        if any(len(values) != 1 for values in query.values()):
            self.reply(400, 'Invalid callback.')
            return
        values = {key: items[0] for key, items in query.items()}
        if not hmac.compare_digest(values.get('state', '').encode(), attempt.state.encode()):
            self.reply(400, 'Invalid sign-in state. Return to the app and try again.')
            return
        if attempt.callback is not None:
            self.reply(400, 'This sign-in attempt has already finished.')
            return
        attempt.callback = values
        self.reply(200, 'Đã nhận phản hồi đăng nhập. Ứng dụng đang xác thực với OpenAI. '
                   'Đăng nhập chỉ hoàn tất khi tài khoản xuất hiện trong ứng dụng. '
                   'Quay lại Chọn ảnh cưới để xem kết quả; bạn có thể đóng thẻ này.')

    def reply(self, status, message):
        payload = message.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)


class ChatGPTAuth:
    def __init__(self, local: Path):
        self.path = local / 'auth' / 'chatgpt.dat'
        self.mutex = RLock()

    @contextmanager
    def locked(self):
        with self.mutex:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(self.path) + '.lock')
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                raise AuthError('Phiên ChatGPT đang được cập nhật ở cửa sổ khác. Hãy thử lại sau.')
            try:
                yield
            finally:
                lock.unlock()

    def read(self):
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {'version': 1, 'host_id': 'urn:uuid:' + str(uuid4()), 'active': '', 'accounts': []}
        try:
            if len(raw) > 2_000_000:
                raise ValueError()
            data = json.loads(protect(raw, decrypt=True))
            if (data.get('version') != 1 or not isinstance(data.get('host_id'), str)
                    or not isinstance(data.get('accounts'), list)
                    or any(not isinstance(item, dict) or not item.get('client_id') or not item.get('subject')
                           for item in data['accounts'])):
                raise ValueError()
            return data
        except (ValueError, TypeError, KeyError):
            raise AuthError('Không đọc được phiên ChatGPT đã lưu. Kiểm tra tài khoản Windows hoặc tệp phiên.') from None

    def write(self, data):
        encrypted = protect(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.chatgpt-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.replace(temporary, self.path)
            finally:
                stream.close()
                temporary.unlink(missing_ok=True)

    @staticmethod
    def account(record):
        return Account(record['client_id'], record.get('email', ''), record['subject'],
                       bool(record.get('access_token')), DIRECT_SCOPE in record.get('scopes', []),
                       record.get('welcomed', False))

    def accounts(self):
        with self.locked():
            data = self.read()
            return [self.account(item) for item in data['accounts']], data['active']

    def set_active(self, client_id):
        with self.locked():
            data = self.read()
            if not any(item['client_id'] == client_id for item in data['accounts']):
                raise AuthError('Không tìm thấy tài khoản ChatGPT đã chọn.')
            data['active'] = client_id
            self.write(data)

    def prepare_login(self, client_id='') -> LoginAttempt:
        with self.locked():
            data = self.read()
            pending = data.get('pending_registration', {})
            if not isinstance(pending, dict) or pending.get('host_id') != data['host_id']:
                pending = {}
            selected = next((item for item in data['accounts'] if item['client_id'] == client_id), None)
            if client_id and selected is None and client_id != pending.get('client_id'):
                raise AuthError('Không tìm thấy tài khoản ChatGPT đã chọn.')
            self.write(data)  # Persist host ID trước lần đăng nhập đầu tiên.
        try:
            server = CallbackServer(('127.0.0.1', 0), CallbackHandler)
        except OSError:
            raise AuthError('Không mở được cổng đăng nhập cục bộ. Kiểm tra firewall rồi thử lại.') from None
        redirect = f'http://127.0.0.1:{server.server_port}/auth/callback'
        verifier = secrets.token_urlsafe(48)
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        issued = selected['client_id'] if selected else pending.get('client_id', '')
        params = {
            'client_id': issued or 'dynamic_agent_client', 'response_type': 'code',
            'redirect_uri': redirect, 'scope': SCOPES, 'resource': RESOURCE,
            'state': state, 'nonce': nonce, 'code_challenge_method': 'S256',
            'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
            'ext_agent_host_id': data['host_id'],
        }
        if selected:
            if selected.get('id_token'):
                params['id_token_hint'] = selected['id_token']
            if selected.get('email'):
                params['login_hint'] = selected['email']
            if DIRECT_SCOPE not in selected.get('scopes', []):
                params['prompt'] = 'consent'
        elif not issued:
            params['agent_name_hint'] = 'Chon Anh Cuoi'
        attempt = LoginAttempt(server, AUTHORIZE + '?' + urlencode(params), state, nonce, verifier,
                               issued, redirect, data['host_id'], selected['subject'] if selected else '')
        server.attempt = attempt
        return attempt

    @staticmethod
    def validate_identity(token, client_id, nonce=None):
        try:
            configuration = request_json(DISCOVERY)
            jwks_url = configuration['jwks_uri']
            if (configuration.get('issuer') != ISSUER or urlsplit(jwks_url).scheme != 'https'
                    or urlsplit(jwks_url).netloc != 'auth.openai.com'):
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
                raise ValueError()
            keys = request_json(jwks_url)['keys']
            matching = [key for key in keys if key.get('kid') == header['kid'] and key.get('kty') == 'RSA']
            if len(matching) != 1:
                raise ValueError()
            key = jwt.PyJWK.from_dict(matching[0], algorithm='RS256').key
            required = ['exp', 'iat', 'iss', 'aud', 'sub'] + (['nonce'] if nonce is not None else [])
            claims = jwt.decode(token, key, algorithms=['RS256'], audience=client_id, issuer=ISSUER,
                                leeway=30, options={'require': required})
            if not isinstance(claims['sub'], str) or not claims['sub']:
                raise ValueError()
            if nonce is not None and (not isinstance(claims['nonce'], str)
                                     or not hmac.compare_digest(claims['nonce'].encode(), nonce.encode())):
                raise ValueError()
            if claims.get('email') is not None and not isinstance(claims['email'], str):
                raise ValueError()
            return claims
        except AuthError:
            raise
        except (jwt.PyJWTError, ValueError, KeyError, TypeError, AttributeError):
            raise AuthError('Không xác thực được danh tính ChatGPT. Phiên hiện tại chưa bị thay thế; hãy đăng nhập lại.') from None

    @staticmethod
    def token_record(tokens, previous=None):
        previous = previous or {}
        access = tokens.get('access_token')
        duration = tokens.get('expires_in')
        token_type = tokens.get('token_type')
        if (not isinstance(access, str) or not access or not access.isascii() or any(c.isspace() for c in access)
                or not isinstance(token_type, str) or token_type.lower() != 'bearer'
                or type(duration) is not int or not 0 < duration <= 86400):
            raise AuthError('Thông tin phiên ChatGPT không hợp lệ.')
        scope = tokens.get('scope')
        if scope is not None and not isinstance(scope, str):
            raise AuthError('Quyền dùng gói ChatGPT không hợp lệ.')
        refresh = tokens.get('refresh_token', previous.get('refresh_token', ''))
        granted = scope.split() if scope is not None else previous.get('scopes', [])
        if not isinstance(refresh, str) or ('offline_access' in granted and not refresh):
            raise AuthError('Thông tin gia hạn phiên ChatGPT không hợp lệ.')
        return {**previous, 'access_token': access, 'refresh_token': refresh,
                'id_token': tokens.get('id_token', previous.get('id_token', '')),
                'expires_at': time.time() + duration,
                'scopes': granted}

    def finish_login(self, attempt, callback, cancel: Event):
        if cancel.is_set():
            raise LoginCancelled()
        if not hmac.compare_digest(callback.get('state', '').encode(), attempt.state.encode()):
            raise AuthError('Trạng thái đăng nhập không hợp lệ.')
        if callback.get('error'):
            raise AuthError('Bạn chưa cấp quyền đăng nhập/dùng gói ChatGPT. Có thể bấm Continue with ChatGPT để thử lại.')
        issued = callback.get('client_id') or attempt.client_id
        if (not issued or issued == 'dynamic_agent_client' or not re.fullmatch(r'[a-zA-Z0-9_-]{1,256}', issued)
                or (attempt.client_id and issued != attempt.client_id) or not callback.get('code')):
            raise AuthError('Đăng ký ChatGPT chưa hoàn tất hoặc không khớp tài khoản đã chọn.')
        attempt.client_id = issued
        # Lưu registration chưa hoàn tất riêng với tài khoản đã xác minh. Nếu code bị từ chối,
        # lần xác thực mới phải dùng issued ID, không tạo thêm dynamic registration.
        with self.locked():
            data = self.read()
            if not any(item['client_id'] == issued for item in data['accounts']):
                data['pending_registration'] = {'client_id': issued, 'host_id': attempt.host_id}
                self.write(data)
        try:
            tokens = request_json(TOKEN_ENDPOINT, form={
                'grant_type': 'authorization_code', 'client_id': issued, 'code': callback['code'],
                'code_verifier': attempt.verifier, 'redirect_uri': attempt.redirect_uri, 'resource': RESOURCE,
            })
        except AuthError as error:
            if error.code == 'invalid_grant':
                raise AuthorizationCodeRejected(issued, error) from None
            message = 'Không đổi được mã đăng nhập thành phiên ChatGPT. ' + str(error)
            if error.diagnostic:
                message += '\n' + error.diagnostic
            raise AuthError(message, status=error.status, code=error.code, param=error.param,
                            request_id=error.request_id, body_shape=error.body_shape, reason=error.reason) from None
        claims = self.validate_identity(tokens.get('id_token', ''), issued, attempt.nonce)
        if attempt.subject and claims['sub'] != attempt.subject:
            raise AuthError('Tài khoản đăng nhập khác tài khoản đã chọn. Chưa thay thế phiên hiện tại.')
        with self.locked():
            data = self.read()
            old = next((item for item in data['accounts'] if item['client_id'] == issued), {})
            if old and old['subject'] != claims['sub']:
                raise AuthError('Danh tính ChatGPT không khớp phiên đã lưu.')
            record = self.token_record(tokens, old)
            record.update(client_id=issued, subject=claims['sub'], email=claims.get('email', ''), issuer=ISSUER)
            if cancel.is_set():
                raise LoginCancelled()
            data['accounts'] = [item for item in data['accounts'] if item['client_id'] != issued] + [record]
            data['active'] = issued
            if data.get('pending_registration', {}).get('client_id') == issued:
                data.pop('pending_registration', None)
            self.write(data)
            return self.account(record)

    def mark_welcomed(self, client_id):
        with self.locked():
            data = self.read()
            for item in data['accounts']:
                if item['client_id'] == client_id:
                    item['welcomed'] = True
            self.write(data)

    @staticmethod
    def clear_tokens(record):
        for key in ('access_token', 'refresh_token', 'id_token', 'expires_at'):
            record.pop(key, None)

    def access_token(self, client_id):
        with self.locked():
            data = self.read()
            record = next((item for item in data['accounts'] if item['client_id'] == client_id), None)
            if not record or not record.get('access_token'):
                raise AuthError('Hãy đăng nhập ChatGPT trước khi đánh giá ảnh.')
            if DIRECT_SCOPE not in record.get('scopes', []):
                raise AuthError('Chưa bật quyền dùng gói ChatGPT. Bấm Continue with ChatGPT để cấp quyền.')
            if record.get('expires_at', 0) > time.time() + 60:
                return record['access_token']
            if not record.get('refresh_token'):
                raise AuthError('Phiên ChatGPT đã hết hạn. Hãy đăng nhập lại.')
            try:
                tokens = request_json(TOKEN_ENDPOINT, form={
                    'grant_type': 'refresh_token', 'client_id': client_id,
                    'refresh_token': record['refresh_token'], 'resource': RESOURCE,
                })
            except AuthError as error:
                if error.code in TERMINAL_REFRESH:
                    self.clear_tokens(record)
                    self.write(data)
                raise
            if not isinstance(tokens.get('refresh_token'), str) or not tokens['refresh_token']:
                raise AuthError('Không nhận được phiên gia hạn ChatGPT đầy đủ. Hãy đăng nhập lại.')
            updated = self.token_record(tokens, record)
            if tokens.get('id_token'):
                claims = self.validate_identity(tokens['id_token'], client_id)
                if claims['sub'] != record['subject']:
                    raise AuthError('Danh tính phiên gia hạn không khớp tài khoản ChatGPT.')
            record.update(updated)
            self.write(data)
            if DIRECT_SCOPE not in record['scopes']:
                raise AuthError('Quyền dùng gói ChatGPT đã thay đổi. Hãy đăng nhập lại.')
            return record['access_token']

    def models(self, client_id):
        data = request_json(RESOURCE + '/models', access_token=self.access_token(client_id))
        if not isinstance(data.get('models'), list):
            raise AuthError('Danh sách model ChatGPT không hợp lệ. Hãy tải lại.')
        models = []
        seen = set()
        for item in data.get('models', []):
            if not isinstance(item, dict):
                continue
            slug = item.get('slug')
            if item.get('visibility') == 'list' and isinstance(slug, str) and MODEL_ID.fullmatch(slug) and slug not in seen:
                seen.add(slug)
                name = item.get('display_name', slug)
                models.append((slug, name if isinstance(name, str) else slug))
        if not models:
            raise AuthError('Tài khoản này chưa có model khả dụng qua gói ChatGPT.')
        return models

    def sign_out(self, client_id):
        with self.locked():
            data = self.read()
            record = next((item for item in data['accounts'] if item['client_id'] == client_id), None)
            if not record:
                return True
            revoked = not record.get('refresh_token')
            if record.get('refresh_token'):
                try:
                    endpoint = request_json(DISCOVERY)['revocation_endpoint']
                    if urlsplit(endpoint).scheme != 'https' or urlsplit(endpoint).netloc != 'auth.openai.com':
                        raise AuthError('Địa chỉ thu hồi phiên không hợp lệ.')
                    for retry in range(2):
                        try:
                            request_json(endpoint, form={'token': record['refresh_token'],
                                                         'token_type_hint': 'refresh_token', 'client_id': client_id})
                            revoked = True
                            break
                        except AuthError as error:
                            if retry or error.status is not None and error.status < 500:
                                break
                            time.sleep(0.2)
                except (AuthError, KeyError):
                    pass
            self.clear_tokens(record)
            self.write(data)
            return revoked


@dataclass(frozen=True)
class PlanSession:
    auth: ChatGPTAuth = field(repr=False)
    client_id: str

    def respond(self, payload):
        body = {key: value for key, value in payload.items() if key != 'max_output_tokens'}
        body.update(store=False, stream=True)
        token = self.auth.access_token(self.client_id)
        request = Request(RESOURCE + '/responses', data=json.dumps(body).encode('utf-8'), method='POST',
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                                   'Accept': 'text/event-stream'})
        try:
            with open_secure(request) as stream:
                return read_response_stream(stream)
        except HTTPError as error:
            try:
                data = json.loads(error.read(65536))
            except (ValueError, OSError):
                data = {}
            raise service_error(data, error.code, error.headers.get('x-request-id', '') if error.headers else '') from None
        except (URLError, TimeoutError, OSError):
            raise AuthError('Mất kết nối ChatGPT. Kết quả các nhóm trước vẫn được giữ; hãy thử lại sau.') from None


def read_response_stream(stream):
    data_lines = []
    size = 0
    while True:
        line = stream.readline(1_000_001)
        if not line:
            break
        size += len(line)
        if len(line) > 1_000_000 or size > 8_000_000:
            raise AuthError('Phản hồi ChatGPT quá lớn. Chọn ít ảnh hơn.')
        line = line.rstrip(b'\r\n')
        if line.startswith(b'data:'):
            data_lines.append(line[5:].lstrip(b' '))
        elif not line and data_lines:
            raw = b'\n'.join(data_lines)
            data_lines = []
            if raw == b'[DONE]':
                break
            try:
                event = json.loads(raw)
                kind = event['type']
                if kind == 'response.completed':
                    response = event['response']
                    if not isinstance(response, dict) or response.get('status') != 'completed':
                        raise AuthError('ChatGPT chưa hoàn tất kết quả. Chưa áp dụng lựa chọn.')
                    return response
                if kind == 'response.failed':
                    raise service_error(event.get('response', {}))
                if kind == 'error':
                    raise service_error({'error': event})
                if kind == 'response.incomplete':
                    raise AuthError('ChatGPT trả về kết quả chưa đầy đủ. Chưa áp dụng lựa chọn.')
            except AuthError:
                raise
            except (ValueError, KeyError, TypeError):
                raise AuthError('Luồng kết quả ChatGPT không hợp lệ.') from None
    raise AuthError('Luồng ChatGPT bị ngắt trước khi hoàn tất. Chưa áp dụng lựa chọn của nhóm này.')
