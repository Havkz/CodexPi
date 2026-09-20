import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.common import Redactor
from app.controller import Controller
from app.db import Database
from app.native import tui_proxy


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        controller = Controller.__new__(Controller)
        controller.root = self.root
        controller.db = Database(self.root / 'test.db')
        controller.lock = asyncio.Lock()
        controller.redactor = Redactor(self.root)
        controller.tui_connections = {}
        controller.unsnooze = {}
        controller.wait_idle = AsyncMock()
        self.controller = controller
        for name in ('first', 'second'):
            path = self.root / name
            path.mkdir()
            controller.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                codex_session_id,tmux_session_name,created_at,updated_at,queue_position)
                VALUES (?,?,?,?,?,?,?,?,?)''', (name, name, name, str(path), name, name, time.time(), time.time(),
                                                1 if name == 'first' else 2))
            controller.db.update(name, lifecycle='ready')

    def tearDown(self):
        self.controller.db.conn.close()
        self.temp.cleanup()

    async def test_pending_resume_keeps_selection_until_ack(self):
        controller = self.controller
        controller.select('first')
        controller.db.update('first', operation=json.dumps({'kind': 'resume', 'requested_at': time.time()}))
        controller.source = type('Source', (), {'rows': lambda self: {'first': {'status': 'paused'}}})()
        await controller.poll_goals()
        self.assertEqual(controller.db.setting('selected'), 'first')
        controller.record_goal(controller.db.get('first'), {'status': 'active'})
        self.assertIsNone(controller.db.get('first')['operation'])
        controller.source.rows = lambda: {'first': {'status': 'paused'}}
        await controller.poll_goals()
        controller.wait_idle.assert_awaited_once()
        self.assertIsNone(controller.db.setting('selected'))

    async def test_gate_pauses_second_goal_before_native_execution(self):
        controller = self.controller
        controller.select('first')
        calls = []

        class Upstream:
            async def rpc(self, method, params):
                calls.append((method, params))
                if method == 'thread/goal/get':
                    return {'goal': None}
                if method == 'thread/goal/set':
                    return {'goal': {'status': params['status']}}
                return {}

            async def close(self):
                pass

        upstream = Upstream()
        app = web.Application()
        app['controller'] = controller
        app['sockets'] = set()
        app.router.add_get('/', tui_proxy)
        with patch('app.native.Native.connect', AsyncMock(return_value=upstream)):
            async with TestClient(TestServer(app)) as client:
                async with client.ws_connect('/') as socket:
                    # Omitted status also defaults to active in native Codex, and must be gated.
                    await socket.send_json({'id': 1, 'method': 'thread/goal/set', 'params': {
                        'threadId': 'second', 'objective': 'EXACT user objective'}})
                    response = await socket.receive_json()
                    self.assertEqual(response['result']['goal']['status'], 'paused')
                    self.assertEqual(calls[-1][1]['objective'], 'EXACT user objective')
                    self.assertEqual(controller.db.setting('selected'), 'first')
                    before = len(calls)
                    for ident, method, params in ((2, 'turn/start', {'threadId': 'second'}),
                            (3, 'thread/fork', {'threadId': 'first'}),
                            (4, 'thread/queue/start', {'threadId': 'first'}),
                            (5, 'thread/resume', {'threadId': 'first', 'history': ['replacement']})):
                        await socket.send_json({'id': ident, 'method': method, 'params': params})
                        self.assertIn('error', await socket.receive_json())
                    self.assertEqual(len(calls), before)


if __name__ == '__main__':
    unittest.main()
