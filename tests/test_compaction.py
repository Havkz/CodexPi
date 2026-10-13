import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.compaction import tick, warning
from app.controller import Controller
from app.db import Database
from app.worker_server import job_denial


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        c = Controller.__new__(Controller)
        c.root, c.db, c.maintenance = self.root, Database(self.root / 'test.db'), False
        self.addCleanup(c.db.conn.close)
        self.c = c
        self.sid = '01a072f0-df80-7152-aff3-a5e66960c071'
        self.session_file = 'rollout-2026-09-05T20-59-43-' + self.sid + '.jsonl'
        c.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,codex_session_id,
            tmux_session_name,goal_status,lifecycle,queue_position,created_at,updated_at)
            VALUES ('first','first','first',?,?,'first','active','ready',1,1,1)''', (str(self.root), self.sid))
        c.db.set_setting('selected', 'first')
        self.cache = self.root / 'token-optimizer' / ('quality-cache-' + self.session_file.removesuffix('.jsonl') + '.json')
        self.cache.parent.mkdir()
        self.sample = {'session_file': self.session_file, 'timestamp': '2026-01-01T00:00:00+00:00', 'compactions': 1,
            'fill_warning': {'level': 'CRITICAL', 'message': '85% context fill, compact now'}}
        self.cache.write_text(json.dumps(self.sample))
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root)})
        env.start(); self.addCleanup(env.stop)
        self.goal = {'status': 'active', 'createdAt': 1, 'objective': 'Keep working'}
        self.busy = True
        self.turns = [{'id': 'work', 'status': 'inProgress', 'items': []}]
        self.compact_calls = 0
        self.uncertain = False
        async def rpc(method, params, **kwargs):
            if method == 'thread/goal/get': return {'goal': dict(self.goal) if self.goal else None}
            if method == 'thread/goal/set':
                self.goal['status'] = params['status']; return {'goal': dict(self.goal)}
            if method == 'thread/read':
                return {'thread': {'id': self.sid, 'cwd': str(self.root), 'path': self.session_file,
                    'status': {'type': 'active' if self.busy else 'idle'}}}
            if method == 'thread/turns/list':
                return {'data': self.turns if params.get('itemsView') == 'full'
                        else [{**turn, 'items': []} for turn in self.turns]}
            if method == 'thread/loaded/list': return {'data': [self.sid]}
            if method == 'thread/compact/start':
                self.assertFalse(self.busy)
                self.compact_calls += 1
                if self.uncertain: raise TimeoutError('Delivery unknown')
                self.busy = True
                self.turns = [{'id': 'compact', 'status': 'inProgress', 'items': [{'type': 'contextCompaction'}]}]
                return {}
            self.fail('Unexpected native call ' + method)
        c.native = SimpleNamespace(rpc=AsyncMock(side_effect=rpc))

    async def test_waits_for_work_allows_its_windows_tools_and_restores_once_after_restart(self):
        await tick(self.c)
        self.assertEqual(self.goal['status'], 'paused')
        self.assertEqual(self.compact_calls, 0)
        self.assertTrue(self.c.account_holds_goal(self.c.db.get('first')))
        self.assertIsNone(await job_denial(self.c, self.c.db.get('first')))
        self.busy = False; self.turns[0]['status'] = 'completed'
        await tick(self.c)
        self.assertEqual(self.compact_calls, 1)
        self.c.db.conn.close(); self.c.db = Database(self.root / 'test.db'); self.addCleanup(self.c.db.conn.close)
        await tick(self.c)
        self.assertEqual(self.compact_calls, 1)
        self.busy = False; self.turns[0].update(status='completed', completedAt=time.time())
        await tick(self.c); await tick(self.c)
        self.assertEqual(self.goal['status'], 'active')
        self.assertEqual(self.compact_calls, 1)
        self.assertIsNone(self.c.db.get('first')['operation'])
        self.assertEqual(self.c.db.setting('compact_result/first')['outcome'], 'completed')

    async def test_holds_wrong_cache_and_existing_manual_compaction_do_not_start_new_work(self):
        for key in ('pause_all', 'manual_pause/first'):
            self.c.db.set_setting(key, True); await tick(self.c)
            self.assertIsNone(self.c.db.get('first')['operation'])
            self.c.db.set_setting(key, False)
        self.c.db.update('first', goal_status='paused'); await tick(self.c)
        self.assertIsNone(self.c.db.get('first')['operation'])
        self.c.db.update('first', goal_status='active')
        self.cache.write_text(json.dumps({**self.sample, 'session_file': 'another.jsonl'}))
        self.assertIsNone(warning(self.root, self.sid))
        self.cache.write_text('{broken'); self.assertIsNone(warning(self.root, self.sid))
        self.cache.write_text(json.dumps(self.sample))
        self.busy = False
        self.turns = [{'id': 'manual-compact', 'status': 'completed', 'completedAt': time.time(),
                       'items': [{'type': 'contextCompaction'}]}]
        await tick(self.c); await tick(self.c)
        self.assertEqual(self.compact_calls, 0)
        self.assertEqual(self.goal['status'], 'active')

    async def test_uncertain_delivery_is_not_repeated_and_user_pause_is_never_undone(self):
        self.busy = False; self.uncertain = True; self.turns[0]['status'] = 'completed'
        await tick(self.c)
        state = json.loads(self.c.db.get('first')['operation'])
        self.assertTrue(state['uncertain'])
        state['sent_at'] -= 31
        self.c.db.update('first', operation=json.dumps(state))
        await tick(self.c)
        self.assertEqual(self.goal['status'], 'paused')
        self.assertIsNotNone(self.c.db.get('first')['operation'])
        self.turns = [{'id': 'failed-compact', 'status': 'failed', 'items': [{'type': 'contextCompaction'}]}]
        await tick(self.c); await tick(self.c)
        self.assertEqual(self.compact_calls, 1)
        self.assertEqual(self.c.db.setting('compact_result/first')['outcome'], 'failed')
        self.cache.write_text(json.dumps({**self.sample, 'compactions': 2}))
        self.busy = True
        await tick(self.c)
        self.c.db.set_setting('manual_pause/first', True)
        await tick(self.c)
        self.assertEqual(self.goal['status'], 'paused')
        self.assertIsNone(self.c.db.get('first')['operation'])

    async def test_prompt_without_goal_can_compact_without_creating_a_goal(self):
        self.goal = None; self.busy = False; self.turns[0]['status'] = 'completed'
        await tick(self.c)
        self.busy = False; self.turns[0].update(status='completed', completedAt=time.time())
        await tick(self.c)
        self.assertEqual(self.compact_calls, 1)
        self.assertIsNone(self.goal)

    async def test_explicit_rejection_restores_continuation_without_retry_or_account_change(self):
        from app.accounts import request_switch
        from app.native import NativeError
        self.busy = False; self.turns[0]['status'] = 'completed'
        original = self.c.native.rpc.side_effect
        async def reject(method, params, **kwargs):
            if method == 'thread/compact/start':
                error = NativeError('Request rejected'); error.rejected = True
                raise error
            return await original(method, params, **kwargs)
        self.c.native.rpc.side_effect = reject
        await tick(self.c)
        with self.assertRaisesRegex(ValueError, 'compaction is pending'):
            await request_switch(self.c, 'another-account')
        await tick(self.c); await tick(self.c)
        self.assertEqual(self.goal['status'], 'active')
        self.assertEqual(self.c.db.setting('compact_result/first')['outcome'], 'failed')
        self.assertEqual(sum(c.args[0] == 'thread/compact/start' for c in self.c.native.rpc.await_args_list), 1)

    async def test_blocked_head_compacts_without_answering_its_question_or_resuming_goal(self):
        self.goal['status'] = 'blocked'; self.busy = False; self.turns[0]['status'] = 'completed'
        self.c.db.set_setting('selected', None)
        self.c.db.update('first', goal_status='stalled', block_reason='{"requires_user":true,"question":"Windows acceptance?"}')
        await tick(self.c)
        self.assertEqual(self.goal['status'], 'blocked')
        self.busy = False; self.turns[0].update(status='completed', completedAt=time.time())
        await tick(self.c); await tick(self.c)
        self.assertEqual(self.compact_calls, 1)
        self.assertEqual(self.goal['status'], 'blocked')
        self.assertIsNone(self.c.db.setting('selected'))
        self.assertTrue(json.loads(self.c.db.get('first')['block_reason'])['requires_user'])

    async def test_tui_resume_rejection_preserves_manual_pause_and_compaction_intent(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from app.native import Native, tui_proxy
        from tests.test_scheduler import SchedulerTests
        fixture = SchedulerTests(); fixture.setUp()
        c = fixture.controller
        c.select('first')
        state = json.dumps({'kind': 'compact', 'phase': 'sent'})
        c.db.update('first', operation=state)
        c.db.set_setting('manual_pause/first', True)
        upstream = SimpleNamespace(rpc=AsyncMock(), close=AsyncMock())
        app = web.Application()
        app['controller'], app['sockets'] = c, set()
        app.router.add_get('/', tui_proxy)
        try:
            with patch.object(Native, 'connect', AsyncMock(return_value=upstream)):
                async with TestClient(TestServer(app)) as client:
                    async with client.ws_connect('/') as socket:
                        await socket.send_json({'id': 1, 'method': 'thread/goal/set',
                            'params': {'threadId': 'first', 'status': 'active'}})
                        self.assertIn('compaction is pending', (await socket.receive_json())['error']['message'])
                        self.assertTrue(c.db.setting('manual_pause/first'))
                        self.assertEqual(c.db.get('first')['operation'], state)
                        self.assertEqual(c.db.setting('selected'), 'first')
                        upstream.rpc.assert_not_awaited()
        finally:
            fixture.tearDown()
