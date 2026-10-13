import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.native import Native, tui_proxy, validate_hook_trust
from tests import test_scheduler


class HookReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = test_scheduler.SchedulerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.c = self.fixture.controller
        self.hook = {'key': 'reviewed-hook', 'currentHash': 'sha256:' + 'a' * 64,
                     'enabled': True, 'isManaged': False, 'trustStatus': 'modified'}
        self.listing = {'data': [{'hooks': [self.hook], 'errors': [], 'warnings': []}]}
        self.write = {'edits': [{'keyPath': 'hooks.state', 'mergeStrategy': 'upsert',
                     'value': {self.hook['key']: {'trusted_hash': self.hook['currentHash']}}}],
                      'reloadUserConfig': True}

    async def test_resume_reports_review_before_changing_manual_hold_or_starting_tui(self):
        c = self.c
        c.db.set_setting('manual_pause/first', True)
        c.attach_ready = AsyncMock()
        original = c.native.rpc.side_effect

        async def rpc(method, params, **kwargs):
            if method == 'hooks/list':
                return self.listing
            return await original(method, params, **kwargs)

        c.native.rpc.side_effect = rpc
        with self.assertRaisesRegex(ValueError, 'Resume needs hook review: 1'):
            await c.resume('first')
        self.assertTrue(c.db.setting('manual_pause/first'))
        self.assertIsNone(c.db.setting('selected'))
        self.assertIsNone(c.db.get('first')['operation'])
        c.attach_ready.assert_not_awaited()
        self.listing['data'][0]['errors'] = ['cannot read hook file']
        with self.assertRaisesRegex(ValueError, 'could not be loaded'):
            await c.resume('first')
        self.listing['data'][0]['errors'] = []
        # Disabled and policy-managed hooks never require an interactive grant.
        for field in ('enabled', 'isManaged'):
            self.hook[field] = field == 'isManaged'
            await c.require_trusted_hooks(c.db.get('first'))
            self.hook[field] = field == 'enabled'
        self.hook['trustStatus'] = 'trusted'
        await c.resume('first')
        self.assertEqual(c.db.setting('selected'), 'first')
        self.assertFalse(c.db.setting('manual_pause/first'))

    async def test_restoration_reports_new_hook_review_without_repeated_slash_or_tui_reopen(self):
        c = self.c
        c.select('first')
        c.db.update('first', operation=json.dumps({'kind': 'resume', 'id': 'resume-before-update'}))
        c.attach_ready, c.slash = AsyncMock(), AsyncMock()
        original = c.native.rpc.side_effect

        async def rpc(method, params, **kwargs):
            if method == 'hooks/list':
                return self.listing
            return await original(method, params, **kwargs)

        c.native.rpc.side_effect = rpc
        await c.resume_ready()
        await c.resume_ready()
        result = json.loads(c.db.get('first')['resume_result'])
        self.assertEqual(result['id'], 'resume-before-update')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('hook review', result['message'])
        self.assertNotIn('sent_at', json.loads(c.db.get('first')['operation']))
        c.attach_ready.assert_not_awaited()
        c.slash.assert_not_awaited()

    async def test_startup_tui_accepts_exact_current_hook_trust_without_a_thread_mapping(self):
        upstream = SimpleNamespace(rpc=AsyncMock(return_value=self.listing), close=AsyncMock())
        app = web.Application()
        app['controller'], app['sockets'] = self.c, set()
        app.router.add_get('/', tui_proxy)
        with patch.object(Native, 'connect', AsyncMock(return_value=upstream)):
            async with TestClient(TestServer(app)) as client:
                async with client.ws_connect('/') as socket:
                    await socket.send_json({'id': 1, 'method': 'config/batchWrite', 'params': self.write})
                    self.assertIn('result', await socket.receive_json())
                    self.assertEqual(upstream.rpc.await_args.args, ('config/batchWrite', self.write))
                    self.assertEqual(self.c.tui_connections, {})
                    self.hook['currentHash'] = 'sha256:' + 'b' * 64
                    await socket.send_json({'id': 2, 'method': 'config/batchWrite', 'params': self.write})
                    self.assertIn('error', await socket.receive_json())
                    await socket.send_json({'id': 3, 'method': 'config/batchWrite', 'params': {
                        'edits': [{'keyPath': 'model', 'value': 'gpt-6.1-sol', 'mergeStrategy': 'upsert'}]}})
                    self.assertIn('error', await socket.receive_json())
                    self.assertEqual(sum(call.args[0] == 'config/batchWrite'
                        for call in upstream.rpc.await_args_list), 1)

    async def test_trust_rejects_foreign_files_mixed_batches_changed_or_managed_hooks(self):
        native = SimpleNamespace(rpc=AsyncMock(return_value=self.listing))
        await validate_hook_trust(self.c, native, self.write)
        for change in ({'filePath': '/outside/config.toml'}, {'expectedVersion': 'stale'},
                       {'reloadUserConfig': False}, {'unrecognized': True},
                       {'edits': self.write['edits'] * 2}, {'edits': []}):
            with self.assertRaises(ValueError):
                await validate_hook_trust(self.c, native, {**self.write, **change})
        for change in ({'mergeStrategy': 'replace'}, {'keyPath': 'features'},
                       {'value': {}}, {'value': {'unknown': {'trusted_hash': self.hook['currentHash']}}},
                       {'value': {'reviewed-hook': {'trusted_hash': 'sha256:' + 'b' * 64}}},
                       {'value': {'reviewed-hook': {'trusted_hash': self.hook['currentHash'], 'enabled': True}}}):
            with self.assertRaises(ValueError):
                await validate_hook_trust(self.c, native, {**self.write, 'edits': [{**self.write['edits'][0], **change}]})
        for field in ('enabled', 'isManaged'):
            self.hook[field] = field == 'isManaged'
            with self.assertRaises(ValueError):
                await validate_hook_trust(self.c, native, self.write)
            self.hook[field] = field == 'enabled'
        self.listing['data'][0]['warnings'] = ['loading warning']
        with self.assertRaises(ValueError):
            await validate_hook_trust(self.c, native, self.write)
