import asyncio
from contextlib import closing
import json
from pathlib import Path
import tempfile
import struct
from types import SimpleNamespace
import unittest

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

from app.common import Redactor, password_hash
from app.db import Database
from app.web import make_app
from unittest.mock import AsyncMock, patch


class WebTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_csrf_expiry_and_parallel_rate_limit(self):
        with tempfile.TemporaryDirectory() as temp, closing((db := Database(Path(temp) / 'web.db')).conn):
            root = Path(__file__).resolve().parents[1]
            controller = SimpleNamespace(root=root, db=db, redactor=Redactor(temp),
                config={'lan_subnet': '192.168.2.0/24', 'password_hash': password_hash('test-pass'),
                        'github_account': 'test'}, windows_online=False, bot=None, unsnooze={}, lock=asyncio.Lock())
            app = make_app(controller)
            async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
                response = await client.get('/api/state')
                self.assertEqual(response.status, 401)
                self.assertEqual((await client.get('/api/usage')).status, 401)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual((await client.get('/', headers={'Host': 'evil.example'})).status, 403)
                response = await client.get('/')
                self.assertIn('href="/favicon.ico"', await response.text())
                icon = await client.get('/favicon.ico')
                self.assertEqual(icon.status, 200)
                ico = await icon.read()
                self.assertEqual(struct.unpack('<HHH', ico[:6]), (0, 1, 3))
                for index, size in enumerate((16, 32, 48)):
                    width, height, _, _, planes, bits, length, offset = struct.unpack_from('<BBBBHHII', ico, 6 + index * 16)
                    self.assertEqual((width, height, planes, bits), (size, size, 1, 32))
                    self.assertEqual(ico[offset:offset+8], b'\x89PNG\r\n\x1a\n')
                    self.assertEqual(struct.unpack('>II', ico[offset+16:offset+24]), (size, size))
                    self.assertLessEqual(offset + length, len(ico))
                self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
                cookie = response.cookies['codexpi_login']
                self.assertTrue(cookie['httponly'])
                self.assertEqual(cookie['samesite'], 'Strict')
                self.assertEqual((await client.post('/login', data={'password': 'wrong'})).status, 401)
                self.assertEqual((await client.post('/login', data={'password': 'test-pass'})).status, 403)
                await client.get('/')
                response = await client.post('/login', data={'password': 'test-pass'}, allow_redirects=False,
                    headers={'Origin': str(client.make_url('/')).rstrip('/')})
                self.assertEqual(response.status, 303)
                self.assertTrue(response.cookies['codexpi']['httponly'])
                # A valid random URL-safe CSRF token can resemble a provider key.
                csrf = 'sk-' + 'a' * 40
                db.conn.execute('UPDATE sessions SET csrf=?', (csrf,))
                state = await (await client.get('/api/state')).json()
                self.assertEqual(state['csrf'], csrf)
                self.assertFalse(state['auto_continue'])
                self.assertFalse(state['auto_account_change'])
                self.assertFalse(state['auto_boot_windows'])
                db.set_setting('accounts', [{'account_id': 'saved', 'name': 'Visible account', 'status': 'ready',
                                             'access_token': 'must-never-be-exposed'}])
                db.set_setting('account_switch', {'id': 'pending', 'phase': 'logging_in',
                                                 'login_url': 'private-oauth-url', 'authToken': 'private-native-proof'})
                account_state = await (await client.get('/api/state')).json()
                self.assertEqual(account_state['accounts'][0]['name'], 'Visible account')
                for hidden in ('must-never-be-exposed', 'private-oauth-url', 'private-native-proof'):
                    self.assertNotIn(hidden, json.dumps(account_state))
                db.set_setting('account_switch', {})
                with patch('app.accounts.request_switch', AsyncMock(return_value={'ok': True, 'operation_id': 'account-operation'})) as switch:
                    body = {'action': 'account-switch', 'account_id': 'saved'}
                    self.assertEqual((await client.post('/api/action', json=body)).status, 403)
                    self.assertEqual((await client.post('/api/action', json=body, headers={'X-CSRF-Token': csrf})).status, 200)
                    switch.assert_awaited_once()
                for enabled, expected in [('true', 400), (True, 200), (False, 200)]:
                    result = await client.post('/api/action', json={'action': 'auto-continue', 'enabled': enabled},
                        headers={'X-CSRF-Token': csrf})
                    self.assertEqual(result.status, expected)
                    if expected == 200:
                        self.assertEqual((await (await client.get('/api/state')).json())['auto_continue'], enabled)
                for enabled, expected in [('true', 400), (True, 200), (False, 200)]:
                    result = await client.post('/api/action', json={'action': 'auto-account-change', 'enabled': enabled},
                        headers={'X-CSRF-Token': csrf})
                    self.assertEqual(result.status, expected)
                    if expected == 200:
                        self.assertEqual((await (await client.get('/api/state')).json())['auto_account_change'], enabled)
                for enabled, expected in [('true', 400), (True, 400), (False, 200)]:
                    result = await client.post('/api/action', json={'action': 'auto-boot-windows', 'enabled': enabled},
                        headers={'X-CSRF-Token': csrf})
                    self.assertEqual(result.status, expected)
                db.set_setting('windows_power_observation', {'mac': '74-56-3C-2B-FD-0F',
                    'address': '192.168.2.200', 'startup_ready': True})
                self.assertEqual((await client.post('/api/action', json={'action': 'auto-boot-windows', 'enabled': True},
                    headers={'X-CSRF-Token': csrf})).status, 200)
                self.assertTrue((await (await client.get('/api/state')).json())['auto_boot_windows'])
                self.assertNotIn('password_hash', str(state))
                self.assertEqual(len(state['infrastructure']), 6)
                self.assertEqual(state['infrastructure'][3]['status'], 'unknown')
                db.record_usage({'checked_at': __import__('time').time(), 'rateLimits': {
                    'primary': {'usedPercent': 100, 'windowDurationMins': 300, 'resetsAt': 2000000000},
                    'secondary': {'usedPercent': 20, 'windowDurationMins': 10080}}})
                usage_response = await client.get('/api/usage')
                self.assertEqual(usage_response.status, 200)
                usage = await usage_response.json()
                self.assertEqual(usage['windows']['daily']['remaining'], 0)
                self.assertEqual(usage['history']['weekly'][0]['remaining'], 80)
                self.assertEqual(usage_response.headers['Cache-Control'], 'no-store')
                secret = 'test-quoted-"private-key'
                (Path(temp) / '.env').write_text('TEST_SECRET=' + secret)
                db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                    tmux_session_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?)''',
                    ('project1', '<script>unsafe</script>', 'test', temp, 'codexpi-test', 1, 1))
                db.update('project1', goal_status='stalled', block_reason=json.dumps({
                    'reason': 'Missing choice', 'explanation': 'The next step needs a decision.',
                    'solution': 'Choose A or B: ' + secret, 'details': secret, 'requires_user': True}))
                db.set_setting('prompts/project1', [{'id': 'pending', 'params': {'input': secret}}])
                queued_state = await (await client.get('/api/state')).json()
                self.assertEqual(queued_state['projects'][0]['pending_prompt_count'], 1)
                self.assertNotIn(secret, json.dumps(queued_state))
                db.event('project1', 'stalled', {'reason': {'details': secret}})
                db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    ('job1', 'project1', '{}', 'finished', json.dumps({'stdout': secret,
                    'stderr': 'error', 'exit_code': 1, 'artifacts': []}), 1, 1))
                with patch('app.controller.command', new=AsyncMock(return_value={
                        'stdout': 'a' * 40 + '\0Commit ' + secret + '\0' + '2026-09-20T10:00:00Z\n', 'stderr': '', 'exit_code': 0})) as git:
                    detail_response = await client.get('/api/projects/project1')
                    self.assertEqual(detail_response.status, 200)
                    detail = await detail_response.json()
                    self.assertNotIn(secret, json.dumps(detail))
                    self.assertEqual(detail['events'][0]['payload']['reason']['details'], '[REDACTED]')
                    summary = detail['project']['block_summary']
                    self.assertEqual(summary['reasons'], ['Missing choice'])
                    self.assertEqual(summary['solution'], ['Choose A or B: [REDACTED]'])
                    self.assertTrue(summary['requires_user'])
                    self.assertEqual(summary['details'], '[REDACTED]')
                    self.assertEqual(detail['jobs'][0]['stdout'], '[REDACTED]')
                    self.assertEqual(detail['jobs'][0]['exit_code'], 1)
                    self.assertEqual(detail['commits'][0]['subject'], 'Commit [REDACTED]')
                    git.assert_awaited_once()
                self.assertEqual((await client.get('/api/projects/missing')).status, 400)
                body = {'action': 'logout'}
                self.assertEqual((await client.post('/api/action', json=body)).status, 403)
                self.assertEqual((await client.post('/api/action', json=body,
                    headers={'X-CSRF-Token': state['csrf'], 'Origin': 'http://evil.example'})).status, 403)
                self.assertEqual((await client.post('/api/action', json=body,
                    headers={'X-CSRF-Token': state['csrf']})).status, 200)
                self.assertEqual((await client.get('/api/state')).status, 401)
                self.assertEqual((await client.get('/api/projects/project1')).status, 401)

                async def attempt(index):
                    nonce = str(index)
                    app['login_tokens'][nonce] = __import__('time').monotonic() + 300
                    response = await client.post('/login', data={'password': 'wrong'},
                        headers={'Cookie': 'codexpi_login=' + nonce})
                    return response.status

                codes = await asyncio.gather(*(attempt(i) for i in range(12)))
                self.assertEqual(codes.count(401), 5)
                self.assertEqual(codes.count(429), 7)
                self.assertEqual(db.conn.execute('SELECT failures FROM login_attempts').fetchone()[0], 5)


if __name__ == '__main__':
    unittest.main()
