import asyncio
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
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / 'web.db')
            root = Path(__file__).resolve().parents[1]
            controller = SimpleNamespace(root=root, db=db, redactor=Redactor(temp),
                config={'lan_subnet': '192.168.2.0/24', 'password_hash': password_hash('test-pass'),
                        'github_account': 'test'}, windows_online=False, bot=None, unsnooze={})
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
                state = await (await client.get('/api/state')).json()
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
            db.conn.close()


if __name__ == '__main__':
    unittest.main()
