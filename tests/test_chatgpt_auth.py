import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from core.ai_advisor import AdvisorError, analyze_photos
from core.chatgpt_auth import (
    DIRECT_SCOPE, DISCOVERY, ISSUER, RESOURCE, SCOPES, TOKEN_ENDPOINT,
    AuthError, AuthorizationCodeRejected, ChatGPTAuth, LoginCancelled, PlanSession,
    protect, read_response_stream, request_json,
)


def review_response():
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{
        'type': 'output_text', 'text': json.dumps({'summary': 'Tốt', 'photos': [
            {'id': 1, 'score': 90, 'reason': 'Ánh sáng tốt', 'editing_note': ''}]})}]}]}


def sse(event):
    return b'data: ' + json.dumps(event).encode() + b'\n\n'


class ChatGPTAuthTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key(), as_dict=True)
        cls.jwk['kid'] = 'unit-test-key'

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.auth = ChatGPTAuth(self.base)

    def identity(self, nonce_value, client='oaiapp_first', subject='user-first', **overrides):
        claims = {'iss': ISSUER, 'aud': client, 'sub': subject, 'email': 'first@example.test',
                  'iat': int(time.time()), 'exp': int(time.time()) + 3600, 'nonce': nonce_value}
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'unit-test-key'})

    def tokens(self, nonce, client='oaiapp_first', subject='user-first', scope=SCOPES):
        return {'access_token': 'test-access-secret', 'refresh_token': 'test-refresh-secret',
                'id_token': self.identity(nonce, client, subject), 'token_type': 'Bearer',
                'expires_in': 3600, 'scope': scope}

    def discovery(self, url, **kwargs):
        if url == DISCOVERY:
            return {'issuer': ISSUER, 'jwks_uri': ISSUER + '/.well-known/jwks.json',
                    'revocation_endpoint': ISSUER + '/api/accounts/oauth/revoke'}
        if url.endswith('/jwks.json'):
            return {'keys': [self.jwk]}
        raise AssertionError('Unexpected request')

    def prepare(self, client_id=''):
        attempt = self.auth.prepare_login(client_id)
        self.addCleanup(attempt.server.server_close)
        return attempt

    def login(self, *, scope=SCOPES, client='oaiapp_first', subject='user-first'):
        attempt = self.prepare()
        callback = {'state': attempt.state, 'code': 'test-authorization-code', 'client_id': client}
        tokens = self.tokens(attempt.nonce, client, subject, scope)

        def network(url, **kwargs):
            return tokens if url == TOKEN_ENDPOINT else self.discovery(url, **kwargs)

        with patch('core.chatgpt_auth.request_json', side_effect=network):
            return self.auth.finish_login(attempt, callback, Event())

    def test_initial_registration_pkce_and_persistent_host(self):
        first = self.prepare()
        second = self.prepare()
        query = parse_qs(urlsplit(first.url).query)
        self.assertEqual(query['client_id'], ['dynamic_agent_client'])
        self.assertEqual(query['resource'], [RESOURCE])
        self.assertEqual(query['scope'], [SCOPES])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['ext_agent_host_id'], [second.host_id])
        self.assertNotEqual(first.state, second.state)
        self.assertNotEqual(first.verifier, second.verifier)
        self.assertTrue(query['redirect_uri'][0].startswith('http://127.0.0.1:'))
        self.assertNotIn(first.verifier, first.url)
        self.assertNotIn(first.state, repr(first))
        with self.assertRaises(LoginCancelled):
            cancel = Event()
            cancel.set()
            first.wait(cancel)
        with self.assertRaises(AuthError):
            second.wait(Event(), timeout=0)

    def test_callback_rejects_forged_state_and_accepts_valid_response(self):
        attempt = self.prepare()
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiting = pool.submit(attempt.wait, Event(), 4)
            connection = HTTPConnection('127.0.0.1', attempt.server.server_port, timeout=2)
            connection.request('GET', '/auth/callback?state=forged&code=secret')
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.close()
            self.assertIsNone(attempt.callback)
            valid = urlencode({'state': attempt.state, 'code': 'test-code', 'client_id': 'oaiapp_first'})
            connection = HTTPConnection('127.0.0.1', attempt.server.server_port, timeout=2)
            connection.request('GET', '/auth/callback?' + valid)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertNotIn(b'test-code', response.read())
            self.assertEqual(response.getheader('Referrer-Policy'), 'no-referrer')
            connection.close()
            self.assertEqual(waiting.result(timeout=3)['code'], 'test-code')

    def test_validated_login_is_encrypted_and_reauthorization_reuses_client(self):
        account = self.login()
        self.assertTrue(account.signed_in)
        self.assertTrue(account.plan_enabled)
        encrypted = self.auth.path.read_bytes()
        self.assertNotIn(b'test-access-secret', encrypted)
        self.assertNotIn(b'test-refresh-secret', encrypted)
        self.assertNotIn(b'first@example.test', encrypted)
        self.assertEqual(self.auth.accounts()[1], account.client_id)
        returning = self.prepare(account.client_id)
        query = parse_qs(urlsplit(returning.url).query)
        self.assertEqual(query['client_id'], [account.client_id])
        self.assertNotIn('agent_name_hint', query)
        self.assertIn('id_token_hint', query)
        self.assertEqual(query['login_hint'], ['first@example.test'])
        self.assertNotIn('prompt', query)
        self.assertEqual(ChatGPTAuth(self.base).accounts()[0][0], account)

    def test_rejected_initial_code_resumes_issued_client_with_fresh_pkce_after_restart(self):
        first = self.prepare()
        callback = {'state': first.state, 'code': 'rejected-authorization-code', 'client_id': 'oaiapp_recovery'}
        rejection = AuthError('Expired', status=400, code='invalid_grant', request_id='req_rejected')
        with patch('core.chatgpt_auth.request_json', side_effect=rejection) as token_exchange:
            with self.assertRaises(AuthorizationCodeRejected) as error:
                self.auth.finish_login(first, callback, Event())
        self.assertEqual(token_exchange.call_count, 1)
        self.assertEqual(error.exception.client_id, 'oaiapp_recovery')
        self.assertIn('invalid_grant', str(error.exception))
        self.assertNotIn('rejected-authorization-code', str(error.exception))
        self.assertEqual(self.auth.accounts(), ([], ''))
        restarted = ChatGPTAuth(self.base)
        second = restarted.prepare_login()
        self.addCleanup(second.server.server_close)
        query = parse_qs(urlsplit(second.url).query)
        self.assertEqual(query['client_id'], ['oaiapp_recovery'])
        self.assertNotIn('agent_name_hint', query)
        self.assertEqual(second.host_id, first.host_id)
        self.assertNotEqual(second.state, first.state)
        self.assertNotEqual(second.nonce, first.nonce)
        self.assertNotEqual(second.verifier, first.verifier)
        tokens = self.tokens(second.nonce, 'oaiapp_recovery')

        def network(url, **kwargs):
            if url != TOKEN_ENDPOINT:
                return self.discovery(url, **kwargs)
            form = kwargs['form']
            self.assertEqual(form['client_id'], 'oaiapp_recovery')
            self.assertEqual(form['redirect_uri'], second.redirect_uri)
            self.assertEqual(form['code_verifier'], second.verifier)
            self.assertEqual(form['code'], 'fresh-code')
            return tokens

        with patch('core.chatgpt_auth.request_json', side_effect=network):
            account = restarted.finish_login(second, {'state': second.state, 'code': 'fresh-code'}, Event())
        self.assertTrue(account.signed_in)
        self.assertTrue(account.plan_enabled)
        with restarted.locked():
            self.assertNotIn('pending_registration', restarted.read())

    def test_token_error_diagnostics_are_safe_and_do_not_misreport_as_expired_session(self):
        original = HTTPError(TOKEN_ENDPOINT, 400, 'Bad Request', {'x-request-id': 'req_unit'}, io.BytesIO(
            b'{"error":"invalid_grant","error_description":"PKCE code_verifier invalid SECRET-CODE"}'))
        with patch('core.chatgpt_auth.open_secure', side_effect=original):
            with self.assertRaises(AuthError) as error:
                request_json(TOKEN_ENDPOINT, form={'code': 'SECRET-CODE'})
        self.assertEqual(error.exception.reason, 'pkce_verification_failed')
        wrapped = AuthorizationCodeRejected('oaiapp_recovery', error.exception)
        self.assertIn('HTTP 400', str(wrapped))
        self.assertIn('pkce_verification_failed', str(wrapped))
        self.assertNotIn('SECRET-CODE', str(wrapped))
        self.assertNotIn('Phiên ChatGPT đã hết hạn', str(wrapped))

    def test_signature_issuer_audience_expiry_nonce_are_verified(self):
        for claims in ({'aud': 'wrong'}, {'iss': 'https://attacker.invalid'},
                       {'exp': int(time.time()) - 100}, {'nonce': 'wrong'}, {'sub': ''}):
            with self.subTest(claims=claims):
                token = self.identity('expected', **claims)
                with patch('core.chatgpt_auth.request_json', side_effect=self.discovery):
                    with self.assertRaises(AuthError):
                        self.auth.validate_identity(token, 'oaiapp_first', 'expected')
        untrusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode({'iss': ISSUER, 'aud': 'oaiapp_first', 'sub': 'wrong', 'nonce': 'expected',
                            'iat': int(time.time()), 'exp': int(time.time()) + 300}, untrusted,
                           algorithm='RS256', headers={'kid': 'unit-test-key'})
        with patch('core.chatgpt_auth.request_json', side_effect=self.discovery):
            with self.assertRaises(AuthError):
                self.auth.validate_identity(token, 'oaiapp_first', 'expected')

    def test_denied_and_mismatched_logins_preserve_active_account(self):
        account = self.login()
        before = self.auth.path.read_bytes()
        attempt = self.prepare(account.client_id)
        before = self.auth.path.read_bytes()
        for callback in (
            {'state': 'wrong', 'code': 'code'},
            {'state': attempt.state, 'error': 'access_denied'},
            {'state': attempt.state, 'code': 'code', 'client_id': 'oaiapp_other'},
        ):
            with self.subTest(callback=callback), patch('core.chatgpt_auth.request_json') as request:
                with self.assertRaises(AuthError):
                    self.auth.finish_login(attempt, callback, Event())
                request.assert_not_called()
                self.assertEqual(self.auth.path.read_bytes(), before)
        tokens = self.tokens(attempt.nonce, account.client_id, 'different-user')
        with patch('core.chatgpt_auth.request_json', side_effect=lambda url, **kw: tokens if url == TOKEN_ENDPOINT else self.discovery(url, **kw)):
            with self.assertRaises(AuthError):
                self.auth.finish_login(attempt, {'state': attempt.state, 'code': 'code'}, Event())
        self.assertEqual(self.auth.path.read_bytes(), before)

    def test_identity_only_does_not_enable_plan_usage_and_requests_consent_again(self):
        account = self.login(scope='openid profile email offline_access')
        self.assertTrue(account.signed_in)
        self.assertFalse(account.plan_enabled)
        with self.assertRaises(AuthError):
            self.auth.access_token(account.client_id)
        query = parse_qs(urlsplit(self.prepare(account.client_id).url).query)
        self.assertEqual(query['prompt'], ['consent'])
        self.assertIn(DIRECT_SCOPE, query['scope'][0])

    def test_refresh_rotates_tokens_once_and_terminal_error_clears_only_credentials(self):
        account = self.login()
        with self.auth.locked():
            data = self.auth.read()
            data['accounts'][0]['expires_at'] = 0
            self.auth.write(data)
        refreshed = {'access_token': 'replacement-access', 'refresh_token': 'replacement-refresh',
                     'expires_in': 3600, 'token_type': 'Bearer'}
        with patch('core.chatgpt_auth.request_json', return_value=refreshed) as request:
            self.assertEqual(self.auth.access_token(account.client_id), 'replacement-access')
            self.assertEqual(ChatGPTAuth(self.base).access_token(account.client_id), 'replacement-access')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs['form']['client_id'], account.client_id)
        self.assertNotIn('scope', request.call_args.kwargs['form'])
        with self.auth.locked():
            data = self.auth.read()
            self.assertEqual(data['accounts'][0]['refresh_token'], 'replacement-refresh')
            data['accounts'][0]['expires_at'] = 0
            self.auth.write(data)
        before = self.auth.path.read_bytes()
        with patch('core.chatgpt_auth.request_json', side_effect=AuthError('Temporary', status=503)):
            with self.assertRaises(AuthError):
                self.auth.access_token(account.client_id)
        self.assertEqual(self.auth.path.read_bytes(), before)
        with patch('core.chatgpt_auth.request_json', side_effect=AuthError('Expired', code='invalid_grant')):
            with self.assertRaises(AuthError):
                self.auth.access_token(account.client_id)
        saved, _ = self.auth.accounts()
        self.assertFalse(saved[0].signed_in)
        self.assertEqual(saved[0].client_id, account.client_id)

    def test_multiple_accounts_logout_and_atomic_storage_failure(self):
        first = self.login()
        second = self.login(client='oaiapp_second', subject='user-second')
        before = self.auth.path.read_bytes()
        with patch('core.chatgpt_auth.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                self.auth.set_active(first.client_id)
        self.assertEqual(self.auth.path.read_bytes(), before)
        self.assertFalse(list(self.auth.path.parent.glob('.chatgpt-*.tmp')))
        with patch('core.chatgpt_auth.request_json', side_effect=AuthError('Offline')):
            self.assertFalse(self.auth.sign_out(first.client_id))
        accounts, _ = self.auth.accounts()
        records = {item.client_id: item for item in accounts}
        self.assertFalse(records[first.client_id].signed_in)
        self.assertTrue(records[second.client_id].signed_in)
        returning = parse_qs(urlsplit(self.prepare(first.client_id).url).query)
        self.assertEqual(returning['client_id'], [first.client_id])
        self.assertNotIn('id_token_hint', returning)

    def test_model_catalog_is_from_selected_account(self):
        account = self.login()
        data = {'models': [{'slug': 'vision-model', 'display_name': 'Vision', 'visibility': 'list'},
                           {'slug': 'hidden', 'visibility': 'hide'},
                           {'slug': '../invalid', 'visibility': 'list'}]}
        with patch('core.chatgpt_auth.request_json', return_value=data) as request:
            self.assertEqual(self.auth.models(account.client_id), [('vision-model', 'Vision')])
        self.assertEqual(request.call_args.kwargs['access_token'], 'test-access-secret')
        self.assertEqual(request.call_args.args[0], RESOURCE + '/models')

    def test_revocation_uses_refresh_token_and_parallel_vault_access_is_blocked(self):
        account = self.login()
        calls = []

        def network(url, **kwargs):
            calls.append((url, kwargs))
            return self.discovery(url) if url == DISCOVERY else {}

        with patch('core.chatgpt_auth.request_json', side_effect=network):
            self.assertTrue(self.auth.sign_out(account.client_id))
        self.assertEqual(calls[-1][1]['form'], {'token': 'test-refresh-secret',
                                               'token_type_hint': 'refresh_token', 'client_id': account.client_id})
        self.assertFalse(self.auth.accounts()[0][0].signed_in)
        with self.auth.locked():
            with self.assertRaises(AuthError):
                ChatGPTAuth(self.base).accounts()

    def test_dpapi_round_trip_and_session_absent_from_backup(self):
        from core.backup import create_backup
        from core.data_store import Project
        from zipfile import ZipFile

        original = b'test-credential'
        encrypted = protect(original)
        self.assertEqual(protect(encrypted, decrypt=True), original)
        self.assertNotEqual(encrypted, original)
        self.login()
        archive = create_backup(self.base, Project())
        with ZipFile(archive) as saved:
            self.assertNotIn('chatgpt.dat', saved.namelist())
            self.assertNotIn(b'test-access-secret', b''.join(saved.read(name) for name in saved.namelist()))


class PlanInferenceTest(TestCase):
    def test_plan_uses_stream_and_never_api_key_or_unsupported_fields(self):
        auth = type('Auth', (), {'access_token': lambda self, client: 'plan-access-token'})()
        session = PlanSession(auth, 'oaiapp_first')
        stream = io.BytesIO(sse({'type': 'response.completed', 'response': review_response()}))
        with (patch('core.ai_advisor.image_data_url', return_value='data:image/jpeg;base64,eA=='),
              patch('core.ai_advisor.urlopen') as api,
              patch('core.chatgpt_auth.open_secure', return_value=stream) as plan):
            result = analyze_photos(Path.cwd(), ['a.jpg'], 'never-use-this-api-key', 'vision-model', plan_session=session)
        api.assert_not_called()
        request = plan.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(payload['stream'])
        self.assertFalse(payload['store'])
        self.assertNotIn('max_output_tokens', payload)
        self.assertNotIn('never-use-this-api-key', str(request.headers))
        self.assertEqual(request.get_header('Authorization'), 'Bearer plan-access-token')
        self.assertEqual(result.photos[0].path, 'a.jpg')

    def test_limit_failure_or_disconnection_does_not_apply_partial_stream(self):
        failure = {'type': 'response.failed', 'response': {'error': {
            'code': 'subscription_sharing_usage_limit_exceeded', 'param': 'model'}}}
        with self.assertRaises(AuthError) as error:
            read_response_stream(io.BytesIO(sse(failure)))
        self.assertEqual(error.exception.code, 'subscription_sharing_usage_limit_exceeded')
        self.assertIn('Quản lý hạn mức', str(error.exception))
        delta = {'type': 'response.output_text.delta', 'delta': 'Incomplete JSON'}
        for data in (sse(delta), sse({'type': 'response.incomplete'}), b'data: invalid\n\n', b'data: [DONE]\n\n'):
            with self.subTest(data=data), self.assertRaises(AuthError):
                read_response_stream(io.BytesIO(data))

    def test_plan_http_error_preserves_diagnostics_and_never_falls_back(self):
        auth = type('Auth', (), {'access_token': lambda self, client: 'private-access-token'})()
        error = HTTPError(RESOURCE + '/responses', 403, 'Forbidden', {'x-request-id': 'req_test'},
                          io.BytesIO(b'{"detail":"not enabled"}'))
        with patch('core.chatgpt_auth.open_secure', side_effect=error):
            with self.assertRaises(AuthError) as failure:
                PlanSession(auth, 'client').respond({'model': 'vision'})
        self.assertEqual(failure.exception.status, 403)
        self.assertEqual(failure.exception.body_shape, 'detail')
        self.assertEqual(failure.exception.request_id, 'req_test')
        self.assertNotIn('private-access-token', str(failure.exception))
        with (patch('core.ai_advisor.image_data_url', return_value='x'),
              patch.object(PlanSession, 'respond', side_effect=AuthError('Hết hạn mức')),
              patch('core.ai_advisor.urlopen') as api):
            with self.assertRaises(AdvisorError):
                analyze_photos(Path.cwd(), ['a.jpg'], 'paid-api-key', 'vision', plan_session=PlanSession(auth, 'client'))
        api.assert_not_called()
