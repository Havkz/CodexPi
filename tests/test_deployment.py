import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app import deployment, lifecycle
from app.db import Database
from tests import test_lifecycle

Crash = test_lifecycle.Crash


class DeploymentTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, temp):
        c, state, original_command = test_lifecycle.LifecycleTests().make_controller(temp)
        state.update(service=False, starts=0, unhealthy=False)
        async def command(*args, **kwargs):
            if args[0] == 'systemctl':
                if 'enable' in args:
                    if not state['service']:
                        state['starts'] += 1
                    state['service'] = True
                elif 'disable' in args:
                    state['service'] = False
                elif 'show' in args:
                    return {'stdout': 'active' if state['service'] else 'inactive', 'exit_code': 0}
                elif 'is-active' in args and not state['service']:
                    raise RuntimeError('Service is not active')
            elif args[0] == 'health' and state['unhealthy']:
                raise RuntimeError('Application health check failed')
            return await original_command(*args, **kwargs)
        c.refresh_git = AsyncMock()
        c.db.update('project-1', last_commit='a' * 40, last_ci_status='passed')
        body = {'project_id': 'project-1', 'goal_requires_24x7': True, 'reason': 'Explicit test goal requires Pi service',
                'argv': ['python3', 'service.py'], 'check': ['health']}
        return c, state, command, body

    async def test_request_admission_and_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, state, command, body = self.fixture(tmp)
            for changes in ({'goal_requires_24x7': False}, {'check': []}, {'argv': ['python3', 'a\nb']},
                            {'argv': [c.db.get('project-1')['project_path'] + '/service']}):
                with self.assertRaises(ValueError):
                    await deployment.request(c, {**body, **changes})
                self.assertIsNone(c.db.setting('deployment/project-1'))
            c.db.set_setting('selected', None)
            with self.assertRaisesRegex(ValueError, 'selected'):
                await deployment.request(c, body)
            c.db.set_setting('selected', 'project-1')
            target = c.root.parent / 'first'
            target.mkdir()
            with self.assertRaises(ValueError):
                await deployment.request(c, body)
            target.rmdir()
            unit = deployment.unit_path(c, c.db.get('project-1'))
            unit.parent.mkdir(parents=True)
            unit.write_text('unrelated service')
            with self.assertRaisesRegex(ValueError, 'ownership'):
                await deployment.request(c, body)
            self.assertEqual(unit.read_text(), 'unrelated service')
            c.db.conn.close()

    async def test_completion_moves_once_renames_and_deletes_owned_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, state, command, body = self.fixture(tmp)
            original = c.db.get('project-1')
            await deployment.request(c, body)
            state['native_status'] = 'complete'
            with patch('app.controller.command', command), patch('app.lifecycle.command', command), \
                    patch('app.deployment.command', command), patch('app.deployment.asyncio.sleep', AsyncMock()):
                await c.complete(c.db.get('project-1'))
                current = c.db.get('project-1')
                self.assertEqual(current['goal_status'], 'complete')
                self.assertEqual(current['project_path'], str(c.root.parent / 'first'))
                self.assertEqual(current['codex_session_id'], original['codex_session_id'])
                self.assertEqual(state['cwd'], current['project_path'])
                self.assertFalse(Path(original['project_path']).exists())
                self.assertTrue(state['service'])
                self.assertEqual(state['starts'], 1)
                # Recovery between deployment and completion does not restart the app.
                await deployment.complete(c, current)
                self.assertEqual(state['starts'], 1)
                await lifecycle.begin(c, 'project-1', 'rename', name='Renamed')
                current = c.db.get('project-1')
                self.assertEqual(current['project_path'], str(c.root.parent / 'renamed'))
                unit = deployment.unit_path(c, current)
                self.assertIn('renamed', unit.read_text())
                self.assertTrue(state['service'])
                await lifecycle.begin(c, 'project-1', 'delete', confirmation='Renamed')
                self.assertFalse(state['service'])
                self.assertFalse(unit.exists())
                self.assertIsNone(c.db.setting('deployment/project-1'))
                self.assertEqual(c.db.all(), [])
                manifest = json.loads((c.root / 'backups/deleted/project-1/manifest.json').read_text())
                self.assertEqual(manifest['deployment']['argv'], body['argv'])
                self.assertEqual(state['repo'], 'owner/renamed')
            c.db.conn.close()

    async def test_deployment_recovers_after_each_effect_without_parallel_goal(self):
        for phase in ('quiesced', 'directory', 'session', 'finalize'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                c, state, command, body = self.fixture(tmp)
                await deployment.request(c, body)
                state['native_status'] = 'complete'
                original_save, original_update = lifecycle.save, c.db.update
                def save(*args):
                    if args[-1] == phase:
                        raise Crash()
                    original_save(*args)
                def update(*args, **kwargs):
                    original_update(*args, **kwargs)
                    if phase == 'finalize' and kwargs.get('lifecycle') == 'ready':
                        raise Crash()
                with patch('app.controller.command', command), patch('app.lifecycle.command', command), \
                        patch('app.deployment.command', command), patch('app.deployment.asyncio.sleep', AsyncMock()):
                    with patch('app.lifecycle.save', save), patch.object(c.db, 'update', update), self.assertRaises(Crash):
                        await c.complete(c.db.get('project-1'))
                    db_path = c.db.path
                    c.db.conn.close()
                    c.db = Database(db_path)
                    await lifecycle.recover(c)
                    await c.complete(c.db.get('project-1'))
                result = c.db.get('project-1')
                self.assertEqual(result['goal_status'], 'complete', result['operation'])
                self.assertEqual(result['lifecycle'], 'ready')
                self.assertEqual(state['starts'], 1)
                self.assertEqual(state['native_status'], 'complete')
                self.assertFalse(any(call[0] == 'thread/goal/set' for call in state['calls']))
                self.assertFalse((c.root / 'projects/first').exists())
                c.db.conn.close()

    async def test_failed_health_keeps_repairable_session_and_never_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, state, command, body = self.fixture(tmp)
            await deployment.request(c, body)
            state.update(native_status='complete', unhealthy=True)
            with patch('app.controller.command', command), patch('app.lifecycle.command', command), \
                    patch('app.deployment.command', command), patch('app.deployment.asyncio.sleep', AsyncMock()):
                await c.complete(c.db.get('project-1'))
            result = c.db.get('project-1')
            self.assertEqual(result['goal_status'], 'stalled')
            self.assertEqual(result['lifecycle'], 'ready')
            self.assertIsNone(result['operation'])
            self.assertEqual(result['project_path'], state['cwd'])
            self.assertIn('health check failed', result['block_reason'])
            self.assertFalse(state['service'])
            self.assertEqual(state['native_status'], 'blocked')
            self.assertEqual(c.db.conn.execute("SELECT count(*) FROM events WHERE kind='complete'").fetchone()[0], 0)
            self.assertFalse(c.db.setting('advance_queue', False))
            c.db.conn.close()

    async def test_pending_ci_does_not_move_or_start_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, state, command, body = self.fixture(tmp)
            await deployment.request(c, body)
            c.db.update('project-1', last_ci_status='pending')
            state['native_status'] = 'complete'
            with patch('app.controller.command', command):
                await c.complete(c.db.get('project-1'))
            self.assertTrue((c.root / 'projects/first').exists())
            self.assertFalse((c.root.parent / 'first').exists())
            self.assertFalse(state['service'])
            self.assertEqual(c.db.setting('deployment/project-1')['status'], 'requested')
            self.assertEqual(c.db.get('project-1')['completion_notified'], 0)
            c.db.conn.close()

    def test_unit_arguments_are_not_shell_or_systemd_expansions(self):
        unit = deployment.render({'project_id': 'example', 'project_path': '/home/pi/project'},
                                 {'argv': ['./service', '$TOKEN', '%n', 'a b', '"quoted"', '\\path']})
        self.assertIn('"/home/pi/project/service"', unit)
        self.assertIn('"$$TOKEN" "%%n" "a b" "\\"quoted\\"" "\\\\path"', unit)
        self.assertIn('KillMode=control-group', unit)
        self.assertIn('WorkingDirectory=/home/pi/project\n', unit)


if __name__ == '__main__':
    unittest.main()
