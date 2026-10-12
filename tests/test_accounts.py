import asyncio
import base64
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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
            with patch('app.accounts.atomic_write') as write:
                vault.checkpoint({'type': 'chatgpt'}, proof, expected_id=one['account_id'])
                write.assert_not_called()
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
    async def test_slow_usage_commit_keeps_loop_responsive_and_finishes_before_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / 'test.db')
            started, release = threading.Event(), threading.Event()
            original = Database.record_usage
            caller_thread = threading.get_ident()

            def slow_write(writer, sample, account_id):
                self.assertNotEqual(threading.get_ident(), caller_thread)
                self.assertEqual(writer.conn.execute('PRAGMA synchronous').fetchone()[0], 2)
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release the durable writer')
                original(writer, sample, account_id)

            task = None
            try:
                with patch.object(Database, 'record_usage', slow_write):
                    task = asyncio.create_task(db.record_usage_async(account(1800000, daily=25), 'first'))
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    self.assertIsNone(db.setting('account_usage/first'))
                    task.cancel()
                    await asyncio.sleep(0.01)
                    self.assertFalse(task.done())
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertEqual(db.setting('account_usage/first')['account_id'], 'first')
                    with db.transaction():
                        with self.assertRaisesRegex(RuntimeError, 'outside an existing transaction'):
                            await db.record_usage_async(account(1800060), 'first')
            finally:
                release.set()
                if task is not None and not task.done():
                    await asyncio.gather(task, return_exceptions=True)
                db.conn.close()

    async def test_inactive_live_usage_is_isolated_bounded_and_failure_keeps_history(self):
        from app.accounts import refresh_saved_accounts
        from app.native import NativeError
        with tempfile.TemporaryDirectory() as directory:
            root, now = Path(directory), time.time()
            home = root / 'active-home'
            first, second = login('first'), login('second')
            ids = [auth_identity(raw)[0] for raw in (first, second)]
            atomic_write(home / 'auth.json', first)
            saved = AccountVault(root, home)
            atomic_write(saved.path(ids[1]), second)
            db = Database(root / 'test.db')
            c = SimpleNamespace(root=root, db=db, account_vault=saved)
            db.set_setting('accounts', [{'account_id': ident, 'status': 'ready', 'name': 'Account'} for ident in ids])
            db.activate_account(ids[0]); db.record_usage(account(now, daily=30))
            before = db.setting('account_usage')
            messages, packets = [], []
            process = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0), terminate=Mock(), kill=Mock())
            def write(raw):
                packet = json.loads(raw)
                messages.append(packet['method'])
                if packet['method'] == 'initialized':
                    return
                result = {'initialize': {}, 'account/read': {'account': {'type': 'chatgpt', 'email': 'second@example.test'}},
                          'account/rateLimits/read': {**account(now, daily=90), 'accountId': 'workspace'},
                          'getAuthStatus': {'authMethod': 'chatgpt', 'authToken': 'rotated-access'}}[packet['method']]
                packets.append((json.dumps({'id': packet['id'], 'result': result}) + '\n').encode())
            process.stdin = SimpleNamespace(write=write, drain=AsyncMock())
            process.stdout = SimpleNamespace(readline=AsyncMock(side_effect=lambda: packets.pop(0)))
            async def spawn(*args, **kwargs):
                isolated = Path(kwargs['env']['CODEX_HOME'])
                self.assertNotEqual(isolated, home)
                self.assertEqual(isolated.joinpath('auth.json').read_text(), second)
                self.assertIn('cli_auth_credentials_store="file"', args)
                atomic_write(isolated / 'auth.json', login('second', 'rotated-access'))
                return process
            try:
                with patch('app.accounts.asyncio.create_subprocess_exec', AsyncMock(side_effect=spawn)) as start:
                    await refresh_saved_accounts(c)
                    await refresh_saved_accounts(c)
                    start.assert_awaited_once()
                self.assertEqual(messages, ['initialize', 'initialized', 'account/read', 'account/rateLimits/read', 'getAuthStatus'])
                self.assertEqual(home.joinpath('auth.json').read_text(), first)
                self.assertEqual(saved.path(ids[1]).read_text(), login('second', 'rotated-access'))
                self.assertFalse(list(saved.directory.glob('.usage-*')))
                self.assertEqual(db.setting('active_account'), ids[0])
                self.assertEqual(db.setting('account_usage'), before)
                history = db.usage_history(time.time(), ids[1])
                self.assertEqual(history['daily'][0]['remaining'], 10)
                key = 'account_telemetry/' + ids[1]
                db.set_setting(key, {'attempted_at': now - 61})
                with patch('app.accounts.observe_saved_account', AsyncMock(side_effect=NativeError('private-token'))) as observe:
                    await refresh_saved_accounts(c)
                    await refresh_saved_accounts(c)
                    observe.assert_awaited_once()
                    self.assertNotIn('private-token', json.dumps(db.setting(key)))
                    self.assertEqual(db.usage_history(time.time(), ids[1]), history)
                    db.set_setting(key, {'attempted_at': now - 61})
                    db.set_setting('account_switch', {'phase': 'waiting_turn'})
                    await refresh_saved_accounts(c)
                    db.set_setting('account_switch', {})
                    c.maintenance = True
                    await refresh_saved_accounts(c)
                    observe.assert_awaited_once()
                self.assertEqual(db.setting('accounts')[1]['status'], 'ready')
                self.assertEqual(db.setting('active_account'), ids[0])
                process.terminate.assert_called_once()
            finally:
                db.conn.close()

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
            from app.native import NativeError
            atomic_write(home / 'auth.json', first)
            db = Database(root / 'test.db')
            c = SimpleNamespace(db=db, account_vault=vault, native=rpc('test-access-first'), health_errors={},
                                persist_usage_resets=Mock())
            try:
                await refresh(c)
                c.native.rpc = AsyncMock(side_effect=NativeError('Network timeout while refreshing token'))
                with self.assertRaises(NativeError):
                    await refresh(c)
                self.assertEqual(db.setting('accounts')[0]['status'], 'ready')
                c.native.rpc.side_effect = NativeError('refresh_token_reused')
                with self.assertRaisesRegex(ValueError, 'sign in again'):
                    await refresh(c)
                self.assertEqual(db.setting('accounts')[0]['status'], 'needs_login')
                self.assertIsNone(db.setting('account_usage')['checked_at'])
                self.assertEqual(vault.path(ident).read_bytes(), before)
            finally:
                db.conn.close()


class AccountSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_change_requires_native_limit_and_waits_or_probes_without_ping_pong(self):
        from app.accounts import automatic_change, remember
        from tests.test_scheduler import SchedulerTests
        fixture = SchedulerTests()
        fixture.setUp()
        c, home, now = fixture.controller, fixture.root / 'codex-home', time.time()
        c.account_vault = AccountVault(c.root, home)
        raws = [login('first'), login('second')]
        ids = [auth_identity(raw)[0] for raw in raws]
        loaded = {'raw': raws[0], 'goal': 'usageLimited'}
        samples = {ids[0]: {**account(now, daily=100, reset=now + 60), 'ordinaryUsageAllowed': False},
                   ids[1]: {**account(now, daily=20, reset=now + 120), 'ordinaryUsageAllowed': True}}
        async def rpc(method, params, **kwargs):
            if method == 'thread/goal/get':
                return {'goal': {'status': loaded['goal'], 'objective': 'Same goal', 'createdAt': 1, 'updatedAt': 10}}
            if method == 'account/read':
                return {'account': {'type': 'chatgpt'}}
            if method == 'account/rateLimits/read':
                return {**samples[auth_identity(loaded['raw'])[0]], 'accountId': 'workspace'}
            if method == 'getAuthStatus':
                return {'authMethod': 'chatgpt', 'authToken': json.loads(loaded['raw'])['tokens']['access_token']}
            raise AssertionError('Automatic selection sent an execution RPC: ' + method)
        c.native.rpc = AsyncMock(side_effect=rpc)
        try:
            for index in reversed(range(2)):
                atomic_write(home / 'auth.json', raws[index]); loaded['raw'] = raws[index]
                metadata, sample = await observe_account(c.native, c.account_vault)
                await remember(c, metadata, sample)
            c.db.activate_account(ids[0]); c.select('first')
            c.record_status(c.db.get('first'), 'usage limited')
            c.native.rpc.reset_mock()
            await automatic_change(c)
            c.native.rpc.assert_not_awaited()  # Default off really means no automatic decision.
            c.db.set_setting('auto_account_change', True)
            loaded['goal'] = 'paused'
            await automatic_change(c)
            self.assertFalse(switching(c))  # No inference from DB status, stale usage or inactivity.
            loaded['goal'] = 'usageLimited'
            c.db.set_setting('account_selection', {**c.db.setting('account_selection'), 'next_check': 0})
            # A stale empty weekly snapshot must not pin the project when B has refilled.
            c.db.record_usage({**account(now - 1000, daily=20, weekly=100, reset=now + 120),
                               'ordinaryUsageAllowed': False}, ids[1])
            await automatic_change(c)
            self.assertFalse(switching(c))
            from app.accounts import refresh_saved_accounts
            async def inactive_observation(controller, ident):
                self.assertEqual(ident, ids[1])
                return (next(a for a in c.db.setting('accounts') if a['account_id'] == ident),
                        {**samples[ident], 'account_id': ident, 'checked_at': time.time()})
            with patch('app.accounts.observe_saved_account', AsyncMock(side_effect=inactive_observation)):
                await refresh_saved_accounts(c)
            c.db.set_setting('account_selection', {**c.db.setting('account_selection'), 'next_check': 0})
            await automatic_change(c)
            self.assertEqual(c.db.setting('account_switch')['target_account'], ids[1])
            self.assertEqual(c.db.setting('account_selection')['attempted'], ids)
            limited_event = json.loads(c.db.conn.execute("SELECT payload FROM events WHERE kind='usage limited' "
                "ORDER BY event_id DESC LIMIT 1").fetchone()[0])
            self.assertEqual(limited_event['usage_limit']['resetAt'], (now + 60) * 1000)
            self.assertEqual(limited_event['usage_limit']['account_id'], ids[0])
            c.db.set_setting('account_switch', {'phase': 'complete'})
            c.db.activate_account(ids[1])
            loaded['raw'] = raws[1]
            atomic_write(home / 'auth.json', raws[1])
            samples[ids[1]] = {**account(now, daily=100, reset=now + 120), 'ordinaryUsageAllowed': False}
            c.db.record_usage({**samples[ids[1]], 'checked_at': now})
            c.db.record_usage({**samples[ids[0]], 'checked_at': now}, ids[0])
            c.db.set_setting('account_selection', {**c.db.setting('account_selection'), 'next_check': 0})
            await automatic_change(c)
            self.assertEqual(c.db.setting('account_selection')['waiting_for']['account_id'], ids[0])
            self.assertEqual(c.db.setting('account_switch')['target_account'], ids[0])  # A's earlier 5h reset.
            c.db.set_setting('auto_account_change', False)
            with patch('app.native.idle_thread', AsyncMock(return_value=False)):
                c.native.rpc.side_effect = lambda method, params, **kw: {'data': ['first']} if method == 'thread/loaded/list' else {}
                await tick(c)
            self.assertEqual(c.db.setting('account_switch')['target_account'], ids[1])
            self.assertEqual(c.db.setting('account_switch')['phase'], 'waiting_turn')
            self.assertFalse(c.db.setting('account_switch')['automatic'])
            # A new native limit after the mapped B-resume is a B event, even if
            # polling did not observe the brief active transition.
            c.db.set_setting('account_switch', {'phase': 'complete'})
            c.unsnooze = {'sessions': [{'sessionId': 'first', 'status': 'stopped',
                                       'resetAt': (now + 3600) * 1000, 'resetSource': 'native'}]}
            c.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'b-resume', 'account_id': ids[1],
                                                     'sent_at': now, 'before_updated_at': 10}))
            c.record_goal(c.db.get('first'), {'status': 'usageLimited', 'updatedAt': 11})
            self.assertEqual(c.db.setting('usage_account/first'), ids[1])
            self.assertEqual(json.loads(c.db.get('first')['usage_limit'])['resetAt'], (now + 120) * 1000)
            self.assertEqual(c.db.conn.execute("SELECT COUNT(*) FROM events WHERE kind='usage limited'").fetchone()[0], 2)
            c.record_goal(c.db.get('first'), {'status': 'usageLimited', 'updatedAt': 11})
            self.assertEqual(c.db.conn.execute("SELECT COUNT(*) FROM events WHERE kind='usage limited'").fetchone()[0], 2)
            # Expiration of the CURRENT login must not pin a genuinely limited
            # goal to it when a different saved login is still usable.
            c.db.activate_account(ids[0])
            c.db.update('first', goal_status='active', operation=None)
            c.record_status(c.db.get('first'), 'usage limited')
            c.db.set_setting('auto_account_change', True)
            c.db.record_usage({**account(time.time(), daily=20), 'ordinaryUsageAllowed': True}, ids[1])
            atomic_write(home / 'auth.json', raws[0]); loaded['raw'] = raws[0]
            async def expired_rpc(method, params, **kwargs):
                if method == 'account/read':
                    from app.native import NativeError
                    raise NativeError('refresh_token_expired')
                return await rpc(method, params, **kwargs)
            c.native.rpc.side_effect = expired_rpc
            await automatic_change(c)
            self.assertEqual(c.db.setting('account_switch')['target_account'], ids[1])
            self.assertEqual(next(a for a in c.db.setting('accounts') if a['account_id'] == ids[0])['status'], 'needs_login')
        finally:
            fixture.tearDown()

    async def test_regular_browser_login_cancel_and_removal_preserve_accounts_and_native_context(self):
        from app.accounts import public_state, recover_switch, remove_account
        from tests.test_scheduler import SchedulerTests
        import uuid
        fixture = SchedulerTests()
        fixture.setUp()
        c, home = fixture.controller, fixture.root / 'codex-home'
        c.account_vault = AccountVault(c.root, home)
        raws = [login('first'), login('second')]
        ids = [auth_identity(raw)[0] for raw in raws]
        loaded = {'raw': raws[0], 'goal': 'active', 'turn': 'idle'}
        goal = {'objective': 'Keep context', 'createdAt': 17, 'updatedAt': 20}
        url = ('https://auth.openai.com/oauth/authorize?response_type=code&'
               'redirect_uri=http%3A%2F%2F127.0.0.1%3A1455%2Fauth%2Fcallback&state=test-state&'
               'code_challenge=test-pkce&code_challenge_method=S256')
        async def rpc(method, params, **kwargs):
            if method == 'thread/goal/get':
                return {'goal': {**goal, 'status': loaded['goal']}}
            if method == 'thread/goal/set':
                loaded['goal'] = params['status']; return {}
            if method == 'thread/loaded/list':
                return {'data': ['first']}
            if method == 'thread/read':
                return {'thread': {'status': {'type': loaded['turn']}}}
            if method == 'account/read':
                if loaded.get('requires_login'):
                    return {'account': None, 'requiresOpenaiAuth': True}
                return {'account': {'type': 'chatgpt'} if loaded['raw'] else None}
            if method == 'account/rateLimits/read':
                return {**account(time.time()), 'accountId': 'workspace', 'ordinaryUsageAllowed': True}
            if method == 'getAuthStatus':
                return {'authMethod': 'chatgpt', 'authToken': json.loads(loaded['raw'])['tokens']['access_token']}
            if method == 'account/login/start':
                self.assertIsNone(loaded['raw'])  # Native reload actually signed out locally.
                return {'type': 'chatgpt', 'loginId': str(uuid.uuid4()), 'authUrl': url}
            if method == 'account/login/cancel':
                return {}
            raise AssertionError('Unexpected native execution: ' + method)
        async def reloaded(controller, state):
            loaded['raw'] = home.joinpath('auth.json').read_text() if home.joinpath('auth.json').exists() else None
        c.native.rpc = AsyncMock(side_effect=rpc)
        c.worker, c.worker_seen = SimpleNamespace(closed=False), time.monotonic()
        c.cancel_wakes = AsyncMock()
        atomic_write(home / 'auth.json', raws[0])
        atomic_write(home / 'sessions/original.jsonl', 'Original native history')
        atomic_write(home / 'config.toml', 'preserve = true')
        try:
            await refresh(c)
            c.select('first')
            c.db.update('first', goal_status='active')
            mapping = [(p['codex_session_id'], p['project_path'], p['queue_position']) for p in c.db.all()]
            with patch('app.accounts.reload_native', AsyncMock(side_effect=reloaded)), patch('app.worker_server.send', AsyncMock()) as send:
                await request_switch(c, None, adding=True)
                # A forged early cancel cannot bypass the running-turn barrier.
                with self.assertRaisesRegex(ValueError, 'No failed or pending'):
                    await recover_switch(c, restore=True)
                for _ in range(6):
                    await tick(c)
                self.assertEqual(c.db.setting('account_switch')['phase'], 'logging_in')
                self.assertFalse(home.joinpath('auth.json').exists())
                self.assertEqual(c.account_vault.path(ids[0]).read_text(), raws[0])
                self.assertEqual(send.await_args.args[1]['url'], url)
                exported = json.dumps(public_state(c))
                self.assertNotIn(url, exported)
                self.assertNotIn('test-access', exported)
                atomic_write(home / 'auth.json', raws[1])
                loaded['raw'] = raws[1]  # Actual native callback; notification may have been lost.
                for _ in range(3):
                    await tick(c)
                self.assertEqual(c.db.setting('active_account'), ids[1])
                self.assertEqual(len(c.db.setting('accounts')), 2)
                self.assertEqual(public_state(c)['account_operation']['phase'], 'confirming_resume')
                self.assertIsNone(c.db.get('first')['resume_result'])
                c.db.update('first', operation=None)
                loaded['goal'] = 'paused'
                c.db.set_setting('manual_pause/first', True)
                await request_switch(c, None, adding=True)
                for _ in range(5):
                    await tick(c)
                self.assertEqual(c.db.setting('account_switch')['phase'], 'logging_in')
                await recover_switch(c, restore=True)
                loaded['turn'] = 'active'
                await tick(c)
                self.assertEqual(c.db.setting('account_switch')['phase'], 'waiting_turn')
                self.assertFalse(home.joinpath('auth.json').exists())
                loaded['turn'] = 'idle'
                for _ in range(6):
                    await tick(c)
                self.assertEqual(c.db.setting('active_account'), ids[1])
                self.assertTrue(c.db.setting('manual_pause/first'))
                self.assertIsNone(c.db.get('first')['operation'])
                # A natively missing/expired login must not lock out regular reauthentication.
                loaded['requires_login'] = True
                with self.assertRaisesRegex(ValueError, 'sign in again'):
                    await refresh(c)
                self.assertEqual(next(a for a in c.db.setting('accounts') if a['account_id'] == ids[1])['status'], 'needs_login')
                self.assertIsNone(c.db.setting('account_usage').get('checked_at'))
                await request_switch(c, None, adding=True)
                for _ in range(5):
                    await tick(c)
                self.assertEqual(c.db.setting('account_switch')['phase'], 'logging_in')
                self.assertEqual(c.account_vault.path(ids[1]).read_text(), raws[1])
                loaded['requires_login'] = False
                loaded['raw'] = raws[1]
                atomic_write(home / 'auth.json', raws[1])
                for _ in range(3):
                    await tick(c)
                self.assertEqual(next(a for a in c.db.setting('accounts') if a['account_id'] == ids[1])['status'], 'ready')
                self.assertTrue(c.db.setting('manual_pause/first'))
                self.assertIsNone(c.db.get('first')['operation'])
            with self.assertRaisesRegex(ValueError, 'exact account name'):
                remove_account(c, ids[0], 'wrong')
            with self.assertRaisesRegex(ValueError, 'active account'):
                remove_account(c, ids[1], 'second@example.test')
            with patch.object(c.db, 'delete_account_usage', side_effect=RuntimeError('Simulated crash')):
                with self.assertRaises(RuntimeError):
                    remove_account(c, ids[0], 'first@example.test')
            await tick(c)  # The durable removal journal finishes without restoring credentials.
            self.assertIsNone(c.db.setting('account_remove'))
            self.assertEqual([a['account_id'] for a in c.db.setting('accounts')], [ids[1]])
            self.assertTrue(c.account_vault.path(ids[1]).exists())
            self.assertEqual(home.joinpath('sessions/original.jsonl').read_text(), 'Original native history')
            self.assertEqual(home.joinpath('config.toml').read_text(), 'preserve = true')
            self.assertEqual(mapping, [(p['codex_session_id'], p['project_path'], p['queue_position']) for p in c.db.all()])
            self.assertFalse(any(call.args[0] in ('account/logout', 'logout', 'turn/start', 'turn/interrupt') for call in c.native.rpc.await_args_list))
        finally:
            fixture.tearDown()

    async def test_account_reset_wait_and_notifications_never_borrow_another_accounts_state(self):
        from app.accounts import bind_legacy_limits, finish_switch, fresh_usage, resume_account_wait, wake_key
        from app.discord_bot import EMBED_COLORS, status_embed
        from app.prompts import reconcile
        from tests.test_scheduler import SchedulerTests
        import hashlib
        fixture = SchedulerTests()
        fixture.setUp()
        c, now = fixture.controller, time.time()
        goal = {'objective': 'Original goal', 'createdAt': 17, 'updatedAt': 20, 'status': 'usageLimited'}
        running = set()
        async def rpc(method, params, **kwargs):
            if method == 'thread/loaded/list':
                return {'data': ['first', 'second']}
            if method == 'thread/goal/get':
                return {'goal': goal}
            if method == 'thread/read':
                return {'thread': {'id': params['threadId'], 'cwd': str(c.root / params['threadId']),
                                   'status': {'type': 'active' if params['threadId'] in running else 'idle'}}}
            raise AssertionError('Unexpected execution RPC: ' + method)
        c.native.rpc = AsyncMock(side_effect=rpc)
        try:
            c.select('first')
            reset_a, reset_b = int((now + 300) * 1000), int((now + 900) * 1000)
            c.db.update('first', goal_status='usage limited', usage_limit=json.dumps({'resetAt': reset_a}))
            c.db.set_setting('usage_wake/first', {'reset_at': reset_a})
            c.db.event('first', 'usage limited', {'reason': None})
            bind_legacy_limits(c, 'a')
            c.db.set_setting('accounts', [{'account_id': 'a', 'name': 'Account A'},
                                          {'account_id': 'b', 'name': 'Account B'}])
            c.db.activate_account('a')
            self.assertEqual(c.db.setting(wake_key(c, c.db.get('first')))['reset_at'], reset_a)
            old_event = dict(c.db.conn.execute('SELECT * FROM events').fetchone())
            old_payload = json.loads(old_event['payload']) | {'embed_color': EMBED_COLORS[0]}
            c.db.activate_account('b')
            self.assertIsNone(c.db.setting(wake_key(c, c.db.get('first'))))
            c.db.record_usage({**account(now, daily=100, reset=now + 900), 'ordinaryUsageAllowed': False})
            c.unsnooze = {'sessions': [{'sessionId': 'first', 'status': 'stopped', 'resetAt': reset_b}]}
            c.persist_usage_resets()
            self.assertEqual(json.loads(c.db.get('first')['usage_limit'])['resetAt'], reset_a)
            self.assertEqual(json.loads(c.db.conn.execute('SELECT payload FROM events').fetchone()[0]),
                             json.loads(old_event['payload']))
            c.db.update('first', usage_limit=json.dumps({'resetAt': reset_b}))
            c.db.set_setting('prompt_limit/first', {'goal_status': goal['status'], 'goal_updated_at': 20})
            text = status_embed(c, c.db.get('first'), old_event, old_payload).description
            self.assertIn('Account A', text)
            self.assertIn(f'<t:{int(reset_a / 1000)}:R>', text)
            self.assertNotIn(f'<t:{int(reset_b / 1000)}:', text)
            self.assertNotIn('failed prompt is not replayed', text)  # Policy belongs to the old event.
            self.assertTrue(await reconcile(c, c.db.get('first')))
            c.db.conn.execute("DELETE FROM settings WHERE key='prompt_limit/first'")
            c.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'old-wake',
                                                      'source': 'unsnooze', 'account_id': 'a'}))
            await c.resume_ready()
            self.assertIsNone(c.db.get('first')['operation'])
            self.assertEqual(json.loads(c.db.get('first')['resume_result'])['status'], 'cancelled')
            state = {'id': 'new-switch', 'project_id': 'first', 'session_id': 'first',
                     'project_path': str(c.root / 'first'), 'goal_created_at': 17,
                     'objective_hash': hashlib.sha256(goal['objective'].encode()).hexdigest(),
                     'goal_hold': True, 'target_account': 'b'}
            await finish_switch(c, state)
            self.assertEqual(c.db.setting('account_wait')['account_id'], 'b')
            self.assertIsNone(c.db.get('first')['operation'])  # No refill invented from A's reset.
            c.db.conn.close()
            c.db = Database(c.root / 'test.db')
            self.assertTrue(await resume_account_wait(c))
            c.select('second')
            self.assertFalse(await resume_account_wait(c))
            self.assertIsNotNone(c.db.setting('account_wait'))  # Queue-away/back survives.
            c.select('first')
            c.db.record_usage({**account(now + 5, reset=now + 900), 'ordinaryUsageAllowed': True})
            self.assertFalse(fresh_usage(c.db.setting('account_usage'), 'b'))  # Future sample.
            c.db.set_setting('selected', None)
            with patch('app.accounts.time.time', return_value=now + 10):
                c.db.set_setting('selected', 'first')
                c.db.reorder(['second', 'first'])
                await finish_switch(c, state)
                self.assertEqual(c.db.setting('account_wait')['reason'], 'queue')
                self.assertIsNone(c.db.get('first')['operation'])
                c.db.reorder(['first', 'second'])
                c.db.set_setting('selected', None)
                # A later real observation, not the switch request, confirms availability.
                c.db.record_usage({**account(now + 6, reset=now + 900), 'ordinaryUsageAllowed': True})
                running.add('second')
                self.assertTrue(await resume_account_wait(c))
                self.assertIsNone(c.db.get('first')['operation'])
                self.assertIsNone(c.db.setting('selected'))
                running.clear()
                self.assertTrue(await resume_account_wait(c))
                self.assertFalse(await resume_account_wait(c))  # One durable attempt, no second send.
            self.assertEqual(c.db.setting('selected'), 'first')
            operation = json.loads(c.db.get('first')['operation'])
            self.assertEqual((operation['source'], operation['account_id']), ('account-reset', 'b'))
            self.assertNotIn('sent_at', operation)
            self.assertIsNone(c.db.setting('account_wait'))
            c.db.update('first', operation=None)
            c.db.record_usage({**account(now, daily=100), 'ordinaryUsageAllowed': False})
            await finish_switch(c, state)
            c.db.set_setting('manual_pause/first', True)
            self.assertFalse(await resume_account_wait(c))
            self.assertIsNone(c.db.setting('account_wait'))
            self.assertIsNone(c.db.get('first')['operation'])
            self.assertFalse(any(call.args[0] in ('turn/start', 'thread/goal/set') for call in c.native.rpc.await_args_list))
        finally:
            fixture.tearDown()

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
                await remember(c, metadata, usage)
            c.db.activate_account(ids[0])
            c.select('first')
            c.db.update('first', goal_status='active')
            queued_resume = {'kind': 'resume', 'source': 'queue', 'id': 'queued-second', 'requested_at': time.time()}
            c.db.update('second', operation=json.dumps({**queued_resume, 'started_at': time.time()}))
            with self.assertRaisesRegex(ValueError, 'Wait for project lifecycle/resume'):
                await request_switch(c, ids[1])
            c.db.update('second', operation=json.dumps(queued_resume))
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
            from app.accounts import recover_switch
            deadline = c.db.setting('account_switch')['requested_at'] + 3601
            with patch('app.accounts.time.time', return_value=deadline):
                await tick(c)
                self.assertEqual(c.db.setting('account_switch')['phase'], 'recovery_required')
                self.assertEqual(c.account_vault.auth_path.read_text(), logins[0])
                self.assertEqual(c.db.conn.execute('SELECT status FROM jobs').fetchone()[0], 'running')
                await recover_switch(c)
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
            self.assertEqual(json.loads(c.db.get('second')['operation']), queued_resume)
            # Switching away from a quota-empty account must carry the controller's
            # own continuation pause, not strand the goal or borrow its old reset.
            from app.accounts import finish_switch
            c.db.update('first', operation=None, goal_status='paused')
            c.db.record_usage({**account(time.time(), daily=100), 'ordinaryUsageAllowed': False})
            await finish_switch(c, c.db.setting('account_switch'))
            self.assertTrue(c.db.setting('account_wait')['goal_hold'])
            saved_wait = c.db.setting('account_wait')
            saved_switch = c.db.setting('account_switch')
            for field in ('account_id', 'session_id', 'objective_hash'):
                c.db.set_setting('account_wait', {**saved_wait, field: 'obsolete'})
                await request_switch(c, ids[0])
                self.assertNotIn('project_id', c.db.setting('account_switch'))
                c.db.set_setting('account_switch', saved_switch)
            c.db.set_setting('account_wait', saved_wait)
            c.db.set_setting('manual_pause/first', True)
            await request_switch(c, ids[0])
            self.assertNotIn('project_id', c.db.setting('account_switch'))
            c.db.set_setting('manual_pause/first', False)
            c.db.set_setting('account_switch', saved_switch)
            returning = await request_switch(c, ids[0])
            self.assertEqual(c.db.setting('account_switch').get('project_id'), 'first')
            self.assertTrue(c.db.setting('account_switch')['goal_hold'])
            await c.poll_goals()
            self.assertEqual(c.db.setting('selected'), 'first')
            self.assertFalse(c.db.setting('manual_pause/first', False))
            with patch('app.accounts.reload_native', AsyncMock(side_effect=reload_runtime)):
                for _ in range(6):
                    await tick(c)
            self.assertEqual(c.db.setting('active_account'), ids[0])
            self.assertIsNone(c.db.setting('account_wait'))
            operation = json.loads(c.db.get('first')['operation'])
            self.assertEqual(operation['id'], returning['operation_id'])
            self.assertEqual(operation['account_id'], ids[0])
            self.assertNotIn('sent_at', operation)
            # A user pause during another switch revokes the continuation, not the account change.
            c.db.update('first', operation=None, goal_status='active')
            loaded['goal'] = 'active'
            await request_switch(c, ids[1])
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
                        await rpc('thread/goal/get', {'threadId': 'first'})
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
                        self.assertTrue(all(since is not None for since in c.tui_connections['first'].values()))
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
