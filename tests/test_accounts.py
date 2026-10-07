import base64
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.accounts import AccountVault, auth_identity, choose_account, observe_account, refresh, request_switch, switching, tick
from app.common import atomic_write
from app.db import Database
from tests.test_usage import account


def login(user, token=None):
    claims = base64.urlsafe_b64encode(json.dumps({'sub': user, 'email': user + '@example.test'}).encode()).decode().rstrip('=')
    return json.dumps({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                      'tokens': {'id_token': 'header.' + claims + '.signature', 'access_token': token or 'test-access-' + user,
                                 'refresh_token': 'test-refresh-token', 'account_id': 'workspace'}})


class AccountTests(unittest.TestCase):
    def test_account_choice_respects_both_windows_real_observations_and_bounded_probes(self):
        now = 1800000
        accounts = [{'account_id': key, 'status': 'ready'} for key in ('a', 'b')]
        def sample(key, daily, weekly, reset, stamp=now):
            return {**account(stamp, daily, weekly, reset), 'account_id': key}

        samples = {'a': sample('a', 50, 100, now + 60),
                   'b': sample('b', 50, 50, now + 300)}
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'b')
        samples['a'] = sample('a', 50, 80, now + 60)
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'a')
        samples['b'] = sample('b', 50, 20, now + 90)
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'b')  # Near reset: more weekly.
        samples['b'] = sample('b', 50, 50, now + 300, stamp=now + 61)
        self.assertEqual(choose_account(accounts, samples, now + 61)['account_id'], 'b')  # A crossed reset; no assumed refill.
        samples['a'] = sample('a', 0, 0, now + 60, stamp=now - 3600)
        samples['b'] = sample('b', 50, 50, now + 300)
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'b')  # Fresh before stale.
        samples['a'] = sample('a', 100, 80, now + 60)
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'b')
        samples['b'] = sample('b', 100, 20, now + 300)
        decision = choose_account(accounts, samples, now, attempted=['a', 'b'])
        self.assertEqual((decision['account_id'], decision['mode'], decision['reset_at']), ('a', 'wait', now + 60))
        samples['a'] = sample('a', 100, 100, now + 60)
        self.assertEqual(choose_account(accounts, samples, now)['account_id'], 'b')  # Never wait on A's 5h alone.
        accounts[1]['status'] = 'needs_login'
        decision = choose_account(accounts, samples, now)
        self.assertEqual((decision['mode'], decision['reset_at']), ('wait', now + 60 + 86400))
        accounts[1]['status'] = 'ready'
        later = now + 60 + 86401
        decision = choose_account(accounts, samples, later)
        self.assertEqual(decision['mode'], 'verify')  # Time passed: check, never assert 100%.
        self.assertIsNone(choose_account(accounts, samples, later, attempted=['a', 'b']))
        samples['a'] = sample('a', 0, 0, now + 60, stamp=now - 3600)
        decision = choose_account(accounts[:1], samples, now)
        self.assertEqual(decision['mode'], 'verify')  # Stale positive values are not usable proof.
        samples['a']['account_id'] = 'b'
        self.assertEqual(choose_account(accounts[:1], samples, now)['mode'], 'verify')
        self.assertIsNone(choose_account(accounts[:1], samples, now, attempted=['a']))

    def test_private_slots_refresh_identity_and_do_not_copy_sessions_or_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / 'codex-home'
            atomic_write(codex_home / 'config.toml', 'unrelated = true\n')
            atomic_write(codex_home / 'sessions/history.jsonl', 'preserve native history\n')
            first, second = login('first'), login('second')
            atomic_write(codex_home / 'auth.json', first)
            vault = AccountVault(root, codex_home)
            proof = {'authMethod': 'chatgpt', 'authToken': 'test-access-first', 'accountId': 'workspace'}
            one = vault.checkpoint({'type': 'chatgpt', 'email': 'first@example.test', 'planType': 'plus'}, proof)
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                vault.checkpoint({'type': 'chatgpt'}, proof, expected_id='0' * 64)
            atomic_write(codex_home / 'auth.json', second)
            two = vault.checkpoint({'type': 'chatgpt', 'email': 'second@example.test'},
                                   {**proof, 'authToken': 'test-access-second'})
            self.assertNotEqual(one['account_id'], two['account_id'])
            vault.install(one['account_id'])
            self.assertEqual((codex_home / 'auth.json').read_text(), first)
            refreshed = login('first', 'new-test-access-token')
            atomic_write(codex_home / 'auth.json', refreshed)
            vault.checkpoint({'type': 'chatgpt'}, {**proof, 'authToken': 'new-test-access-token'}, expected_id=one['account_id'])
            self.assertEqual(vault.path(one['account_id']).read_text(), refreshed)
            self.assertNotIn('token', json.dumps(one))
            self.assertEqual((codex_home / 'config.toml').read_text(), 'unrelated = true\n')
            self.assertEqual((codex_home / 'sessions/history.jsonl').read_text(), 'preserve native history\n')
            for bad in ('../auth', '', None, 'a' * 65):
                with self.assertRaises(ValueError):
                    vault.path(bad)
            for bad in (b'not-json', b'{}', b'[]', b'{"tokens": []}', b'{"tokens": null}'):
                with self.assertRaisesRegex(ValueError, 'sign in again'):
                    auth_identity(bad)
            atomic_write(vault.path(one['account_id']), second)
            with self.assertRaisesRegex(ValueError, 'does not match'):
                vault.install(one['account_id'])
            self.assertEqual((codex_home / 'auth.json').read_text(), refreshed)
            atomic_write(vault.path(one['account_id']), refreshed)
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(vault.directory.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(vault.path(one['account_id']).stat().st_mode), 0o600)
                two_path = vault.path(two['account_id'])
                two_path.unlink()
                two_path.symlink_to(codex_home / 'auth.json')
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    vault.install(two['account_id'])
                two_path.unlink()
            vault.remove(two['account_id'])
            self.assertTrue(vault.path(one['account_id']).exists())
            self.assertEqual(auth_identity((codex_home / 'auth.json').read_bytes())[0], one['account_id'])

    def test_usage_is_account_scoped_persistent_and_removal_keeps_other_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'database.db'
            db = Database(path)
            try:
                db.record_usage(account(1800000, daily=25))
                legacy = db.usage_history(1800000)
                db.bind_legacy_usage('first')
                db.activate_account('first')
                self.assertEqual(db.usage_history(1800000), legacy)
                db.record_usage(account(1800060, daily=30))
                first = db.usage_history(1800060)
                db.record_usage(account(1800060, daily=90), 'second')
                self.assertEqual(db.usage_history(1800060), first)
                self.assertEqual(db.setting('account_usage')['rateLimits']['primary']['usedPercent'], 30)
                db.activate_account('second')
                self.assertEqual(db.usage_history(1800060)['daily'][-1]['remaining'], 10)
                db.activate_account('unknown')
                self.assertIsNone(db.setting('account_usage')['checked_at'])
                self.assertEqual(db.usage_history(1800060)['daily'], [])
                db.activate_account('first')
                db.delete_account_usage('second')
                self.assertEqual(db.usage_history(1800060), first)
                self.assertEqual(db.usage_history(1800060, 'second')['daily'], [])
                with self.assertRaises(ValueError):
                    db.delete_account_usage('first')
                with self.assertRaises(ValueError):
                    db.bind_legacy_usage('second')
            finally:
                db.conn.close()
            db = Database(path)
            try:
                self.assertEqual(db.setting('active_account'), 'first')
                self.assertEqual(db.usage_history(1800060), first)
            finally:
                db.conn.close()


class AccountObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_loaded_identity_and_fresh_limits_are_required_without_exporting_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'codex-home'
            first, second = login('first'), login('second')
            atomic_write(home / 'auth.json', first)
            vault = AccountVault(root, home)
            ident = auth_identity(first)[0]
            fresh = {**account(1800000), 'accountId': 'workspace'}
            def rpc(native_token, provider_id='workspace'):
                return SimpleNamespace(rpc=AsyncMock(side_effect=[{'account': {'type': 'chatgpt'}},
                    {**fresh, 'accountId': provider_id}, {'authMethod': 'chatgpt', 'authToken': native_token}]))

            metadata, usage = await observe_account(rpc('test-access-first'), vault, ident)
            self.assertEqual(metadata['account_id'], ident)
            self.assertEqual(usage['account_id'], ident)
            self.assertGreater(usage['checked_at'], 1800000)
            exported = json.dumps((metadata, usage))
            self.assertNotIn('test-access', exported)
            self.assertNotIn('refresh_token', exported)
            before = vault.path(ident).read_bytes()
            for native_token, provider in [('test-access-second', 'workspace'), ('test-access-first', 'other'),
                                          (None, 'workspace'), ('test-access-first', None)]:
                with self.assertRaisesRegex(ValueError, 'do not match'):
                    await observe_account(rpc(native_token, provider), vault, ident)
                self.assertEqual(vault.path(ident).read_bytes(), before)
            # Two principals can share the same workspace and have no public email.
            # Installing B while the server still uses A must not attribute A's quota to B.
            atomic_write(home / 'auth.json', second)
            with self.assertRaisesRegex(ValueError, 'do not match'):
                await observe_account(rpc('test-access-first'), vault)
            self.assertFalse(vault.path(auth_identity(second)[0]).exists())
            self.assertEqual(vault.path(ident).read_bytes(), before)


class AccountSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_waits_for_turn_and_jobs_recovers_journal_and_respects_manual_pause(self):
        # Reuse the scheduler's existing two-project fixture, not a parallel harness.
        from tests.test_scheduler import SchedulerTests
        fixture = SchedulerTests()
        fixture.setUp()
        c, home = fixture.controller, fixture.root / 'codex-home'
        c.account_vault = AccountVault(c.root, home)
        logins = [login('first'), login('second')]
        ids = [auth_identity(raw)[0] for raw in logins]
        loaded = {'raw': logins[0], 'status': 'active', 'goal': 'active'}
        goal = {'objective': 'Preserve this exact goal', 'createdAt': 17, 'updatedAt': 20}
        async def rpc(method, params, **kwargs):
            if method == 'account/read':
                return {'account': {'type': 'chatgpt'}}
            if method == 'account/rateLimits/read':
                return {**account(1800000), 'accountId': 'workspace', 'ordinaryUsageAllowed': True}
            if method == 'getAuthStatus':
                return {'authMethod': 'chatgpt', 'authToken': json.loads(loaded['raw'])['tokens']['access_token']}
            if method == 'thread/goal/get':
                return {'goal': {**goal, 'status': loaded['goal']}}
            if method == 'thread/goal/set':
                self.assertTrue(switching(c))  # Journal predates continuation pause.
                loaded['goal'] = params['status']
                return {'goal': {**goal, 'status': loaded['goal']}}
            if method == 'thread/loaded/list':
                return {'data': ['first']}
            if method == 'thread/read':
                return {'thread': {'id': params['threadId'], 'cwd': str(c.root / params['threadId']),
                                   'status': {'type': loaded['status']}}}
            raise AssertionError('Unexpected execution RPC: ' + method)
        async def reload_runtime(controller, state):
            loaded['raw'] = c.account_vault.auth_path.read_text()
        c.native.rpc = AsyncMock(side_effect=rpc)
        c.cancel_wakes = AsyncMock()
        c.source = SimpleNamespace(rows=lambda: {'first': {'status': 'paused'}})
        try:
            for raw in reversed(logins):
                atomic_write(home / 'auth.json', raw)
                loaded['raw'] = raw
                # Initially confirm/save both without pretending they are simultaneously active.
                metadata, usage = await observe_account(c.native, c.account_vault)
                from app.accounts import remember
                remember(c, metadata, usage)
            c.db.activate_account(ids[0])
            c.select('first')
            c.db.update('first', goal_status='active')
            mapping = [(p['project_id'], p['codex_session_id'], p['project_path'], p['queue_position']) for p in c.db.all()]
            result = await request_switch(c, ids[1])
            with self.assertRaisesRegex(ValueError, 'already pending'):
                await request_switch(c, ids[1])
            await tick(c)
            self.assertEqual(loaded['goal'], 'paused')
            self.assertEqual(loaded['status'], 'active')  # Running turn was NOT interrupted.
            self.assertEqual(c.db.setting('account_switch')['phase'], 'waiting_turn')
            await c.poll_goals()
            self.assertFalse(c.db.setting('manual_pause/first', False))
            self.assertEqual(c.db.setting('selected'), 'first')
            from app.worker_server import job_denial
            self.assertIsNone(await job_denial(c, c.db.get('first')))  # Current turn's tools may finish.
            with self.assertRaisesRegex(ValueError, 'pending Codex account'):
                await c.resume('second')
            await c.advance_queue()
            await c.resume_ready()
            self.assertEqual(c.db.setting('selected'), 'first')
            loaded['status'] = 'idle'
            self.assertIn('no executing native turn', await job_denial(c, c.db.get('first')))
            c.db.conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                ('windows-job', 'first', '{}', 'running', None, 1, 1))
            await tick(c)
            self.assertEqual(c.db.setting('account_switch')['phase'], 'waiting_turn')
            c.db.conn.execute("UPDATE jobs SET status='finished'")
            await tick(c)
            await tick(c)
            self.assertEqual(c.db.setting('account_switch')['phase'], 'installing')
            self.assertIn('account change', await job_denial(c, c.db.get('first')))
            before_old_slot = c.account_vault.path(ids[0]).read_bytes()
            # Recover the exact journal, including a crash AFTER auth.json installation.
            c.account_vault.install(ids[1])
            c.db.conn.close()
            c.db = Database(c.root / 'test.db')
            with patch('app.accounts.reload_native', AsyncMock(side_effect=reload_runtime)) as reload_mock:
                for _ in range(4):
                    await tick(c)
                reload_mock.assert_awaited_once()
            self.assertFalse(switching(c))
            self.assertEqual(c.db.setting('active_account'), ids[1])
            self.assertEqual(c.account_vault.path(ids[0]).read_bytes(), before_old_slot)
            operation = json.loads(c.db.get('first')['operation'])
            self.assertEqual((operation['source'], operation['id']), ('account-switch', result['operation_id']))
            self.assertNotIn('sent_at', operation)  # HTTP/account confirmation isn't goal confirmation.
            self.assertEqual(mapping, [(p['project_id'], p['codex_session_id'], p['project_path'], p['queue_position']) for p in c.db.all()])
            # A user pause during another switch revokes the continuation, not the account change.
            c.db.update('first', operation=None, goal_status='active')
            loaded['goal'] = 'active'
            await request_switch(c, ids[0])
            c.db.set_setting('manual_pause/first', True)
            with patch('app.accounts.reload_native', AsyncMock(side_effect=reload_runtime)):
                for _ in range(6):
                    await tick(c)
            self.assertFalse(switching(c))
            self.assertTrue(c.db.setting('manual_pause/first'))
            self.assertIsNone(c.db.get('first')['operation'])
            self.assertFalse(any(call.args[0] in ('turn/start', 'turn/interrupt') for call in c.native.rpc.await_args_list))
            with self.assertRaisesRegex(ValueError, 'genuine native'):
                await request_switch(c, ids[1], automatic=True)
            self.assertFalse(switching(c))
        finally:
            fixture.tearDown()

    async def test_account_reload_keeps_frontend_connection_and_replays_only_subscriptions(self):
        import asyncio
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from app.native import Native, tui_proxy
        from tests.test_scheduler import SchedulerTests
        fixture = SchedulerTests()
        fixture.setUp()
        c = fixture.controller
        callback = []
        restored = asyncio.Event()
        old = SimpleNamespace(rpc=AsyncMock(return_value={}), close=AsyncMock(),
                              ws=SimpleNamespace(send_json=AsyncMock()))
        async def new_rpc(method, params, **kwargs):
            if method == 'thread/resume':
                restored.set()
            return {'source': 'new-native-runtime'}
        new = SimpleNamespace(rpc=AsyncMock(side_effect=new_rpc), close=AsyncMock(),
                              ws=SimpleNamespace(send_json=AsyncMock()))
        runtimes = iter((old, new))
        async def connect(native, initialize=True):
            callback.append(native.disconnected)
            return next(runtimes)
        app = web.Application()
        app['controller'], app['sockets'] = c, set()
        app.router.add_get('/', tui_proxy)
        try:
            with patch.object(Native, 'connect', connect):
                async with TestClient(TestServer(app)) as client:
                    async with client.ws_connect('/') as socket:
                        async def rpc(method, params):
                            await socket.send_json({'id': 1, 'method': method, 'params': params})
                            return await socket.receive_json()
                        await rpc('initialize', {'clientInfo': {'name': 'test', 'version': '1'}})
                        await rpc('thread/resume', {'threadId': 'first'})
                        before = old.rpc.await_count
                        c.db.set_setting('account_switch', {'phase': 'reloading'})
                        await callback[0]()
                        await asyncio.wait_for(restored.wait(), 2)
                        response = await rpc('thread/read', {'threadId': 'first'})
                        self.assertEqual(response['result']['source'], 'new-native-runtime')
                        self.assertFalse(socket.closed)
                        self.assertEqual(old.rpc.await_count, before)
                        old.close.assert_awaited_once()
                        self.assertEqual([call.args[0] for call in new.rpc.await_args_list],
                                         ['initialize', 'thread/resume', 'thread/read'])
                        self.assertTrue(c.tui_connections['first'])
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
