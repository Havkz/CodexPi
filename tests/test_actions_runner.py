import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
import time
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from app import actions, power
from app.windows_ci import ExecutionSlot
from tests import test_power


class ActionsCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_job_wakes_once_takes_priority_and_unknown_state_prevents_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            c = test_power.PowerTests().controller(directory)
            c.config['github_account'] = 'Havkz'
            c.health_errors = {}
            c.redactor = SimpleNamespace(clean=str)
            c.db.set_setting('self_hosted_actions', True)
            c.db.set_setting('auto_boot_windows', True)
            self.assertTrue(actions.busy(c))  # Missing/stale observation cannot mean idle.
            queued = True
            async def api(*args, **kwargs):
                endpoint = args[-1]
                if endpoint.endswith('/runners'):
                    data = {'runners': [{'id': 21, 'os': 'Windows', 'labels': [{'name': 'codexpi'}]}]}
                elif '/jobs?' in endpoint:
                    data = [{'jobs': [{'id': 11, 'name': 'tests', 'status': 'queued', 'runner_id': None,
                                       'labels': ['self-hosted', 'Windows', 'codexpi']}]}]
                else:
                    data = [{'workflow_runs': [{'id': 10}]}] if queued and 'status=queued' in endpoint else [{'workflow_runs': []}]
                return {'stdout': json.dumps(data)}
            try:
                with patch('app.controller.command', side_effect=api), patch('app.power.wake') as wake:
                    await actions.poll(c)
                    self.assertTrue(actions.busy(c))
                    await power.tick(c)
                    await power.tick(c)
                    wake.assert_called_once()
                    self.assertEqual(c.db.setting('windows_power')['trigger'], ['github-actions', 'Havkz/CodexPi', 11])
                    state = c.db.setting('windows_power')
                    state.update(phase='owned', idle_since=time.time() - 1000)
                    c.db.set_setting('windows_power', state)
                    c.worker = SimpleNamespace(closed=False)
                    c.worker_seen = time.monotonic()
                    with patch('app.worker_server.send', AsyncMock()) as send:
                        await power.tick(c)
                        send.assert_not_called()
                    state = c.db.setting('github_actions')
                    state['checked_at'] = 0
                    c.db.set_setting('github_actions', state)
                    with patch('app.controller.command', side_effect=RuntimeError('GitHub unavailable')):
                        await actions.poll(c)
                    self.assertTrue(actions.busy(c))
                    self.assertIn('GitHub unavailable', c.health_errors['github_actions'])
                    state = c.db.setting('github_actions')
                    state['checked_at'] = 0
                    c.db.set_setting('github_actions', state)
                    queued = False
                    await actions.poll(c)
                    self.assertFalse(actions.busy(c))
                    self.assertNotIn('github_actions', c.health_errors)
            finally:
                c.db.conn.close()


spec = importlib.util.spec_from_file_location('actions_installer',
    Path(__file__).resolve().parents[1] / 'Setup/install-actions-runner.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RunnerInstallationTests(unittest.TestCase):
    def test_one_execution_slot_ci_priority_crash_recovery_and_pid_reuse(self):
        identities = {10: 100, 20: 200, 30: 300}
        with tempfile.TemporaryDirectory() as directory, patch('app.windows_ci.identity', side_effect=lambda pid: identities.get(pid)):
            slot = ExecutionSlot(directory)
            try:
                self.assertTrue(slot.claim(10, 100, 'worker'))
                self.assertFalse(slot.claim(20, 200, 'ci'))
                self.assertTrue(slot.ci_busy())
                slot.release(10, 100)
                self.assertFalse(slot.claim(30, 300, 'worker'))  # Waiting CI goes first.
                self.assertTrue(slot.claim(20, 200, 'ci'))
                slot.release(20, 999)  # A recycled/different process cannot release the slot.
                self.assertFalse(slot.claim(30, 300, 'worker'))
                identities[20] = 201  # The actual owning process has exited; no blind lease timeout.
                self.assertTrue(slot.claim(30, 300, 'worker'))
                self.assertFalse(slot.ci_busy())
                with patch('app.windows_ci.identity', side_effect=OSError('Access denied')):
                    with self.assertRaises(OSError):
                        slot.claim(10, 100, 'ci')
                self.assertEqual(slot.db.execute('SELECT pid FROM execution WHERE acquired=1').fetchall(), [(30,)])
            finally:
                slot.db.close()

    def test_registration_is_explicit_private_and_codexpi_owned(self):
        data = {'full_name': 'Havkz/Sybu-Debug', 'private': True, 'archived': False,
                'description': 'Managed by CodexPi project a5e6f61b-2281-4a2e-a1b2-552e4ae23e25'}
        installer.validate_repository('Havkz/Sybu-Debug', data)
        installer.validate_repository('Havkz/CodexPi', {**data, 'full_name': 'Havkz/CodexPi', 'description': ''})
        for name, changed in [('other/Sybu-Debug', data), ('Havkz/../outside', data),
                              ('Havkz/Sybu-Debug', {**data, 'private': False}),
                              ('Havkz/Sybu-Debug', {**data, 'archived': True}),
                              ('Havkz/Sybu-Debug', {**data, 'description': ''}),
                              ('Havkz/Sybu-Debug', {**data, 'full_name': 'Havkz/Other'})]:
            with self.subTest(name=name, data=changed), self.assertRaises(ValueError):
                installer.validate_repository(name, changed)
