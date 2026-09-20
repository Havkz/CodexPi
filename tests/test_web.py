import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

from app.common import Redactor, password_hash
from app.db import Database
from app.web import make_app


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
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual((await client.get('/', headers={'Host': 'evil.example'})).status, 403)
                response = await client.get('/')
                cookie = response.cookies['codexpi_login']
                self.assertTrue(cookie['httponly'])
                self.assertEqual(cookie['samesite'], 'Strict')
                self.assertEqual((await client.post('/login', data={'password': 'wrong'})).status, 401)
                self.assertEqual((await client.post('/login', data={'password': 'test-pass'})).status, 403)
                await client.get('/')
                response = await client.post('/login', data={'password': 'test-pass'}, allow_redirects=False)
                self.assertEqual(response.status, 303)
                self.assertTrue(response.cookies['codexpi']['httponly'])
                state = await (await client.get('/api/state')).json()
                self.assertNotIn('password_hash', str(state))
                body = {'action': 'logout'}
                self.assertEqual((await client.post('/api/action', json=body)).status, 403)
                self.assertEqual((await client.post('/api/action', json=body,
                    headers={'X-CSRF-Token': state['csrf'], 'Origin': 'http://evil.example'})).status, 403)
                self.assertEqual((await client.post('/api/action', json=body,
                    headers={'X-CSRF-Token': state['csrf']})).status, 200)
                self.assertEqual((await client.get('/api/state')).status, 401)

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
