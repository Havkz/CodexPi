import importlib.util
import contextlib
from pathlib import Path
import unittest
import tempfile
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from app import actions, power
from app.actions_guard import validate, install as install_guard, LOCAL_FIRST_RUNNERS
from app.windows_ci import ExecutionSlot
from app.windows_worker import Worker
from tests import test_power


class ActionsCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def test_controlled_ci_honors_pause_and_never_retries_uncertain_dispatch(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as cleanup:
            c = test_power.PowerTests().controller(directory)
            cleanup.callback(c.db.conn.close)
            c.redactor = SimpleNamespace(clean=str)
            c.db.update('project', github_repo='Havkz/Project', goal_status='active')
            c.db.set_setting('self_hosted_actions', True)
            c.db.set_setting('github_actions', {'checked_at': time.time(), 'jobs': []})
            sha = 'a' * 40
            command = AsyncMock(return_value={'stdout': 'main'})
            with patch('app.controller.command', command):
                await actions.dispatch_ci(c, c.db.get('project'), sha)
                command.assert_not_awaited()  # Intermediate pushes are not CI requests.
                c.db.update('project', goal_status='complete')
                c.db.set_setting('completion_check/project', {'checked_at': time.time()})
                for hold in ('pause_all', 'manual_pause/project'):
                    c.db.set_setting(hold, True)
                    await actions.dispatch_ci(c, c.db.get('project'), sha)
                    command.assert_not_awaited()
                    c.db.set_setting(hold, False)
                async def response(*args, **kwargs):
                    if args[:2] == ('git', 'ls-remote'):
                        return {'stdout': sha + '\trefs/heads/main'}
                    if args[:2] == ('gh', 'api'):
                        raise TimeoutError('response lost after submission')
                    return {'stdout': 'main'}
                command.side_effect = response
                await actions.dispatch_ci(c, c.db.get('project'), sha)
                receipt = c.db.setting('ci_dispatch/project')[sha]
                self.assertEqual(receipt['phase'], 'uncertain')
                self.assertIn('response lost', receipt['error'])
                before = command.await_count
                await actions.dispatch_ci(c, c.db.get('project'), sha)
                self.assertEqual(command.await_count, before)
                next_sha = 'b' * 40
                command.side_effect = None
                command.return_value = {'stdout': next_sha + '\trefs/heads/main'}
                await actions.dispatch_ci(c, c.db.get('project'), next_sha)
                self.assertEqual(c.db.setting('ci_dispatch/project')[next_sha]['phase'], 'submitted')
                before = command.await_count
                await actions.dispatch_ci(c, c.db.get('project'), next_sha)
                self.assertEqual(command.await_count, before)
                with patch('app.actions.time.time', return_value=time.time() + 901):
                    await actions.dispatch_ci(c, c.db.get('project'), next_sha)
                self.assertEqual(c.db.setting('ci_dispatch/project')[next_sha]['phase'], 'uncertain')
                self.assertEqual(command.await_count, before)
            c.db.conn.close()

    async def test_setup_is_journaled_idempotent_and_only_github_confirms_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            c = test_power.PowerTests().controller(directory)
            ident = str(uuid.uuid4())
            c.db.conn.execute("UPDATE projects SET project_id=?,github_repo=?", (ident, 'Havkz/New-Project'))
            c.worker = SimpleNamespace(closed=False)
            c.worker_seen = time.monotonic()
            c.redactor = SimpleNamespace(clean=str)
            project = c.db.get(ident)
            worker = Worker(directory, 'private-secret', 'https://unused')
            try:
                with patch('app.worker_server.send', AsyncMock()) as send:
                    with self.assertRaisesRegex(RuntimeError, 'confirmation'):
                        await actions.register(c, project)
                    body = send.call_args.args[1]
                    with self.assertRaisesRegex(RuntimeError, 'confirmation'):
                        await actions.register(c, project)
                    send.assert_called_once()
                result = {'stdout': '', 'stderr': '', 'exit_code': 0, 'artifacts': []}
                with patch('app.windows_worker.execute', AsyncMock(return_value=result)) as execute:
                    self.assertIsNone(worker.accept_actions_setup(body))
                    self.assertIsNone(worker.accept_actions_setup(body))
                    await worker.execution
                    execute.assert_awaited_once()
                    self.assertEqual(execute.call_args.args[0][-3:], ['--project-id', ident, 'Havkz/New-Project'])
                    reply = worker.accept_actions_setup(body)
                    self.assertEqual(reply['type'], 'actions_setup_result')
                    actions.setup_result(c, reply)
                    self.assertEqual(c.db.setting('actions_registration/' + ident)['phase'], 'registered')
                    actions.setup_result(c, reply)  # Duplicate delivery does not change its result.
                    with self.assertRaises(ValueError):
                        worker.accept_actions_setup({**body, 'repo': 'Havkz/Other'})
                    with self.assertRaises(ValueError):
                        worker.accept_actions_setup({**body, 'id': str(uuid.uuid4()), 'argv': ['shutdown']})
                    with self.assertRaises(ValueError):
                        worker.accept_actions_setup({**body, 'id': str(uuid.uuid4()), 'repo': 'Other/Project'})
                state = c.db.setting('actions_registration/' + ident)
                state['phase'] = 'sent'
                c.db.set_setting('actions_registration/' + ident, state)
                actions.setup_inventory(c, [body['id']])
                self.assertEqual(c.db.setting('actions_registration/' + ident)['phase'], 'sent')
                actions.setup_inventory(c, [])
                self.assertEqual(c.db.setting('actions_registration/' + ident)['phase'], 'pending')
            finally:
                worker.db.close()
                c.db.conn.close()

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
            job_status = 'queued'
            job_labels = ['self-hosted', 'Windows', 'codexpi']
            async def api(*args, **kwargs):
                self.assertIn('--header', args)
                self.assertIn('Cache-Control: no-cache', args)
                endpoint = args[-1]
                if endpoint.endswith('/runners'):
                    data = {'runners': [{'id': 21, 'os': 'Windows', 'labels': [{'name': 'codexpi'}]}]}
                elif '/jobs?' in endpoint:
                    data = [{'jobs': [{'id': 11, 'name': 'tests', 'status': job_status, 'runner_id': None,
                                       'labels': job_labels}]}]
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
                    queued = True
                    c.db.set_setting('github_actions', {'checked_at': 0,
                        'first_seen': {'Havkz/CodexPi/11': time.time() - 901}})
                    await actions.poll(c)
                    self.assertIn('15 minutes', c.db.setting('github_actions')['error'])
                    self.assertTrue(actions.busy(c))
                    job_status = 'in_progress'
                    state = c.db.setting('github_actions')
                    state['checked_at'] = 0
                    c.db.set_setting('github_actions', state)
                    await actions.poll(c)
                    self.assertNotIn('error', c.db.setting('github_actions'))
                    self.assertTrue(actions.busy(c))  # Confirmed running CI still owns priority.
                    for job_labels in [['ubuntu-latest'], ['windows-latest']]:
                        c.db.set_setting('github_actions', {'checked_at': 0})
                        await actions.poll(c)
                        self.assertNotIn('error', c.db.setting('github_actions'))
                        self.assertFalse(actions.busy(c))
                    job_labels = ['unexpected-runner']
                    c.db.set_setting('github_actions', {'checked_at': 0})
                    await actions.poll(c)
                    self.assertIn('Non-local', c.db.setting('github_actions')['error'])
            finally:
                c.db.conn.close()


spec = importlib.util.spec_from_file_location('actions_installer',
    Path(__file__).resolve().parents[1] / 'Setup/install-actions-runner.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RunnerInstallationTests(unittest.TestCase):
    def test_explicit_local_first_fallback_preserves_controlled_triggers(self):
        for expression in LOCAL_FIRST_RUNNERS:
            job = {'runs-on': expression}
            validate({'on': 'workflow_dispatch', 'jobs': {'test': job}}, set())
            with self.assertRaises(ValueError):
                validate({'on': 'push', 'jobs': {'test': job}}, set())
        job = {'runs-on': 'ubuntu-latest', 'if': "vars.CI_WINDOWS_RUNNER == ''"}
        validate({'on': 'workflow_dispatch', 'jobs': {'test': job}}, set())
        with self.assertRaises(ValueError):
            validate({'on': 'workflow_dispatch', 'jobs': {'test': dict(job, **{'if': 'always()'})}}, set())

    def test_push_guard_rejects_hosted_dynamic_and_external_reusable_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'repository root'):
                install_guard(directory)
            self.assertFalse((Path(directory) / '.git').exists())
        validate({'on': 'workflow_dispatch', 'jobs': {'test': {'runs-on': ['self-hosted', 'Windows', 'X64', 'codexpi']}}}, set())
        local = '.github/workflows/checks.yml'
        validate({'on': 'workflow_call', 'jobs': {'test': {'uses': './' + local}}}, {local})
        for job in ({'runs-on': 'ubuntu-latest'}, {'runs-on': '${{ matrix.runner }}'},
                    {'runs-on': ['self-hosted', 'Windows']},
                    {'uses': 'other/repository/.github/workflows/tests.yml@main'},
                    {'uses': './' + local}):
            with self.subTest(job=job), self.assertRaises(ValueError):
                validate({'on': 'workflow_dispatch', 'jobs': {'test': job}}, set())

    def test_managed_workflows_cannot_trigger_push_pr_timer_or_cancel_running_ci(self):
        job = {'runs-on': ['self-hosted', 'Windows', 'X64', 'codexpi']}
        for trigger in ('push', ['push', 'pull_request'], {'schedule': [{'cron': '* * * * *'}]}):
            with self.subTest(trigger=trigger), self.assertRaisesRegex(ValueError, 'controlled'):
                validate({'on': trigger, 'jobs': {'test': job}}, set())
        validate({'on': {'workflow_dispatch': {}}, 'jobs': {'test': job}}, set())
        with self.assertRaisesRegex(ValueError, 'cancel'):
            validate({'on': 'workflow_dispatch', 'concurrency': {'cancel-in-progress': True},
                      'jobs': {'test': job}}, set())

    def test_linux_distribution_cannot_be_registered_under_an_interactive_account(self):
        spec = importlib.util.spec_from_file_location('linux_ci',
            Path(__file__).resolve().parents[1] / 'Setup/run-linux-ci.py')
        linux = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(linux)
        with patch.object(linux.os, 'name', 'nt'), patch.object(linux, 'run', return_value=SimpleNamespace(
                stdout='"USER\\User","S-1-5-21-1000"')) as command:
            with self.assertRaisesRegex(RuntimeError, 'service account'):
                linux.prepare()
            command.assert_called_once()  # No import, download, reboot or user-distro mutation.

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
