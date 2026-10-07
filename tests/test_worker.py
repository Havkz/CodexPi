import json
from contextlib import closing
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.windows_worker import Worker, execute, protect_secret, relative_path, validate_job


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_login_opens_only_official_url_and_one_owned_callback_tunnel(self):
        url = ('https://auth.openai.com/oauth/authorize?response_type=code&'
               'redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&state=test&'
               'code_challenge=pkce&code_challenge_method=S256')
        with tempfile.TemporaryDirectory() as directory, closing((worker := Worker(directory, 'test-secret', 'http://unused')).db):
            body = {'operation_id': str(uuid.uuid4()), 'url': url, 'expires_at': time.time() + 300}
            process = SimpleNamespace(returncode=None, terminate=lambda: setattr(process, 'returncode', 0), wait=AsyncMock())
            writer = SimpleNamespace(close=lambda: None, wait_closed=AsyncMock())
            with patch('app.windows_worker.asyncio.create_subprocess_exec', AsyncMock(return_value=process)) as spawn, \
                    patch('app.windows_worker.asyncio.open_connection', AsyncMock(return_value=(None, writer))), \
                    patch('app.windows_worker.webbrowser.open', return_value=True) as browser:
                await worker.open_login(body)
                await worker.open_login(body)
                spawn.assert_awaited_once()
                browser.assert_called_once_with(url)
                self.assertIn('127.0.0.1:1455:127.0.0.1:1455', spawn.await_args.args)
                self.assertIn('ExitOnForwardFailure=yes', spawn.await_args.args)
                for bad in (url.replace('auth.openai.com', 'evil.example'),
                            url.replace('localhost%3A1455', 'evil.example%3A1455'),
                            url + '&access_token=not-allowed', 'file:///C:/secret', url.replace('S256', 'plain')):
                    with self.assertRaises(ValueError):
                        await worker.open_login({**body, 'url': bad})
                await worker.close_login_tunnel()
                self.assertIsNone(worker.login_tunnel)
                self.assertIsNone(worker.execution)
                self.assertEqual(worker.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

    async def test_checkout_auth_uses_gh_only_for_git_children(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Worker(directory, secrets.token_hex(32), 'http://unused')
            path = worker.projects / 'test-project'
            repo = 'test/test-project'
            commit = 'a' * 40
            calls = []
            prompt_before = os.environ.get('GIT_TERMINAL_PROMPT')

            async def child(argv, cwd, timeout, *, env=None):
                calls.append(argv)
                stdout = ''
                if argv[0] == 'git':
                    self.assertEqual(argv[1:5], ['-c', 'credential.helper=', '-c',
                                                'credential.helper=!gh auth git-credential'])
                    self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
                    verb = argv[5]
                    if verb == 'clone':
                        self.assertEqual(argv[6:8], ['--no-checkout', 'https://github.com/' + repo + '.git'])
                        (path / '.git').mkdir(parents=True)
                    elif verb == 'remote':
                        stdout = 'https://github.com/' + repo + '.git'
                    elif verb == 'rev-parse':
                        stdout = commit
                else:
                    self.assertEqual(argv, ['test-command'])
                    self.assertIsNone(env)
                    stdout = 'test-passed'
                return {'stdout': stdout, 'stderr': '', 'exit_code': 0, 'timed_out': False, 'artifacts': []}

            with patch('app.windows_worker.execute', child):
                for _ in range(2):  # first clone, then fetch in the same owned checkout
                    job = {'job_id': str(uuid.uuid4()), 'slug': 'test-project', 'repo': repo,
                           'commit': commit, 'argv': ['test-command'], 'timeout': 10, 'artifacts': []}
                    worker.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                                      (job['job_id'], json.dumps(job), 'running', None, time.time()))
                    await worker.run_job(job)
                    result = json.loads(worker.db.execute('SELECT result FROM jobs WHERE id=?',
                                                          (job['job_id'],)).fetchone()[0])
                    self.assertEqual(result['exit_code'], 0, result)
                    self.assertEqual(result['stdout'], 'test-passed')
                    self.assertEqual(result['commit'], commit)
            self.assertEqual(sum(args[0] == 'git' and args[5] == 'clone' for args in calls), 1)
            self.assertEqual(sum(args[0] == 'git' and args[5] == 'fetch' for args in calls), 2)
            self.assertFalse(any('--global' in args or '--system' in args for args in calls))
            self.assertEqual(os.environ.get('GIT_TERMINAL_PROMPT'), prompt_before)
            worker.db.close()

    async def test_native_execution_exit_output_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            result = await execute([sys.executable, '-c',
                'import sys; print("native-output"); print("native-error", file=sys.stderr); sys.exit(7)'], directory, 10)
            self.assertEqual(result['exit_code'], 7)
            self.assertIn('native-output', result['stdout'])
            self.assertIn('native-error', result['stderr'])
            result = await execute([sys.executable, '-c', 'import time; time.sleep(30)'], directory, 1)
            self.assertTrue(result['timed_out'])
            self.assertNotEqual(result['exit_code'], 0)

    def test_validation_and_restart_does_not_repeat(self):
        job = {'type': 'job', 'job_id': str(uuid.uuid4()), 'slug': 'test-project',
               'repo': 'test/test-project', 'commit': 'a' * 40, 'timeout': 10,
               'argv': ['python', '--version'], 'artifacts': ['dist/result.txt']}
        validate_job(job)
        for path in ('../outside', '..\\outside', 'C:\\outside', '\\outside', 'file:stream',
                     '//server/share', 'nested/../../outside', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                relative_path(path)
        with tempfile.TemporaryDirectory() as directory:
            worker = Worker(directory, secrets.token_hex(32), 'http://unused')
            worker.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                (job['job_id'], json.dumps(job), 'running', None, time.time()))
            worker.db.close()
            recovered = Worker(directory, secrets.token_hex(32), 'http://unused')
            row = recovered.db.execute('SELECT * FROM jobs').fetchone()
            self.assertEqual(row['status'], 'finished')
            self.assertTrue(json.loads(row['result'])['outcome_unknown'])
            self.assertIsNone(recovered.execution)
            recovered.db.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_dpapi_current_user_roundtrip(self):
        secret = secrets.token_bytes(32)
        encrypted = protect_secret(secret)
        self.assertNotIn(secret, encrypted)
        self.assertEqual(protect_secret(encrypted, decrypt=True), secret)
        with self.assertRaises(OSError):
            protect_secret(b'not a DPAPI credential', decrypt=True)


if __name__ == '__main__':
    unittest.main()
