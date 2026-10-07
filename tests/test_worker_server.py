import asyncio
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.common import Redactor, SignedChannel
from app.controller import Controller
from app.db import Database
from app.worker_server import dispatch_pending, submit_job, worker_socket


class WorkerAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        c = Controller.__new__(Controller)
        c.root = Path(self.temp.name)
        c.db = Database(c.root / 'test.db')
        self.addCleanup(c.db.conn.close)
        command = patch('app.worker_server.command', AsyncMock())
        command.start()
        self.addCleanup(command.stop)
        c.lock, c.worker_send_lock = asyncio.Lock(), asyncio.Lock()
        c.worker = SimpleNamespace(closed=False, send_json=AsyncMock())
        c.worker_key = SimpleNamespace(sign=lambda body: body)
        c.worker_seen = time.monotonic()
        c.redactor = Redactor(c.root)
        c.native = SimpleNamespace(rpc=AsyncMock(return_value={'goal': {'status': 'active'}}))
        for name, status, position in [('first', 'active', 1), ('second', 'paused', 2)]:
            c.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                codex_session_id,tmux_session_name,github_repo,goal_status,lifecycle,queue_position,
                created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (name, name, name, str(c.root / name), name, name, 'owner/' + name,
                 status, 'ready', position, 1, 1))
        c.db.set_setting('selected', 'first')
        self.c = c
        self.body = {'project_id': 'first', 'commit': 'a' * 40, 'argv': ['python', '--version']}

    def pending(self, ident, project):
        self.c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,created_at,updated_at) VALUES(?,?,?,?,?)',
                              (ident, project, json.dumps(self.body), 1, 1))

    def test_signed_heartbeat_required_and_expires_at_sixty_seconds(self):
        c = self.c
        c.worker_seen = 0
        with patch('app.controller.time.monotonic', return_value=5):
            self.assertFalse(c.windows_online)  # Connected is not a signed alive.
            c.worker_seen = 1
            self.assertTrue(c.windows_online)
        with patch('app.controller.time.monotonic', return_value=61):
            self.assertFalse(c.windows_online)

    async def test_signed_heartbeats_retry_deferred_wake_once_per_availability(self):
        c = self.c
        c.config = {'worker_secret': 's' * 32}
        c.worker, c.worker_key, c.worker_seen = None, None, 0
        c.db.update('first', goal_status='stalled', windows_required=1,
                    block_reason=json.dumps({'reason': 'Windows offline', 'requires_user': False}))
        c.db.set_setting('selected', 'second')
        app = web.Application()
        app['controller'] = c
        app.router.add_get('/worker', worker_socket)
        delivered = asyncio.Event()
        with patch('app.worker_server.dispatch_pending', AsyncMock(side_effect=lambda _: delivered.set())):
            async with TestClient(TestServer(app)) as client:
                async with client.ws_connect('/worker') as socket:
                    challenge = (await socket.receive_json())['challenge']
                    channel = SignedChannel(c.config['worker_secret'], challenge, 'worker')
                    await socket.send_json(channel.sign({'type': 'hello'}))
                    self.assertEqual(channel.verify(await socket.receive_json()), {'type': 'accepted'})
                    await socket.send_json(channel.sign({'type': 'inventory', 'jobs': []}))

                    async def heartbeat():
                        delivered.clear()
                        await socket.send_json(channel.sign({'type': 'alive'}))
                        await asyncio.wait_for(delivered.wait(), 2)

                    await heartbeat()
                    self.assertIsNone(c.db.get('first')['operation'])  # Other selected project retains its slot.
                    c.db.set_setting('selected', None)
                    await heartbeat()  # Already online, but the slot has become eligible.
                    self.assertIsNotNone(c.db.get('first')['operation'])
                    operation = json.loads(c.db.get('first')['operation'])
                    self.assertEqual(operation['source'], 'windows')
                    operation['error'] = 'TUI confirmation failed'
                    c.db.update('first', operation=json.dumps(operation))
                    await heartbeat()
                    self.assertEqual(json.loads(c.db.get('first')['operation']), operation)
                    c.worker_seen = time.monotonic() - 61
                    c.db.set_setting('manual_pause/first', True)
                    await heartbeat()
                    self.assertEqual(json.loads(c.db.get('first')['operation']), operation)
                    c.db.set_setting('manual_pause/first', False)
                    await heartbeat()
                    retry = json.loads(c.db.get('first')['operation'])
                    self.assertNotEqual(retry['id'], operation['id'])
                    await heartbeat()
                    self.assertEqual(json.loads(c.db.get('first')['operation']), retry)

    async def test_unselected_offline_request_cannot_overwrite_pause_or_user_block(self):
        c = self.c
        c.worker_seen = time.monotonic() - 61
        c.db.update('second', block_reason=json.dumps({'requires_user': True, 'reason': 'Need decision'}))
        before = c.db.get('second')
        with self.assertRaisesRegex(ValueError, 'selected, executing'):
            await submit_job(c, dict(self.body, project_id='second'))
        self.assertEqual(c.db.get('second'), before)
        c.native.rpc.assert_not_awaited()
        self.assertFalse((c.root / 'second/.codexpi/block.json').exists())
        self.assertEqual(c.db.conn.execute('SELECT count(*) FROM events').fetchone()[0], 0)

    async def test_submission_checks_holds_queue_lifecycle_and_actual_native_goal(self):
        c = self.c
        for field, value in [('goal_status', 'paused'), ('goal_status', 'usage limited'),
                             ('goal_status', 'complete'), ('queue_position', 2),
                             ('operation', '{}'), ('lifecycle', 'deleting')]:
            old = c.db.get('first')[field]
            c.db.update('first', **{field: value})
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'selected, executing'):
                await submit_job(c, self.body)
            c.db.update('first', **{field: old})
        for setting in ('pause_all', 'manual_pause/first'):
            c.db.set_setting(setting, True)
            with self.assertRaisesRegex(ValueError, 'selected, executing'):
                await submit_job(c, self.body)
            c.db.set_setting(setting, False)
        for goal in (None, {'status': 'paused'}, {'status': 'usageLimited'}, {'status': 'complete'}):
            c.native.rpc.return_value = {'goal': goal}
            with self.assertRaisesRegex(ValueError, 'active native goal'):
                await submit_job(c, self.body)
        self.assertEqual(c.db.conn.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        c.worker.send_json.assert_not_awaited()

    async def test_offline_valid_request_blocks_only_after_validation(self):
        c = self.c
        c.worker_seen = time.monotonic() - 61
        with self.assertRaisesRegex(ValueError, 'argv'):
            await submit_job(c, dict(self.body, argv=[]))
        self.assertEqual(c.db.get('first')['goal_status'], 'active')
        with self.assertRaisesRegex(ValueError, 'Windows offline'):
            await submit_job(c, self.body)
        p = c.db.get('first')
        self.assertEqual(p['goal_status'], 'stalled')
        self.assertTrue(p['windows_required'])
        self.assertFalse(json.loads(p['block_reason'])['requires_user'])
        c.native.rpc.assert_any_await('thread/goal/set', {'threadId': 'first', 'status': 'blocked'})

    async def test_dispatch_rechecks_queue_and_does_not_head_of_line_block(self):
        c = self.c
        self.pending('old-paused', 'second')
        self.pending('also-paused', 'second')
        self.pending('allowed', 'first')
        await dispatch_pending(c)
        old = c.db.conn.execute('SELECT * FROM jobs WHERE job_id=?', ('old-paused',)).fetchone()
        self.assertEqual(old['status'], 'finished')
        self.assertTrue(json.loads(old['result'])['cancelled'])
        self.assertEqual(c.worker.send_json.await_args.args[0]['job_id'], 'allowed')
        await dispatch_pending(c)
        c.worker.send_json.assert_awaited_once()

    async def test_native_transition_and_unavailable_probe_after_durable_acceptance(self):
        c = self.c
        c.native.rpc.side_effect = [{'goal': {'status': 'active'}}, {'goal': {'status': 'usageLimited'}}]
        result = await submit_job(c, self.body)
        row = c.db.conn.execute('SELECT * FROM jobs WHERE job_id=?', (result['job_id'],)).fetchone()
        self.assertEqual(row['status'], 'finished')
        self.assertTrue(json.loads(row['result'])['cancelled'])
        c.worker.send_json.assert_not_awaited()
        c.native.rpc.side_effect = [{'goal': {'status': 'active'}}, ConnectionError('native reconnect')]
        with self.assertLogs('worker', level='WARNING'):
            result = await submit_job(c, self.body)
        self.assertEqual(c.db.conn.execute('SELECT status FROM jobs WHERE job_id=?',
                                          (result['job_id'],)).fetchone()[0], 'pending')
        c.native.rpc.side_effect = None
        await dispatch_pending(c)
        self.assertEqual(c.worker.send_json.await_args.args[0]['job_id'], result['job_id'])

    async def test_admission_and_dispatch_serialize_with_pause_and_keep_ambiguous_delivery(self):
        c = self.c
        with patch('app.worker_server.command', AsyncMock()):
            result = await asyncio.wait_for(submit_job(c, self.body), 2)
        self.assertEqual(c.worker.send_json.await_args.args[0]['job_id'], result['job_id'])
        c.db.conn.execute('DELETE FROM jobs')
        self.pending('held', 'first')
        async with c.lock:
            task = asyncio.create_task(dispatch_pending(c))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            c.db.set_setting('pause_all', True)
        await asyncio.wait_for(task, 2)
        self.assertTrue(json.loads(c.db.conn.execute('SELECT result FROM jobs').fetchone()[0])['cancelled'])
        c.db.set_setting('pause_all', False)
        c.db.conn.execute('DELETE FROM jobs')
        self.pending('ambiguous', 'first')
        c.worker.send_json.side_effect = ConnectionError('lost after send')
        await dispatch_pending(c)
        self.assertEqual(c.db.conn.execute('SELECT status FROM jobs').fetchone()[0], 'sent')
        # Do not invent a safe cancellation/retry after a possibly delivered command.
        await dispatch_pending(c)
        self.assertEqual(c.worker.send_json.await_count, 2)


if __name__ == '__main__':
    unittest.main()
