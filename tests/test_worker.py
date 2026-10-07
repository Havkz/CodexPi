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
               'redirect_uri=http%3A%2F%2F127.0.0.1%3A1455%2Fauth%2Fcallback&state=test&'
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
                            url.replace('127.0.0.1%3A1455', 'evil.example%3A1455'),
                            url.replace('1455', '8787'), url.replace('auth%2Fcallback', 'other'),
                            url + '&access_token=not-allowed', 'file:///C:/secret', url.replace('S256', 'plain')):
                    with self.assertRaises(ValueError):
                        await worker.open_login({**body, 'url': bad})
                await worker.close_login_tunnel()
                self.assertIsNone(worker.login_tunnel)
                self.assertIsNone(worker.execution)
                self.assertEqual(worker.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)
                from app.common import codex_login_url
                legacy = url.replace('127.0.0.1', 'localhost')
                self.assertEqual(codex_login_url(legacy), legacy)

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

    async def test_checkout_runtime_files_diagnostics_and_collision_recovery(self):
        with tempfile.TemporaryDirectory() as directory, closing((worker := Worker(directory, 'test-secret', 'http://unused')).db):
            path = worker.projects / 'test-project'
            path.mkdir()

            async def git(*args):
                result = await execute(['git', *args], path, 15)
                self.assertEqual(result['exit_code'], 0, result)
                return result['stdout'].strip()

            await git('init')
            await git('config', 'user.name', 'Worker Test')
            await git('config', 'user.email', 'worker@example.invalid')
            await git('config', 'core.autocrlf', 'false')
            await git('remote', 'add', 'origin', 'https://github.com/test/test-project.git')
            source = path / 'source.txt'
            source.write_text('original\n')
            await git('add', 'source.txt')
            await git('commit', '-m', 'original')
            first = await git('rev-parse', 'HEAD')
            source.write_text('next\n')
            collision = path / 'new-file.txt'
            collision.write_text('repository version\n')
            await git('add', 'source.txt', 'new-file.txt')
            await git('commit', '-m', 'next')
            second = await git('rev-parse', 'HEAD')
            await git('checkout', '--detach', first)
            (path / '.git/codexpi-checkout').write_text('test/test-project')
            (path / 'logs').mkdir()
            runtime = path / 'logs/latest.log'
            runtime.write_bytes(b'runtime data\n')
            calls = []

            async def child(argv, cwd, timeout, *, env=None):
                calls.append(argv)
                # Both exact commits are real local Git objects; only network
                # fetching is mocked. Status, checkout and the test run are real.
                if argv[0] == 'git' and len(argv) > 5 and argv[5] == 'fetch':
                    return {'stdout': '', 'stderr': '', 'exit_code': 0, 'timed_out': False}
                return await execute(argv, cwd, timeout, env=env)

            async def run(argv, commit=first):
                job = {'job_id': str(uuid.uuid4()), 'slug': 'test-project', 'repo': 'test/test-project',
                       'commit': commit, 'argv': argv, 'timeout': 15, 'artifacts': []}
                worker.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                                  (job['job_id'], json.dumps(job), 'running', None, time.time()))
                await worker.run_job(job)
                return json.loads(worker.db.execute('SELECT result FROM jobs WHERE id=?', (job['job_id'],)).fetchone()[0])

            command = [sys.executable, '-c', 'print("native-test-ok")']
            with patch('app.windows_worker.execute', child):
                result = await run(command)
                self.assertEqual(result['exit_code'], 0, result)
                self.assertIn('native-test-ok', result['stdout'])
                self.assertEqual(result['commit'], first)
                self.assertIn('logs/latest.log', result['checkout_status'])
                source.write_text('protected user change\n')
                calls.clear()
                diagnostic = await run(['git', 'status', '--short'])
                self.assertEqual(diagnostic['exit_code'], 0, diagnostic)
                self.assertIn('source.txt', diagnostic['stdout'])
                self.assertFalse(any('fetch' in args or 'checkout' in args for args in calls))
                for argv, commit in ((command, first), (['git', 'status', '--ignored'], first),
                                     (['git', 'status', '--short'], second)):
                    result = await run(argv, commit)
                    self.assertEqual(result['exit_code'], -1, result)
                    self.assertIn('source.txt', result['stderr'])
                    self.assertEqual(source.read_text(), 'protected user change\n')
                    self.assertEqual(await git('rev-parse', 'HEAD'), first)
                source.write_text('original\n')
                collision.write_text('protected untracked file\n')
                result = await run(command, second)
                self.assertEqual(result['exit_code'], -1, result)
                self.assertIn('new-file.txt', result['stderr'])
                self.assertEqual(collision.read_text(), 'protected untracked file\n')
                self.assertEqual(await git('rev-parse', 'HEAD'), first)
                (path / '.git/info/exclude').write_text('new-file.txt\n')
                result = await run(command, second)
                self.assertEqual(result['exit_code'], -1, result)
                self.assertEqual(collision.read_text(), 'protected untracked file\n')
                self.assertEqual(await git('rev-parse', 'HEAD'), first)
                collision.unlink()  # Only this test's own file inside its TemporaryDirectory.
                result = await run(command, second)
                self.assertEqual(result['exit_code'], 0, result)
                self.assertEqual(result['commit'], second)
                self.assertEqual(source.read_text(), 'next\n')
                self.assertEqual(runtime.read_bytes(), b'runtime data\n')

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
