import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

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
        block = self.root / 'first/.codexpi/block.json'
        block.parent.mkdir()
        block.write_text('{"reason":"Old blocker"}')
        controller.db.update('first', block_reason=block.read_text(), windows_required=1)
        controller.record_goal(controller.db.get('first'), {'status': 'active'})
        self.assertIsNone(controller.db.get('first')['operation'])
        self.assertIsNone(controller.db.get('first')['block_reason'])
        self.assertEqual(controller.db.get('first')['windows_required'], 0)
        self.assertFalse(block.exists())
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
                            (5, 'thread/resume', {'threadId': 'first', 'history': ['replacement']}),
                            (6, 'thread/compact/start', {'threadId': 'second'}),
                            (7, 'thread/shellCommand', {'threadId': 'second'}),
                            (8, 'process/spawn', {}), (9, 'command/exec', {}),
                            (10, 'thread/inject_items', {'threadId': 'second'})):
                        await socket.send_json({'id': ident, 'method': method, 'params': params})
                        self.assertIn('error', await socket.receive_json())
                    self.assertEqual(len(calls), before)
                    await socket.send_json({'id': 11, 'method': 'thread/settings/update', 'params': {
                        'threadId': 'first', 'cwd': '/outside', 'permissions': 'danger-full-access'}})
                    self.assertIn('result', await socket.receive_json())
                    self.assertEqual(calls[-1][1]['cwd'], str(self.root / 'first'))
                    self.assertEqual(calls[-1][1]['sandboxPolicy']['type'], 'workspaceWrite')
                    self.assertNotIn('permissions', calls[-1][1])
                    with patch('app.lifecycle.begin', AsyncMock()) as rename:
                        await socket.send_json({'id': 12, 'method': 'thread/name/set', 'params': {
                            'threadId': 'first', 'name': 'New name'}})
                        self.assertIn('result', await socket.receive_json())
                        rename.assert_awaited_once_with(controller, 'first', 'rename', name='New name', defer=True)

    async def test_release_only_detached_idle_persisted_goals(self):
        controller = self.controller
        controller.last_idle_cleanup = 0
        controller.source = SimpleNamespace(rows=lambda: {'first': {'status': 'paused'}, 'second': {'status': 'paused'}})
        controller.native = SimpleNamespace(rpc=AsyncMock(return_value={'thread': {'status': {'type': 'idle'}}}))
        controller.cancel_wakes = AsyncMock()
        calls = []
        async def command(*args, **kwargs):
            calls.append(args)
            return {'exit_code': 0, 'stdout': '1' if 'second:0.0' in args else '0', 'stderr': ''}
        with patch('app.controller.command', command):
            await controller.release_idle_tuis()
        self.assertEqual([args for args in calls if args[1] == 'kill-session'], [('tmux', 'kill-session', '-t', '=first')])
        self.assertEqual(controller.db.get('first')['codex_session_id'], 'first')
        self.assertEqual(controller.db.get('first')['goal_status'], 'paused')
        for excluded in ('active', 'usage limited'):
            controller.last_idle_cleanup = 0
            controller.db.update('first', goal_status=excluded)
            calls.clear()
            with patch('app.controller.command', command):
                await controller.release_idle_tuis()
            self.assertFalse(any(args[1] == 'kill-session' for args in calls))
        controller.db.update('first', goal_status='paused', operation=json.dumps({'kind': 'resume'}))
        controller.last_idle_cleanup = 0
        calls.clear()
        with patch('app.controller.command', command):
            await controller.release_idle_tuis()
        self.assertFalse(any(args[1] == 'kill-session' for args in calls))

    async def test_unsnooze_wake_is_journaled_gated_and_never_an_argv_prompt(self):
        controller = self.controller
        controller.health_errors = {}
        controller.select('first')
        controller.db.update('first', goal_status='usage limited')
        controller.db.update('second', goal_status='usage limited')
        now = time.time() * 1000
        item = {'key': 'first-stop', 'sessionId': 'first', 'status': 'stopped',
                'resetSource': 'parsed', 'resetAt': now - 1000}
        sessions = [{**item, 'key': 'second-stop', 'sessionId': 'second'}, item]
        calls = []

        async def command(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('unsnooze', 'cancel'):
                # A crash after cancellation must not lose the native wake intent.
                self.assertEqual(json.loads(controller.db.get('first')['operation'])['source'], 'unsnooze')
            return {'exit_code': 0, 'stdout': json.dumps({'sessions': sessions}), 'stderr': ''}

        async def poll():
            controller.last_unsnooze_poll = 0
            await controller.selective_wake()

        with patch('app.controller.command', command):
            for field, value in (('resetSource', 'fallback'), ('resetAt', now + 3600000),
                                 ('status', 'resumed'), ('sessionId', 'unmapped')):
                original = item[field]
                item[field] = value
                await poll()
                self.assertIsNone(controller.db.get('first')['operation'])
                item[field] = original
            for state in ('paused', 'stalled', 'limited by budget', 'complete'):
                controller.db.update('first', goal_status=state)
                await poll()
                self.assertIsNone(controller.db.get('first')['operation'])
            controller.db.update('first', goal_status='usage limited')
            controller.db.set_setting('pause_all', True)
            await poll()
            self.assertIsNone(controller.db.get('first')['operation'])
            controller.db.set_setting('pause_all', False)
            await poll()
            operation = controller.db.get('first')['operation']
            self.assertEqual(json.loads(operation)['unsnooze_key'], 'first-stop')
            self.assertIsNone(controller.db.get('second')['operation'])

            # Simulated controller restart: only SQLite survives, no TUI is alive.
            controller.db.conn.close()
            controller.db = Database(self.root / 'test.db')
            controller.attach_ready = AsyncMock()
            controller.slash = AsyncMock()
            await controller.resume_ready()
            controller.attach_ready.assert_awaited_once()
            controller.slash.assert_not_awaited()
            self.assertEqual(controller.db.get('first')['operation'], operation)
            controller.tui_connections['first'] = {1: time.monotonic() - 2}
            controller.db.set_setting('pause_all', True)
            await controller.resume_ready()
            controller.slash.assert_not_awaited()
            controller.db.set_setting('pause_all', False)
            controller.db.update('first', queue_position=2)
            await controller.resume_ready()
            controller.slash.assert_not_awaited()
            self.assertIsNone(controller.db.get('first')['operation'])
            controller.db.update('first', queue_position=1)
            await poll()
            await controller.resume_ready()
            self.assertEqual(controller.slash.await_args.args[1], '/goal resume')
            await controller.resume_ready()
            controller.slash.assert_awaited_once()
            controller.record_goal(controller.db.get('first'), {'status': 'active'})
            self.assertIsNone(controller.db.get('first')['operation'])
        self.assertFalse(any('resume-now' in args for args in calls))
        self.assertFalse(any(args[:2] == ('unsnooze', 'cancel') and args[-1] != 'first-stop' for args in calls))


if __name__ == '__main__':
    unittest.main()
