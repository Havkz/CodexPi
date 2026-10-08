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
        controller.tui_peer_pids = {}
        controller.mapped_tui_ready = AsyncMock(side_effect=lambda project: bool(
            controller.tui_connections.get(project['project_id']) and time.monotonic() -
            min(controller.tui_connections[project['project_id']].values()) >= 1))
        controller.unsnooze = {}
        controller.health_errors = {}
        controller.wait_idle = AsyncMock()
        controller.pane_exists = AsyncMock(return_value=True)
        self.native_status = 'paused'
        self.goal_updated_at = int(time.time()) - 60
        self.thread_status = 'idle'
        async def native_rpc(method, params, **kwargs):
            if method == 'thread/goal/get':
                return {'goal': {'status': self.native_status, 'updatedAt': self.goal_updated_at} if self.native_status else None}
            if method == 'thread/read':
                return {'thread': {'id': params['threadId'], 'cwd': str(self.root / params['threadId']),
                                   'status': {'type': self.thread_status}}}
            if method == 'account/rateLimits/read':
                return {'ordinaryUsageAllowed': True, 'rateLimits': {}}
            return {}
        controller.native = SimpleNamespace(rpc=AsyncMock(side_effect=native_rpc))
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

    async def test_user_prompt_queue_survives_restart_and_never_starts_a_second_turn(self):
        from app.prompts import active, reconcile, submit
        c = self.controller
        c.select('first')
        c.db.update('first', goal_status='active')
        c.db.update('second', queue_position=None)  # New prompt on a previously completed project.
        params = {'threadId': 'second', 'clientUserMessageId': 'user-message',
                  'input': [{'type': 'text', 'text': 'User prompt'}], 'cwd': '/outside',
                  'permissions': 'danger-full-access', 'runtimeWorkspaceRoots': ['/outside']}
        c.source = SimpleNamespace(rows=lambda: {})
        upstream = SimpleNamespace(rpc=AsyncMock())
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, 'Prompt saved'):
                await submit(c, c.db.get('second'), params, upstream)
        upstream.rpc.assert_not_awaited()
        self.assertEqual(len(c.db.setting('prompts/second')), 1)
        self.assertEqual(c.db.get('second')['queue_position'], 2)
        c.db.conn.close()
        c.db = Database(self.root / 'test.db')
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'first')
        c.db.set_setting('selected', None)
        c.db.update('first', goal_status='paused')
        c.db.set_setting('manual_pause/second', True)
        await c.advance_queue()
        self.assertIsNone(c.db.setting('selected'))

        c.db.set_setting('manual_pause/second', False)
        original_rpc = c.native.rpc
        async def rpc(method, args, **kwargs):
            if method == 'turn/start':
                self.assertEqual(active(c, c.db.get('second'))['phase'], 'submitting')
                return {'turn': {'id': 'real-native-turn', 'status': 'inProgress'}}
            if method == 'thread/turns/list':
                return {'data': [{'id': 'real-native-turn', 'status': 'completed'}]}
            return await original_rpc(method, args, **kwargs)
        c.native.rpc = AsyncMock(side_effect=rpc)
        await c.advance_queue()
        sent = next(call.args[1] for call in c.native.rpc.await_args_list if call.args[0] == 'turn/start')
        self.assertEqual(sent['cwd'], str(self.root / 'second'))
        self.assertEqual(sent['runtimeWorkspaceRoots'], [str(self.root / 'second')])
        self.assertEqual(sent['sandboxPolicy']['type'], 'workspaceWrite')
        self.assertNotIn('permissions', sent)
        self.assertEqual(c.db.setting('selected'), 'second')
        self.assertEqual(c.db.get('second')['goal_status'], 'active')
        # A repeated native client message gets its original receipt, not a second turn.
        receipt = await submit(c, c.db.get('second'), params, upstream)
        self.assertEqual(receipt['turn']['id'], 'real-native-turn')
        upstream.rpc.assert_not_awaited()
        c.db.conn.close()
        c.db = Database(self.root / 'test.db')
        await reconcile(c, c.db.get('second'))
        self.assertIsNone(active(c, c.db.get('second')))
        self.assertEqual(c.db.get('second')['goal_status'], 'paused')
        self.assertIsNone(c.db.setting('selected'))


    async def test_prompt_usage_error_survives_goal_poll_restart_and_reset_without_replay(self):
        c = self.controller
        sid = 'first'
        native_goal = {'status': 'paused', 'updatedAt': 10}
        turn_error = 'usageLimitExceeded'
        async def rpc(method, params, **kwargs):
            if method == 'thread/goal/get':
                return {'goal': native_goal}
            if method == 'thread/turns/list':
                return {'data': [{'id': 'quota-turn', 'status': 'failed',
                                  'error': {'codexErrorInfo': turn_error}}]}
            if method == 'thread/read':
                return {'thread': {'status': {'type': self.thread_status}}}
            self.fail('Unexpected native mutation: ' + method)
        c.native.rpc = AsyncMock(side_effect=rpc)
        c.source = SimpleNamespace(rows=lambda: {sid: {'status': 'paused', 'updated_at_ms': 10000}} if native_goal else {})
        c.attach_ready = AsyncMock()
        for native_goal in ({'status': 'paused', 'updatedAt': 10}, None):
            c.select(sid)
            c.db.set_setting('manual_pause/' + sid, False)
            c.db.update(sid, goal_status='active')
            c.db.set_setting('prompt_active/' + sid, {'id': 'prompt', 'turn_id': 'quota-turn',
                'previous_status': 'paused', 'result': {'turn': {'id': 'quota-turn'}}})
            await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'usage limited')
            c.db.conn.close()
            c.db = Database(self.root / 'test.db')
            await c.recover()
            await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'usage limited')
            self.assertFalse(c.db.setting('manual_pause/' + sid, False))
            # Only an actual post-reset account observation can clear this turn
            # error; never resend a partially executed prompt or resume its goal.
            reset = time.time() - 60
            c.db.update(sid, usage_limit=json.dumps({'resetAt': reset * 1000, 'resetSource': 'native-account'}))
            c.db.set_setting('account_usage', {'checked_at': reset - 1, 'ordinaryUsageAllowed': True})
            await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'usage limited')
            c.db.set_setting('account_usage', {'checked_at': time.time(), 'ordinaryUsageAllowed': True})
            self.thread_status = 'active'
            await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'usage limited')
            self.thread_status = 'idle'
            record_status = c.record_status
            def interrupted_reset(*args, **kwargs):
                record_status(*args, **kwargs)
                raise RuntimeError('interrupted reset transaction')
            with patch.object(c, 'record_status', side_effect=interrupted_reset):
                with self.assertRaisesRegex(RuntimeError, 'interrupted reset'):
                    await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'usage limited')
            self.assertIsNotNone(c.db.setting('prompt_limit/' + sid))
            await c.poll_goals()
            self.assertEqual(c.db.get(sid)['goal_status'], 'paused')
            self.assertIsNone(c.db.setting('selected'))
            self.assertIsNone(c.db.setting('prompt_limit/' + sid))
            self.assertIsNone(c.db.get(sid)['usage_limit'])
        self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='usage limited'").fetchone()[0], 2)
        turn_error = 'responseStreamDisconnected'
        c.db.set_setting('prompt_active/' + sid, {'id': 'not-quota', 'turn_id': 'quota-turn', 'previous_status': 'paused'})
        await c.poll_goals()
        self.assertEqual(c.db.get(sid)['goal_status'], 'paused')
        self.assertIsNone(c.db.setting('prompt_limit/' + sid))
        # Pause also cancels a terminal quota hold without needing a native goal.
        c.db.update(sid, goal_status='usage limited')
        c.db.set_setting('prompt_limit/' + sid, {'turn_id': 'quota-turn'})
        await c.pause(c.db.get(sid), manual=True)
        self.assertEqual(c.db.get(sid)['goal_status'], 'paused')
        self.assertIsNone(c.db.setting('prompt_limit/' + sid))

    async def test_cli_update_defers_for_users_execution_and_unknown_native_state(self):
        from app.maintenance import daily_update, idle
        c = self.controller
        async def rpc(method, params, **kwargs):
            if method == 'thread/loaded/list':
                return {'data': ['first']}
            if method == 'thread/read':
                return {'thread': {'status': {'type': self.thread_status}}}
            if method == 'thread/turns/list':
                return {'data': [{'status': 'failed'}]}
            return {}
        c.native.rpc = AsyncMock(side_effect=rpc)
        command = AsyncMock(return_value={'stdout': '0 1', 'stderr': '', 'exit_code': 0})
        with patch('app.maintenance.command', command):
            self.assertTrue(await idle(c))
            for field, value in (('goal_status', 'active'), ('operation', '{"kind":"resume"}'), ('lifecycle', 'deleting')):
                original = c.db.get('first')[field]
                c.db.update('first', **{field: value})
                self.assertFalse(await idle(c))
                c.db.update('first', **{field: original})
            command.return_value['stdout'] = '1 1'
            self.assertFalse(await idle(c))
            command.return_value['stdout'] = '0 1'
            self.thread_status = 'active'
            self.assertFalse(await idle(c))
            self.thread_status = 'systemError'
            self.assertTrue(await idle(c))
            c.db.set_setting('last_tui_activity', time.time())
            self.assertFalse(await idle(c))
            c.db.set_setting('last_tui_activity', 0)
            c.db.set_setting('cli_update', {'phase': 'complete', 'attempted_at': time.time()})
            command.reset_mock()
            await daily_update(c)
            command.assert_not_awaited()

    async def test_pause_releases_system_error_only_after_native_terminal_turn(self):
        c = self.controller
        del c.wait_idle  # Exercise the real shared queue/lifecycle idleness check.
        c.select('first')
        turn_status = 'failed'

        async def rpc(method, params):
            if method.startswith('thread/goal/'):
                return {'goal': {'status': 'paused'}}
            if method == 'thread/read':
                return {'thread': {'status': {'type': 'systemError'}}}
            if method == 'thread/turns/list':
                return {'data': [{'id': 'limited-turn', 'status': turn_status}] if turn_status else []}
            self.fail(method)

        c.native.rpc = AsyncMock(side_effect=rpc)
        await c.pause(c.db.get('first'), manual=True)
        self.assertIsNone(c.db.setting('selected'))
        self.assertTrue(c.db.setting('manual_pause/first'))
        # Error alone, an unknown state, or an executing turn is not idle proof.
        for turn_status in (None, 'unknown', 'inProgress'):
            c.select('first')
            with self.assertRaisesRegex(RuntimeError, 'idleness'):
                await c.pause(c.db.get('first'), manual=True)
            self.assertEqual(c.db.setting('selected'), 'first')

    async def test_recovery_records_native_limit_once_and_clears_resume_intent(self):
        c = self.controller
        c.select('first')
        c.db.update('first', operation=json.dumps({'kind': 'resume', 'sent_at': time.time() - 60}))
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'usage limited', 'updated_at_ms': 1800000000000}})
        c.attach_ready = AsyncMock()
        for _ in range(2):
            await c.recover()
            await c.poll_goals()
        self.assertEqual(c.db.get('first')['goal_status'], 'usage limited')
        self.assertIsNone(c.db.get('first')['operation'])
        self.assertEqual(c.db.setting('selected'), 'first')
        self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='usage limited'").fetchone()[0], 1)
        # A failed durable outbox write must not swallow the transition on retry.
        c.db.update('first', goal_status='active')
        with patch.object(c.db, 'event', side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):
                c.record_goal(c.db.get('first'), {'status': 'usageLimited'})
        self.assertEqual(c.db.get('first')['goal_status'], 'active')

    async def test_empty_goal_resume_restores_session_without_a_slash(self):
        c = self.controller
        self.native_status = None
        c.attach_ready = AsyncMock()
        c.slash = AsyncMock()
        result = await c.resume('first')
        self.assertIsNotNone(c.db.get('first')['operation'])
        self.assertIsNone(c.db.get('first')['resume_result'])
        await c.resume_ready()
        c.attach_ready.assert_awaited_once()
        self.assertEqual(await c.resume('first'), result)  # idempotent while pending
        self.assertEqual(c.db.setting('selected'), 'first')
        c.tui_connections['first'] = {1: time.monotonic() - 2}
        await c.resume_ready()
        c.slash.assert_not_awaited()
        self.assertIsNone(c.db.get('first')['operation'])
        self.assertEqual(json.loads(c.db.get('first')['resume_result'])['status'], 'restored')
        self.assertEqual(c.db.get('first')['goal_status'], 'paused')

    async def test_model_config_gate_accepts_only_native_selection_batch(self):
        c = self.controller
        upstream = SimpleNamespace(rpc=AsyncMock(return_value={}), close=AsyncMock())
        app = web.Application()
        app['controller'], app['sockets'] = c, set()
        app.router.add_get('/', tui_proxy)
        selection = {'edits': [
            {'keyPath': 'model', 'value': 'gpt-test', 'mergeStrategy': 'replace'},
            {'keyPath': 'model_reasoning_effort', 'value': 'medium', 'mergeStrategy': 'replace'}],
            'filePath': None, 'expectedVersion': None, 'reloadUserConfig': True}
        with patch('app.native.Native.connect', AsyncMock(return_value=upstream)):
            async with TestClient(TestServer(app)) as client:
                async with client.ws_connect('/') as socket:
                    async def rpc(method, params):
                        await socket.send_json({'id': 1, 'method': method, 'params': params})
                        return await socket.receive_json()
                    self.assertIn('error', await rpc('config/batchWrite', selection))
                    self.assertIn('result', await rpc('thread/resume', {'threadId': 'first'}))
                    self.assertIn('result', await rpc('config/batchWrite', selection))
                    self.assertEqual(upstream.rpc.await_args.args, ('config/batchWrite', selection))
                    cleared = json.loads(json.dumps(selection))
                    cleared['edits'][1]['value'] = None
                    self.assertIn('result', await rpc('config/batchWrite', cleared))
                    invalid = [dict(selection, filePath='/tmp/config.toml'), dict(selection, unknown=True),
                               dict(selection, edits=[]), dict(selection, edits=selection['edits'] * 2)]
                    for key, value, strategy in [('features.multi_agent', True, 'replace'),
                            ('sandbox_mode', 'danger-full-access', 'replace'), ('model', {}, 'replace'),
                            ('model', '', 'replace'), ('model', 'gpt-test', 'upsert'),
                            ('model_reasoning_effort', 'nonsense', 'replace'), ('profiles.x.model', 'gpt-test', 'replace')]:
                        invalid.append(dict(selection, edits=[{'keyPath': key, 'value': value, 'mergeStrategy': strategy}]))
                    before = upstream.rpc.await_count
                    for params in invalid:
                        self.assertIn('error', await rpc('config/batchWrite', params), params)
                    self.assertIn('error', await rpc('config/value/write', selection['edits'][0]))
                    c.db.update('first', lifecycle='deleting')
                    self.assertIn('error', await rpc('config/batchWrite', selection))
                    self.assertEqual(upstream.rpc.await_count, before)
                    # Neither a model picker nor a general TUI RPC may change the
                    # active saved account or export the controller's bearer token.
                    for method in ('account/login/start', 'account/login/cancel', 'account/logout',
                                   'loginApiKey', 'loginChatGpt', 'cancelLoginChatGpt', 'logout'):
                        self.assertIn('error', await rpc(method, {}))
                    self.assertEqual(upstream.rpc.await_count, before)
                    upstream.rpc.return_value = {'authToken': 'private-test-bearer', 'authMethod': 'chatgpt'}
                    response = await rpc('getAuthStatus', {'includeToken': True})
                    self.assertIsNone(response['result']['authToken'])
                    self.assertEqual(upstream.rpc.await_args.args,
                                     ('getAuthStatus', {'includeToken': False}))

    async def test_resume_confirmation_timeout_crash_and_identity(self):
        c = self.controller
        c.select('first')
        c.tui_connections['first'] = {1: time.monotonic() - 2}
        c.slash = AsyncMock()
        c.attach_ready = AsyncMock()
        result = await c.resume('first')
        operation = json.loads(c.db.get('first')['operation'])
        operation['requested_at'] = time.time() - 3600
        c.db.update('first', operation=json.dumps(operation))
        with patch('app.controller.command', AsyncMock()):
            connections = c.tui_connections.pop('first')
            await c.resume_ready()
            self.assertNotIn('error', json.loads(c.db.get('first')['operation']))
            c.slash.assert_not_awaited()
            c.tui_connections['first'] = connections
            await c.resume_ready()
            c.slash.assert_awaited_once()
            saved = json.loads(c.db.get('first')['operation'])
            self.assertIn('sent_at', saved)
            self.assertIsNone(c.db.get('first')['resume_result'])
            # Reopened durable journal must not send the slash a second time.
            c.db.conn.close()
            c.db = Database(self.root / 'test.db')
            await c.resume_ready()
            c.slash.assert_awaited_once()
            saved['sent_at'] = time.time() - 61
            c.db.update('first', operation=json.dumps(saved))
            await c.resume_ready()
            failure = json.loads(c.db.get('first')['resume_result'])
            self.assertEqual(failure['id'], result['operation_id'])
            self.assertEqual(failure['status'], 'failed')
            self.assertIn('timed out', failure['message'])
            await c.resume_ready()
            c.slash.assert_awaited_once()
        # A successful thread/read for the wrong session is not acknowledgement.
        await c.resume('first')
        c.native.rpc = AsyncMock(side_effect=[{'goal': None}, {'thread': {'id': 'other', 'cwd': str(self.root / 'first')}}])
        await c.resume_ready()
        self.assertIn('identity', json.loads(c.db.get('first')['resume_result'])['message'])

    async def test_normal_resume_does_not_preempt_but_run_now_promotes(self):
        c = self.controller
        c.select('first')
        c.db.update('first', goal_status='active')
        c.db.update('second', queue_position=None)  # Reopened project was removed on completion.
        c.pause = AsyncMock(wraps=c.pause)
        await c.resume('second')
        self.assertEqual(c.db.setting('selected'), 'first')
        self.assertEqual(c.db.get('second')['queue_position'], 2)
        self.assertEqual(json.loads(c.db.get('second')['resume_result'])['status'], 'queued')
        c.pause.assert_not_awaited()
        pending = json.loads(c.db.get('second')['operation'])
        c.db.update('second', queue_position=None)  # Repair an already persisted legacy orphan.
        self.assertEqual((await c.resume('second'))['operation_id'], pending['id'])
        self.assertEqual(c.db.get('second')['queue_position'], 2)
        self.assertEqual(json.loads(c.db.get('second')['operation']), pending)
        await c.run_now('second')
        self.assertEqual(c.db.setting('selected'), 'second')
        self.assertEqual(c.db.get('second')['queue_position'], 1)
        c.pause.assert_awaited_once()

    async def test_limit_reset_persists_but_account_limit_does_not_invent_goal(self):
        c = self.controller
        c.db.set_setting('account_usage', {'ordinaryUsageAllowed': False, 'rateLimits': {
            'primary': {'usedPercent': 100, 'resetsAt': 1800000000}}})
        c.persist_usage_resets()
        self.assertEqual(c.db.get('first')['goal_status'], 'paused')
        self.assertIsNone(c.db.get('first')['usage_limit'])
        c.record_goal(c.db.get('first'), {'status': 'usageLimited'})
        c.persist_usage_resets()
        self.assertEqual(json.loads(c.db.get('first')['usage_limit'])['resetAt'], 1800000000000)
        payload = json.loads(c.db.conn.execute('SELECT payload FROM events').fetchone()[0])
        self.assertEqual(payload['usage_limit']['resetSource'], 'native-account')
        c.db.conn.close()
        c.db = Database(self.root / 'test.db')
        self.assertEqual(json.loads(c.db.get('first')['usage_limit'])['resetAt'], 1800000000000)
        c.record_goal(c.db.get('first'), {'status': 'paused'})
        self.assertIsNone(c.db.get('first')['usage_limit'])

    async def test_account_telemetry_persists_without_resuming_or_inventing_limit(self):
        c = self.controller
        c.last_unsnooze_poll = 0
        c.native.rpc = AsyncMock(return_value={'ordinaryUsageAllowed': False, 'rateLimits': {
            'primary': {'usedPercent': 100, 'windowDurationMins': 300, 'resetsAt': 1800000000},
            'secondary': {'usedPercent': 30, 'windowDurationMins': 10080}}})
        with patch('app.controller.command', AsyncMock(return_value={'stdout': '{"sessions":[]}'})), \
                patch('app.controller.time.monotonic', return_value=5):
            await c.selective_wake()
            saved = c.db.usage_history(time.time())
            self.assertEqual(saved['daily'][0]['remaining'], 0)
            self.assertEqual(saved['weekly'][0]['remaining'], 70)
            c.native.rpc.assert_awaited_once_with('account/rateLimits/read', {}, timeout=15)
            await c.selective_wake()
            self.assertEqual(c.native.rpc.await_count, 1)  # Subsequent polling remains throttled.
            c.last_unsnooze_poll = 0
            c.native.rpc.side_effect = RuntimeError('provider temporarily unavailable')
            await c.selective_wake()
        self.assertEqual(c.db.usage_history(time.time()), saved)
        self.assertIn('account_usage', c.health_errors)
        self.assertTrue(all(p['goal_status'] == 'paused' and not p['operation'] for p in c.db.all()))
        self.assertEqual(c.db.conn.execute('SELECT count(*) FROM events').fetchone()[0], 0)

    async def test_managed_tui_launch_cannot_wait_in_update_prompt(self):
        c = self.controller
        c.pane_exists.return_value = False
        command = AsyncMock(return_value={'stdout': '', 'stderr': '', 'exit_code': 1})
        with patch('app.controller.command', command):
            await c.attach_ready(c.db.get('first'))
        launch = next(call.args[-1] for call in command.await_args_list if call.args[:2] == ('tmux', 'new-session'))
        self.assertIn('check_for_update_on_startup=false', launch)
        self.assertIn('UNSNOOZE_AUTO_RESUME=false', launch)
        self.assertIn('resume first', launch)
        mouse = ('tmux', 'set-option', '-t', c.db.get('first')['tmux_session_name'], 'mouse', 'on')
        self.assertIn(mouse, [call.args for call in command.await_args_list])
        # Reattaching an existing pane must repair scrolling without respawning its draft.
        c.pane_exists.return_value = True
        command.reset_mock()
        with patch('app.controller.command', command):
            await c.attach_ready(c.db.get('first'))
        self.assertEqual([call.args for call in command.await_args_list], [mouse])

    async def test_completion_compacts_queue_and_confirms_pending_resume(self):
        c = self.controller
        c.select('first')
        c.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'r1'}))
        c.refresh_git = AsyncMock()
        c.cancel_wakes = AsyncMock()
        with patch('app.controller.command', AsyncMock(return_value={'stdout': '', 'stderr': '', 'exit_code': 0})):
            await c.complete(c.db.get('first'))
        self.assertEqual(c.db.get('second')['queue_position'], 1)
        self.assertEqual(json.loads(c.db.get('first')['resume_result'])['status'], 'complete')
        self.assertIsNone(c.db.setting('selected'))

    async def test_ci_checks_exact_commit_all_workflows_and_latest_attempt(self):
        c = self.controller
        sha = 'a' * 40
        c.db.update('first', github_repo='owner/first')
        run = {'id': 10, 'run_attempt': 1, 'workflow_id': 1, 'event': 'push',
               'head_sha': sha, 'path': '.github/workflows/tests.yml',
               'status': 'completed', 'conclusion': 'success', 'html_url': 'https://example.invalid/run'}
        cases = [([], [], 'not configured'),
                 (['.github/workflows/tests.yml'], [], 'pending'),
                 (['.github/workflows/tests.yml'], [run], 'passed'),
                 (['.github/workflows/tests.yml', '.github/workflows/other.yml'], [run], 'pending'),
                 (['.github/workflows/tests.yml'], [{**run, 'head_sha': 'b' * 40}], 'pending'),
                 (['.github/workflows/tests.yml'], [{**run, 'conclusion': None}], 'pending'),
                 (['.github/workflows/tests.yml'], [{**run, 'path': run['path'] + '@refs/heads/main'}], 'passed'),
                 (['.github/workflows/tests.yml'], [{**run, 'conclusion': 'failure'},
                    {**run, 'run_attempt': 2}], 'passed'),
                 (['.github/workflows/tests.yml'], [run, {**run, 'id': 11, 'status': 'in_progress', 'conclusion': None}], 'pending'),
                 (['.github/workflows/tests.yml'], [{**run, 'conclusion': 'failure'},
                    {**run, 'event': 'workflow_dispatch', 'id': 12}], 'failure')]
        for workflows, runs, expected in cases:
            with self.subTest(expected=expected, runs=runs):
                async def command(*args, **kwargs):
                    if args[:2] == ('git', 'rev-parse'):
                        output = sha
                    elif args[:2] == ('git', 'ls-tree'):
                        output = '\0'.join(workflows) + ('\0' if workflows else '')
                    elif args[:2] == ('git', 'show'):
                        output = 'on: push\njobs: {}'
                    elif args[:2] == ('gh', 'api'):
                        output = json.dumps([{'workflow_runs': runs[:1]}, {'workflow_runs': runs[1:]}])
                    else:
                        output = json.dumps([{'status': r['status'], 'conclusion': r['conclusion'], 'url': r['html_url']} for r in runs])
                    return {'stdout': output, 'stderr': '', 'exit_code': 0}
                with patch('app.controller.command', command):
                    await c.refresh_git(c.db.get('first'))
                self.assertEqual(c.db.get('first')['last_ci_status'], expected)

    async def test_failed_final_ci_stalls_once_instead_of_advancing_or_spamming(self):
        c = self.controller
        c.select('first')
        c.db.update('first', goal_status='active', last_ci_status='failure')
        c.refresh_git = AsyncMock()
        with patch('app.controller.command', AsyncMock(return_value={'stdout': '', 'exit_code': 0})):
            await c.complete(c.db.get('first'))
            c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'stalled'}})
            await c.poll_goals()
            await c.poll_goals()
        project = c.db.get('first')
        self.assertEqual(project['goal_status'], 'stalled')
        self.assertIn('CI', project['block_reason'])
        self.assertEqual(project['completion_notified'], 0)
        self.assertFalse(c.db.setting('advance_queue', False))
        self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='complete'").fetchone()[0], 0)
        self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='stalled'").fetchone()[0], 1)
        c.native.rpc.assert_any_await('thread/goal/set', {'threadId': 'first', 'status': 'blocked'})

    async def test_native_completion_releases_stale_active_slot_while_ci_is_verified(self):
        c = self.controller
        c.db.update('second', goal_status='active', github_repo='owner/second', last_commit='a' * 40)
        c.db.set_setting('selected', 'first')
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'active'}, 'second': {'status': 'complete'}})
        c.refresh_git = AsyncMock(side_effect=lambda p: c.db.update(p['project_id'], last_ci_status='pending'))
        c.cancel_wakes = AsyncMock()
        command = AsyncMock(return_value={'stdout': '', 'stderr': '', 'exit_code': 0})
        with patch('app.controller.command', command):
            await c.poll_goals()
            self.assertEqual(c.db.get('second')['goal_status'], 'complete')
            self.assertEqual(c.db.get('first')['goal_status'], 'active')  # UNIQUE gate is preserved.
            self.assertEqual(c.db.setting('selected'), 'first')
            self.assertEqual(c.db.get('second')['completion_notified'], 0)
            self.assertEqual(c.db.get('second')['queue_position'], 2)
            self.assertIn('final CI', c.db.setting('completion_check/second')['message'])
            self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='complete'").fetchone()[0], 0)
            await c.poll_goals()
            c.refresh_git.assert_awaited_once()  # No push/API retry storm.
            c.db.conn.close()
            c.db = Database(self.root / 'test.db')
            stamp = c.db.setting('completion_check/second')['checked_at']
            c.refresh_git.side_effect = lambda p: c.db.update(p['project_id'], last_ci_status='passed')
            with patch('app.controller.time.time', return_value=stamp + 31):
                await c.poll_goals()
                await c.poll_goals()
            self.assertEqual(c.db.get('second')['completion_notified'], 1)
            self.assertIsNone(c.db.get('second')['queue_position'])
            self.assertEqual(c.db.setting('selected'), 'first')
            self.assertIsNone(c.db.setting('completion_check/second'))
            self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='complete'").fetchone()[0], 1)

    async def test_ci_does_not_wait_for_pr_only_workflow_on_plain_push(self):
        c, sha = self.controller, 'a' * 40
        c.db.update('first', github_repo='owner/first')
        runs = [{'id': 1, 'run_attempt': 1, 'workflow_id': 1, 'event': 'push', 'head_sha': sha,
                 'path': '.github/workflows/build.yml', 'status': 'completed', 'conclusion': 'success'}]
        workflow, pulls = {'text': 'on: pull_request\njobs: {}'}, []
        async def command(*args, **kwargs):
            if args[:2] == ('git', 'rev-parse'):
                output = sha
            elif args[:2] == ('git', 'ls-tree'):
                output = '.github/workflows/build.yml\0.github/workflows/pr.yml\0'
            elif args[:2] == ('git', 'show'):
                self.assertEqual(args[2], sha + ':.github/workflows/pr.yml')
                output = workflow['text']
            elif args[:2] == ('gh', 'api'):
                output = json.dumps([pulls]) if '/pulls?' in args[-1] else json.dumps([{'workflow_runs': runs}])
            else:
                raise AssertionError(args)
            return {'stdout': output, 'stderr': '', 'exit_code': 0}
        with patch('app.controller.command', command):
            for text in ('on: pull_request\njobs: {}', '"on": [pull_request, pull_request_target]\njobs: {}',
                         'on:\n  pull_request:\n    branches: [main]\njobs: {}'):
                workflow['text'] = text
                await c.refresh_git(c.db.get('first'))
                self.assertEqual(c.db.get('first')['last_ci_status'], 'passed')
            pulls.append({'state': 'open', 'head': {'sha': sha}})
            await c.refresh_git(c.db.get('first'))
            self.assertEqual(c.db.get('first')['last_ci_status'], 'pending')
            pulls.clear()
            for text in ('on: [push, pull_request]\njobs: {}', 'on: workflow_dispatch\njobs: {}',
                         'on: [', 'jobs: {}'):
                workflow['text'] = text
                await c.refresh_git(c.db.get('first'))
                self.assertEqual(c.db.get('first')['last_ci_status'], 'pending')

    async def test_promotion_preserves_inactive_limit_and_user_blockers(self):
        c = self.controller
        for native, stored in (('usageLimited', 'usage limited'), ('blocked', 'stalled')):
            with self.subTest(native=native):
                self.native_status = native
                c.select('first')
                c.db.update('first', goal_status=stored, block_reason=json.dumps({'requires_user': True}))
                c.db.update('second', operation=None)
                c.native.rpc.reset_mock()
                await c.resume('second', promote=True)
                self.assertEqual(c.db.get('first')['goal_status'], stored)
                self.assertFalse(any(call.args[0] == 'thread/goal/set' for call in c.native.rpc.await_args_list))

    async def test_auto_queue_does_not_resume_paused_user_decision(self):
        c = self.controller
        c.db.set_setting('advance_queue', True)
        c.db.update('first', goal_status='paused', block_reason=json.dumps({'requires_user': True}))
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'paused'}})
        c.native.ws = SimpleNamespace(closed=False)
        c.last_backup = c.last_git_poll = time.monotonic()
        c.poll_goals = AsyncMock()
        c.resume_ready = AsyncMock()
        c.selective_wake = AsyncMock()
        c.release_idle_tuis = AsyncMock()
        c.attach_ready = AsyncMock()
        c.bot = None
        with patch('app.controller.asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await c.scheduler()
        self.assertIsNone(c.db.setting('selected'))
        self.assertIsNone(c.db.get('first')['operation'])
        c.attach_ready.assert_not_awaited()

    async def test_manual_pause_survives_restart_and_cancels_stale_resume(self):
        c = self.controller
        c.select('first')
        self.native_status = 'active'
        c.db.update('first', goal_status='active')
        await c.pause(c.db.get('first'), manual=True)
        self.assertTrue(c.db.setting('manual_pause/first'))
        db_path = c.db.path
        c.db.conn.close()
        c.db = Database(db_path)
        c.select('first')
        c.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'stale', 'source': 'recovery', 'requested_at': time.time()}))
        c.attach_ready = AsyncMock()
        c.slash = AsyncMock()
        # Crash after persisting Pause but before the native status changed.
        c.db.update('first', goal_status='active')
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'active'}})
        await c.recover()
        await c.resume_ready()
        self.assertEqual(json.loads(c.db.get('first')['resume_result'])['status'], 'cancelled')
        c.attach_ready.assert_not_awaited()
        c.slash.assert_not_awaited()
        self.native_status = 'paused'
        await c.resume('first')
        self.assertFalse(c.db.setting('manual_pause/first'))

    async def test_windows_reconnect_respects_manual_pause_and_journals_one_resume(self):
        from app.worker_server import unblock_windows
        c = self.controller
        c.attach_ready = AsyncMock()
        c.db.update('first', goal_status='stalled', windows_required=1,
                    block_reason=json.dumps({'reason': 'Windows offline', 'requires_user': False}))
        c.db.set_setting('manual_pause/first', True)
        await unblock_windows(c)
        c.attach_ready.assert_not_awaited()
        c.db.set_setting('manual_pause/first', False)
        await unblock_windows(c)
        operation = json.loads(c.db.get('first')['operation'])
        self.assertTrue(operation.get('id'))
        self.assertEqual(operation.get('source'), 'windows')
        await unblock_windows(c)
        self.assertEqual(json.loads(c.db.get('first')['operation']), operation)
        c.attach_ready.assert_not_awaited()  # The shared journal consumer owns TUI restoration.

    async def test_legacy_paused_projects_need_explicit_intent_not_a_guess(self):
        c = self.controller
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'paused'}, 'second': {'status': 'paused'}})
        c.db.update('second', operation=json.dumps({'kind': 'resume', 'id': 'explicit-pending', 'requested_at': time.time()}))
        await c.recover()
        self.assertTrue(c.db.setting('manual_pause/first'))
        self.assertFalse(c.db.setting('manual_pause/second', False))
        self.assertTrue(c.db.setting('manual_pause_policy_initialized'))

    async def test_resume_waits_for_its_own_pane_not_an_older_browser_connection(self):
        c = self.controller
        del c.mapped_tui_ready
        c.attach_ready = AsyncMock()
        c.slash = AsyncMock()
        await c.resume('first')
        c.tui_connections['first'] = {1: time.monotonic() - 100, 2: time.monotonic()}
        c.tui_peer_pids = {1: 111, 2: 123}
        command = AsyncMock(return_value={'exit_code': 0, 'stdout': '123\n'})
        with patch('app.controller.command', command), patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            await c.resume_ready()
            c.slash.assert_not_awaited()
            self.assertNotIn('sent_at', json.loads(c.db.get('first')['operation']))
            c.tui_connections['first'][2] = time.monotonic() - 2
            await c.resume_ready()
            c.slash.assert_awaited_once()
            self.assertEqual(c.slash.await_args.args[0]['project_id'], 'first')
            self.assertEqual(c.slash.await_args.args[1], '/goal resume')
            await c.resume_ready()
            c.slash.assert_awaited_once()
            # A respawned pane cannot reuse the previous process's connection.
            command.return_value['stdout'] = '124\n'
            self.assertFalse(await c.mapped_tui_ready(c.db.get('first')))

    async def test_resume_repairs_only_detached_idle_unmapped_pane_once(self):
        c = self.controller
        c.select('first')
        c.attach_ready = AsyncMock()
        c.slash = AsyncMock()
        await c.resume('first')
        operation = json.loads(c.db.get('first')['operation'])
        operation['started_at'] = time.time() - 15
        c.db.update('first', operation=json.dumps(operation))

        async def command(*args, **kwargs):
            if 'capture-pane' in args:
                return {'exit_code': 0, 'stdout': 'Preserve the disconnected pane', 'stderr': ''}
            return {'exit_code': 0, 'stdout': '0 123\n', 'stderr': ''}

        with patch('app.controller.command', AsyncMock(side_effect=command)) as calls:
            self.thread_status = 'active'
            await c.resume_ready()
            self.assertFalse(any('if-shell' in call.args for call in calls.await_args_list))
            self.thread_status = 'idle'
            with patch('app.controller.command', AsyncMock(return_value={'exit_code': 0, 'stdout': '1\n'})):
                await c.resume_ready()  # An attached terminal is never replaced.
            self.assertFalse(any('if-shell' in call.args for call in calls.await_args_list))
            c.tui_peer_pids[7] = 123
            with patch('app.controller.process_in_pane', return_value=True):
                await c.resume_ready()  # A connected picker/draft is not a ghost pane.
            self.assertFalse(any('if-shell' in call.args for call in calls.await_args_list))
            c.tui_peer_pids.clear()
            await c.resume_ready()
            self.assertEqual(sum('if-shell' in call.args for call in calls.await_args_list), 1)
            recovered = json.loads(c.db.get('first')['operation'])
            self.assertIn('tui_reopened_at', recovered)
            self.assertNotIn('sent_at', recovered)
            archive = c.root / 'state/tui-recovery' / (operation['id'] + '.txt')
            self.assertEqual(archive.read_text(), 'Preserve the disconnected pane')
            await c.resume_ready()
            self.assertEqual(sum('if-shell' in call.args for call in calls.await_args_list), 1)
            c.tui_connections['first'] = {1: time.monotonic() - 2}
            await c.resume_ready()
            await c.resume_ready()
            c.slash.assert_awaited_once()
            self.assertEqual(c.slash.await_args.args[1], '/goal resume')

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
        self.assertIsNotNone(controller.db.get('first')['operation'])
        self.native_status, self.thread_status = 'active', 'active'
        controller.tui_connections['first'] = {1: time.monotonic() - 2}
        await controller.resume_ready()
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
        # The former goal may already have been cleared/paused before the new one.
        controller.db.update('second', goal_status='paused', completion_notified=1, queue_position=None)
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
                    self.assertEqual(controller.db.get('second')['queue_position'], 2)
                    self.assertEqual(controller.db.get('second')['completion_notified'], 0)
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
                    controller.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'cancel-me'}))
                    await socket.send_json({'id': 13, 'method': 'thread/goal/set', 'params': {
                        'threadId': 'first', 'status': 'paused'}})
                    self.assertIn('result', await socket.receive_json())
                    self.assertTrue(controller.db.setting('manual_pause/first'))
                    self.assertEqual(json.loads(controller.db.get('first')['resume_result'])['status'], 'cancelled')
                    controller.select('first')  # Even a stale selection must not bypass a manual pause.
                    await socket.send_json({'id': 14, 'method': 'turn/start', 'params': {'threadId': 'first'}})
                    self.assertIn('error', await socket.receive_json())
                    await socket.send_json({'id': 15, 'method': 'thread/goal/set', 'params': {
                        'threadId': 'first', 'status': 'active'}})
                    self.assertIn('result', await socket.receive_json())
                    self.assertFalse(controller.db.setting('manual_pause/first'))

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
        self.native_status = 'usageLimited'
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
                controller.db.update('first', usage_limit=None)
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
            restored = json.loads(controller.db.get('first')['operation'])
            self.assertGreater(restored.pop('started_at'), 0)
            self.assertEqual(restored, json.loads(operation))
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
            self.native_status, self.thread_status = 'active', 'active'
            await controller.resume_ready()
            self.assertIsNone(controller.db.get('first')['operation'])
        self.assertFalse(any('resume-now' in args for args in calls))
        self.assertFalse(any(args[:2] == ('unsnooze', 'cancel') and args[-1] != 'first-stop' for args in calls))

    async def test_unsnooze_idle_poll_avoids_restarting_node_every_ten_seconds(self):
        controller = self.controller
        controller.health_errors = {}
        controller.last_unsnooze_poll = time.monotonic() - 11
        controller.select('first')
        status = AsyncMock(return_value={'stdout': '{"sessions":[]}'})
        with patch('app.controller.command', status):
            await controller.selective_wake()
            status.assert_not_awaited()
            controller.db.update('first', goal_status='usage limited')
            await controller.selective_wake()
            status.assert_awaited_once_with('unsnooze', 'status', '--json')
            controller.db.update('first', goal_status='paused')
            controller.last_unsnooze_poll = time.monotonic() - 61
            await controller.selective_wake()
            self.assertEqual(status.await_count, 2)

    async def test_native_reset_wakes_without_unsnooze_record_once_per_reset(self):
        c = self.controller
        c.select('first')
        self.native_status = 'usageLimited'
        reset = (time.time() - 60) * 1000
        c.db.update('first', goal_status='usage limited', usage_limit=json.dumps({
            'resetAt': reset, 'resetSource': 'native-account'}))
        c.slash = AsyncMock()
        c.tui_connections['first'] = {1: time.monotonic() - 2}
        # The real overnight case: empty premium sample left no detector record.
        # Its authoritative account reset survives a controller restart/refill.
        c.db.conn.close()
        c.db = Database(self.root / 'test.db')
        with patch('app.controller.command', AsyncMock(return_value={'stdout': '{"sessions":[]}'})):
            for held in (True, False):
                c.db.set_setting('manual_pause/first', held)
                c.last_unsnooze_poll = 0
                await c.selective_wake()
                self.assertEqual(bool(c.db.get('first')['operation']), not held)
            await c.resume_ready()
            await c.resume_ready()  # An unchanged old limit is not a resume acknowledgement.
            self.assertIsNotNone(c.db.get('first')['operation'])
            self.goal_updated_at += 1  # Native acknowledgement/real new provider limit.
            await c.resume_ready()
            c.last_unsnooze_poll = 0
            await c.selective_wake()
            c.slash.assert_awaited_once()
            self.assertIsNone(c.db.get('first')['operation'])
            self.assertEqual(c.db.setting('usage_wake/first')['reset_at'], reset)
            c.db.update('first', usage_limit=json.dumps({'resetAt': reset + 1000, 'resetSource': 'native-account'}))
            c.last_unsnooze_poll = 0
            await c.selective_wake()
            await c.resume_ready()
            self.assertEqual(c.slash.await_count, 2)
            self.assertEqual(c.slash.await_args.args[1], '/goal resume')

    async def test_usage_reset_reconciles_reordered_head_without_preempting_or_losing_wake(self):
        c = self.controller
        c.select('second')
        c.db.reorder(['first', 'second'])  # Running selection is now the old head, at position 2.
        self.native_status = 'usageLimited'
        reset = (time.time() - 60) * 1000
        for ident in ('first', 'second'):
            c.db.update(ident, goal_status='usage limited', usage_limit=json.dumps({
                'resetAt': reset, 'resetSource': 'native-account'}))
        c.slash = AsyncMock()
        c.attach_ready = AsyncMock()
        c.tui_connections['first'] = {1: time.monotonic() - 2}
        async def poll():
            c.last_unsnooze_poll = 0
            await c.selective_wake()
        with patch('app.controller.command', AsyncMock(return_value={'stdout': '{"sessions":[]}'})):
            # Neither current work, manual intent nor ambiguous Windows work can be preempted.
            for status in ('active', 'paused', 'stalled'):
                c.db.update('second', goal_status=status)
                await poll()
                self.assertEqual(c.db.setting('selected'), 'second')
                self.assertIsNone(c.db.get('first')['operation'])
            c.db.update('second', goal_status='usage limited')
            c.db.set_setting('manual_pause/first', True)
            await poll()
            self.assertEqual(c.db.setting('selected'), 'second')
            c.db.set_setting('manual_pause/first', False)
            self.thread_status = 'active'
            await poll()
            self.assertEqual(c.db.setting('selected'), 'second')
            self.thread_status = 'idle'
            c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                              ('ambiguous', 'second', '{}', 'sent', 1, 1))
            await poll()
            self.assertEqual(c.db.setting('selected'), 'second')
            c.db.conn.execute('DELETE FROM jobs')
            await poll()
            self.assertEqual(c.db.setting('selected'), 'first')
            self.assertEqual(c.db.get('first')['queue_position'], 1)
            c.db.reorder(['second', 'first'])
            await c.resume_ready()  # Cancel before delivery while temporarily moved away.
            c.slash.assert_not_awaited()
            self.assertIsNone(c.db.setting('usage_wake/first'))
            c.db.reorder(['first', 'second'])
            await poll()
            await c.resume_ready()
            self.goal_updated_at += 1
            await c.resume_ready()
            await poll()
            c.slash.assert_awaited_once()
            self.assertEqual(c.slash.await_args.args[1], '/goal resume')
            self.assertEqual(c.db.setting('usage_wake/first')['reset_at'], reset)
            self.assertIsNone(c.db.get('second')['operation'])

    async def test_auto_continue_releases_a_confirmed_blocker_after_failed_resume(self):
        c = self.controller
        c.source = SimpleNamespace(rows=lambda: {p['codex_session_id']: {} for p in c.db.all()})
        c.attach_ready = AsyncMock()
        c.select('first')
        c.db.set_setting('auto_continue', True)
        operation = {'kind': 'resume', 'id': 'failed-resume', 'sent_at': time.time() - 120,
                     'error': 'Resume timed out'}
        c.db.update('first', goal_status='stalled', windows_required=1,
                    block_reason='{"reason":"Windows offline","requires_user":false}',
                    operation=json.dumps(operation))
        self.native_status = 'blocked'
        # An error journal is not proof of idleness or permission to run another goal.
        for native, thread in (('active', 'active'), ('usageLimited', 'idle'), ('blocked', 'active')):
            self.native_status, self.thread_status = native, thread
            await c.advance_queue()
            self.assertEqual(c.db.setting('selected'), 'first')
            self.assertEqual(json.loads(c.db.get('first')['operation']), operation)
        self.native_status, self.thread_status = 'blocked', 'idle'
        c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                          ('job', 'first', '{}', 'sent', 1, 1))
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'first')
        c.db.conn.execute("UPDATE jobs SET status='finished'")
        c.db.set_setting('manual_pause/second', True)
        await c.advance_queue()
        self.assertIsNone(c.db.setting('selected'))
        first = c.db.get('first')
        self.assertIsNone(first['operation'])
        self.assertEqual(first['goal_status'], 'stalled')
        self.assertEqual(json.loads(first['resume_result']), {
            'id': 'failed-resume', 'status': 'failed', 'message': 'Resume timed out'})
        c.db.set_setting('manual_pause/second', False)
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'second')
        self.assertEqual(json.loads(c.db.get('second')['operation'])['source'], 'auto-continue')
        c.native.rpc.assert_any_await('thread/read', {'threadId': 'first', 'includeTurns': False})

    async def test_auto_continue_skips_blockers_but_never_usage_limits_or_manual_holds(self):
        c = self.controller
        c.source = SimpleNamespace(rows=lambda: {p['codex_session_id']: {} for p in c.db.all()})
        c.attach_ready = AsyncMock()
        c.select('first')
        c.db.update('first', goal_status='stalled', block_reason='{"requires_user":true,"reason":"Windows needed"}')
        self.native_status = 'blocked'
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'first')  # Opt in only.
        c.db.set_setting('auto_continue', True)
        c.db.set_setting('pause_all', True)
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'first')
        c.db.set_setting('pause_all', False)
        c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                          ('job', 'first', '{}', 'running', 1, 1))
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'first')
        c.db.conn.execute("UPDATE jobs SET status='finished'")
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'second')
        self.assertEqual(c.db.get('first')['goal_status'], 'stalled')
        c.wait_idle.assert_awaited_once()
        self.assertEqual(json.loads(c.db.get('second')['operation'])['source'], 'auto-continue')
        # Turning the switch off also cancels a not-yet-submitted handoff.
        c.db.set_setting('auto_continue', False)
        await c.resume_ready()
        self.assertIsNone(c.db.get('second')['operation'])
        c.db.set_setting('auto_continue', True)
        c.db.update('second', goal_status='usage limited')
        self.native_status = 'usageLimited'
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'second')
        # A third eligible project can run after the second becomes blocked.
        c.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,codex_session_id,
            tmux_session_name,created_at,updated_at,queue_position,lifecycle) VALUES(?,?,?,?,?,?,?,?,?,?)''',
            ('third', 'third', 'third', str(self.root / 'third'), 'third', 'third', 1, 1, 3, 'ready'))
        c.db.set_setting('manual_pause/third', True)
        c.db.update('second', goal_status='stalled')
        self.native_status = 'blocked'
        await c.advance_queue()
        self.assertIsNone(c.db.setting('selected'))
        c.db.set_setting('manual_pause/third', False)
        await c.advance_queue()
        self.assertEqual(c.db.setting('selected'), 'third')
        self.assertEqual(c.db.get('third')['queue_position'], 1)


if __name__ == '__main__':
    unittest.main()
