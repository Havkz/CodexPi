"""Outbound-only native Windows executor. This process never starts an AI agent."""
import asyncio
import base64
import contextlib
import ctypes
import errno
from ctypes import wintypes
import json
import logging
import math
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path, PureWindowsPath
import random
import re
import sqlite3
import subprocess
import sys
import time
import uuid
import webbrowser

from aiohttp import ClientSession, ClientTimeout, WSMsgType

from .common import SignedChannel, atomic_write, codex_login_url, read_env

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 2 * 1024 * 1024


def protect_secret(value, decrypt=False):
    """Windows DPAPI CurrentUser; no machine-wide or plaintext key file."""
    if os.name != 'nt':
        raise RuntimeError('DPAPI credentials require Windows')

    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, result = Blob(len(value), buffer), Blob()
    crypto = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.length)
    finally:
        kernel.LocalFree(result.data)


def relative_path(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Artifact path is invalid')
    path = PureWindowsPath(value)
    if path.drive or path.root or '..' in path.parts or ':' in value:
        raise ValueError('Artifact path must stay inside the project')
    return path


def validate_job(job):
    if not isinstance(job, dict) or job.get('type') != 'job':
        raise ValueError('Invalid job')
    if str(uuid.UUID(job['job_id'])) != job['job_id']:
        raise ValueError('Invalid job ID')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', job.get('slug', '')) or len(job['slug']) > 80:
        raise ValueError('Invalid project slug')
    if not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', job.get('repo', '')):
        raise ValueError('Invalid GitHub repository')
    if not re.fullmatch('[0-9a-f]{40}', job.get('commit', '')):
        raise ValueError('Exact commit SHA required')
    argv = job.get('argv')
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 128 or
            any(not isinstance(a, str) or '\x00' in a or len(a) > 65536 for a in argv) or not argv[0]):
        raise ValueError('Invalid command arguments')
    if type(job.get('timeout')) is not int or not 1 <= job['timeout'] <= 7200:
        raise ValueError('Invalid timeout')
    if not isinstance(job.get('artifacts'), list) or len(job['artifacts']) > 128:
        raise ValueError('Invalid artifacts')
    for artifact in job['artifacts']:
        relative_path(artifact)


def validate_actions_setup(body):
    if (set(body) != {'type', 'id', 'repo', 'project_id'} or body['type'] != 'actions_setup'
            or not isinstance(body['repo'], str)
            or not re.fullmatch(r'Havkz/[A-Za-z0-9_.-]+', body['repo'])):
        raise ValueError('Invalid Actions runner setup')
    for key in ('id', 'project_id'):
        if not isinstance(body[key], str) or str(uuid.UUID(body[key])) != body[key]:
            raise ValueError('Invalid Actions setup identity')


async def execute(argv, cwd, timeout, *, env=None):
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    process = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE, **kwargs)

    async def capture(stream):
        output = bytearray()
        truncated = False
        while block := await stream.read(65536):
            remaining = OUTPUT_LIMIT - len(output)
            output.extend(block[:remaining])
            truncated |= len(block) > remaining
        return output.decode(errors='replace'), truncated

    stdout_task = asyncio.create_task(capture(process.stdout))
    stderr_task = asyncio.create_task(capture(process.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if os.name == 'nt':
            killer = await asyncio.create_subprocess_exec('taskkill.exe', '/PID', str(process.pid), '/T', '/F',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            await killer.wait()
        else:
            import signal
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        timed_out = True
        if isinstance(exc, asyncio.CancelledError):
            await asyncio.gather(stdout_task, stderr_task)
            raise
    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    return {'stdout': stdout[0], 'stderr': stderr[0], 'exit_code': process.returncode,
            'timed_out': timed_out, 'output_truncated': stdout[1] or stderr[1], 'artifacts': []}


class Worker:
    def __init__(self, root, secret, url, *, boot_worker=False, boot_at=None):
        self.root, self.secret, self.url = Path(root), secret, url
        self.projects = self.root / 'Projects'
        self.projects.mkdir(parents=True, exist_ok=True)
        state = self.root / 'windows-worker/state'
        state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(state / 'jobs.db', isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        if self.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Worker job ledger is corrupt; refusing to execute')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, '
                        'status TEXT NOT NULL, result TEXT, updated REAL NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS power (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.boot_worker, self.boot_at = boot_worker, boot_at
        self.handoff = False
        # Never repeat an interrupted command: it could already have changed external state.
        interrupted = json.dumps({'stdout': '', 'stderr': 'Worker restarted during execution; outcome unknown. '
            'Inspect side effects before issuing a new job.', 'exit_code': -1, 'artifacts': [], 'outcome_unknown': True})
        self.db.execute("UPDATE jobs SET status='finished',result=?,updated=? WHERE status='running'",
                        (interrupted, time.time()))
        self.execution = None
        self.login_tunnel = None
        self.login_operation = None
        self.login_opened = None

    async def power_command(self, body):
        from .windows_power import observation, network_wake_since
        ident = body.get('id')
        if not isinstance(ident, str) or str(uuid.UUID(ident)) != ident:
            raise ValueError('Invalid Windows power operation')
        current = await asyncio.to_thread(observation, self.root, self.boot_at, self.boot_worker)
        row = self.db.execute('SELECT value FROM power WHERE id=?', (ident,)).fetchone()
        state = json.loads(row['value']) if row else {}
        accepted = False
        if body['type'] == 'power_claim':
            requested, previous = body.get('requested_at'), body.get('previous_boot')
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (requested, previous)):
                raise ValueError('Invalid Windows boot identity')
            accepted = bool(current and current['startup_ready'] and current['boot_worker']
                and not current['user_active'] and previous <= current['boot_at'] <= time.time()
                and time.time() - 600 <= requested <= time.time()
                and not self.handoff)
            if accepted:
                accepted = await asyncio.to_thread(network_wake_since, self.root, requested)
            if state:
                accepted = (accepted and state.get('phase') == 'owned' and state.get('requested_at') == requested
                            and state.get('previous_boot') == previous)
            else:
                state = {'phase': 'owned' if accepted else 'released', 'requested_at': requested,
                         'previous_boot': previous, 'boot_at': self.boot_at}
                self.db.execute('INSERT INTO power VALUES (?,?)', (ident, json.dumps(state)))
                self.db.execute('DELETE FROM power WHERE id NOT IN (SELECT id FROM power ORDER BY rowid DESC LIMIT 50)')
            command = 'claim'
        elif body['type'] == 'power_shutdown':
            expires = body.get('expires_at')
            ci_busy = False
            if os.name == 'nt' and (self.root / 'actions-coordination/repositories.json').exists():
                from .windows_ci import ExecutionSlot
                slot = ExecutionSlot(self.root)
                try:
                    ci_busy = slot.ci_busy()
                except (OSError, sqlite3.Error):
                    ci_busy = True  # Unknown CI ownership can never authorize shutdown.
                finally:
                    slot.db.close()
            accepted = bool(type(expires) in (int, float) and math.isfinite(expires)
                and time.time() < expires <= time.time() + 30 and current and current['boot_worker']
                and not current['user_active'] and not self.handoff and not ci_busy and state.get('phase') == 'owned'
                and state['boot_at'] == body.get('boot_at') == self.boot_at
                and not (self.execution and not self.execution.done()) and self.login_tunnel is None
                and not self.db.execute("SELECT 1 FROM jobs WHERE status IN ('running','finished')").fetchone())
            command = 'shutdown'
            if accepted:
                state['phase'] = 'shutdown_sent'
                self.db.execute('UPDATE power SET value=? WHERE id=?', (json.dumps(state), ident))
                # No /f: never force-close another application's unsaved work.
                result = await execute(['shutdown.exe', '/s', '/t', '0'], self.root, 10)
                accepted = result['exit_code'] == 0
        else:
            raise ValueError('Unknown Windows power command')
        return {'type': 'power_result', 'id': ident, 'command': command, 'accepted': accepted, 'boot_at': self.boot_at}

    async def close_login_tunnel(self):
        if self.login_tunnel and self.login_tunnel.returncode is None:
            self.login_tunnel.terminate()
            try:
                await asyncio.wait_for(self.login_tunnel.wait(), 5)
            except asyncio.TimeoutError:
                self.login_tunnel.kill()
                await self.login_tunnel.wait()
        self.login_tunnel = None

    async def open_login(self, body):
        """One owned callback tunnel. No AI, logout, saved tokens or project execution."""
        if self.boot_worker:
            raise ValueError('Browser login requires the interactive Windows worker')
        operation = body.get('operation_id')
        if not isinstance(operation, str) or str(uuid.UUID(operation)) != operation:
            raise ValueError('Invalid account login operation')
        url = codex_login_url(body.get('url'))
        expires = body.get('expires_at')
        if type(expires) not in (int, float) or not time.time() < expires <= time.time() + 900:
            raise ValueError('Account login has expired')
        self.login_expires = expires
        if self.login_operation != operation:
            await self.close_login_tunnel()
        if self.login_tunnel is None or self.login_tunnel.returncode is not None:
            self.login_tunnel = await asyncio.create_subprocess_exec('ssh', '-N',
                '-L', '127.0.0.1:1455:127.0.0.1:1455', '-o', 'BatchMode=yes',
                '-o', 'ConnectTimeout=8', '-o', 'ExitOnForwardFailure=yes',
                '-o', 'ServerAliveInterval=30', 'raspberry@192.168.2.105',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            self.login_operation = operation
            deadline = time.monotonic() + 10
            while True:
                await asyncio.sleep(.1)
                if self.login_tunnel.returncode is not None:
                    raise ValueError('The Codex login callback tunnel could not open; check local port 1455 and SSH')
                try:
                    _, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 1455), 1)
                    writer.close()
                    await writer.wait_closed()
                    break
                except (OSError, asyncio.TimeoutError):
                    if time.monotonic() >= deadline:
                        await self.close_login_tunnel()
                        raise ValueError('The Codex login callback tunnel did not become ready') from None
        if self.login_opened != operation:
            if not await asyncio.to_thread(webbrowser.open, url):
                await self.close_login_tunnel()
                raise ValueError('The Windows default browser could not open the Codex login')
            self.login_opened = operation

    def clean(self, text, project=None):
        text = text.replace(self.secret, '[REDACTED]')
        if project:
            for value in read_env(project / '.env').values():
                if value:
                    text = text.replace(value, '[REDACTED]')
        return re.sub(r'(?i)(?:gh[pousr]_[a-z0-9_]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9_-]{20,})',
                      '[REDACTED]', text)

    def result_message(self, row):
        payload = json.loads(row['payload'])
        body = {'type': 'result', 'job_id': row['id'], 'result': json.loads(row['result'])}
        if payload['type'] == 'actions_setup':
            body.update(type='actions_setup_result', repo=payload['repo'])
        return body

    async def setup_actions(self, body):
        try:
            result = await execute([sys.executable, str(self.root / 'Setup/install-actions-runner.py'),
                '--activate', '--project-id', body['project_id'], body['repo']], self.root, 600)
        except Exception as exc:
            result = {'stdout': '', 'stderr': str(exc), 'exit_code': -1, 'artifacts': []}
        self.db.execute("UPDATE jobs SET status='finished',result=?,updated=? WHERE id=?",
                        (self.clean(json.dumps(result)), time.time(), body['id']))

    def accept_actions_setup(self, body):
        validate_actions_setup(body)
        existing = self.db.execute('SELECT * FROM jobs WHERE id=?', (body['id'],)).fetchone()
        payload = json.dumps(body, sort_keys=True)
        if existing:
            if existing['payload'] != payload:
                raise ValueError('Actions setup ID was reused for a different repository')
            return self.result_message(existing) if existing['result'] else None
        if self.handoff or self.execution and not self.execution.done():
            raise ValueError('Windows worker is busy or draining; reconnect before Actions setup')
        self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                        (body['id'], payload, 'running', None, time.time()))
        self.execution = asyncio.create_task(self.setup_actions(body))
        return None

    async def run_job(self, job):
        if os.name != 'nt' or not (self.root / 'actions-coordination/repositories.json').exists():
            return await self._run_job(job)
        from .windows_ci import ExecutionSlot, identity
        slot = ExecutionSlot(self.root)
        pid, born = os.getpid(), identity(os.getpid())
        try:
            deadline = time.monotonic() + 900
            while not slot.claim(pid, born, 'worker'):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Windows work waited 15 minutes behind GitHub Actions')
                await asyncio.sleep(1)
            await self._run_job(job)
        except Exception as exc:
            result = {'stdout': '', 'stderr': self.clean(str(exc)), 'exit_code': -1, 'artifacts': []}
            self.db.execute("UPDATE jobs SET status='finished',result=?,updated=? WHERE id=?",
                            (json.dumps(result), time.time(), job['job_id']))
        finally:
            slot.release(pid, born)
            slot.db.close()

    async def _run_job(self, job):
        path = self.projects / job['slug']
        checkout_status = ''
        try:
            if path.resolve().parent != self.projects.resolve() or path.is_symlink():
                raise ValueError('Checkout path escapes the project root')
            expected = 'https://github.com/' + job['repo'] + '.git'

            async def checked(*args, cwd=path):
                # Use the already authenticated user-owned gh keyring, not GCM's
                # interactive credential storage. These overrides affect only this child.
                args = [args[0], '-c', 'credential.helper=', '-c',
                        'credential.helper=!gh auth git-credential', *args[1:]]
                result = await execute(args, cwd, 180, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
                if result['exit_code'] or result['timed_out']:
                    raise RuntimeError(Path(args[0]).name + ': ' + result['stderr'][-3000:])
                return result['stdout'].strip()

            if not path.exists():
                await checked('git', 'clone', '--no-checkout', expected, str(path), cwd=self.projects)
            if not (path / '.git').is_dir():
                raise ValueError('Existing directory is not a managed repository checkout')
            origin = await checked('git', 'remote', 'get-url', 'origin')
            if origin != expected:
                raise ValueError('Existing repository origin does not match the requested project')
            # A new --no-checkout clone has no HEAD files yet. Only skip this guard for that exact state.
            initialized = (path / '.git/codexpi-checkout').exists()
            if not initialized and await checked('git', 'ls-files'):
                raise ValueError('Existing checkout has no CodexPi ownership marker; preserving it')
            diagnostic = initialized and not job['artifacts'] and job['argv'] in (
                ['git', 'status', '--short'],
                ['git', 'status', '--porcelain=v1', '--untracked-files=all'])
            if initialized:
                checkout_status = await checked('git', 'status', '--porcelain=v1', '--untracked-files=all')
                if diagnostic:
                    # Exact read-only argv, not a caller's "diagnostic" label. Do
                    # not change the checkout just to inspect local changes.
                    if await checked('git', 'rev-parse', 'HEAD') != job['commit']:
                        raise ValueError('Diagnostic requires the current checkout SHA; no checkout performed')
                elif checkout_status and await checked('git', 'status', '--porcelain=v1', '--untracked-files=no'):
                    raise ValueError('Windows checkout contains tracked local changes; preserving them')
            if not diagnostic:
                await checked('git', 'fetch', '--no-tags', 'origin', job['commit'])
                # Git itself refuses untracked-file collisions. Never force,
                # clean, stash or delete unrelated runtime/user files.
                await checked('git', 'checkout', '--detach', '--no-overwrite-ignore', job['commit'])
            actual = await checked('git', 'rev-parse', 'HEAD')
            if actual != job['commit']:
                raise RuntimeError('Checkout SHA verification failed')
            atomic_write(path / '.git/codexpi-checkout', job['repo'])
            result = await execute(job['argv'], path, job['timeout'])
            result['commit'] = actual
            result['cwd'] = str(path)
            result['elevated'] = bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == 'nt' else False
            for value in job['artifacts']:
                artifact = path.joinpath(*relative_path(value).parts).resolve()
                if not artifact.is_relative_to(path.resolve()):
                    raise ValueError('Artifact resolves outside the checkout')
                if not artifact.exists():
                    raise ValueError('Requested artifact was not produced: ' + value)
                result['artifacts'].append(str(artifact))
        except Exception as exc:
            result = {'stdout': '', 'stderr': str(exc), 'exit_code': -1, 'artifacts': []}
            if checkout_status:
                result['stderr'] += '\nCheckout changes:\n' + checkout_status[:8000]
        if checkout_status:
            result['checkout_status'] = checkout_status[:8000]
            result['checkout_status_truncated'] = len(checkout_status) > 8000
        result = self.clean(json.dumps(result), path)
        self.db.execute("UPDATE jobs SET status='finished',result=?,updated=? WHERE id=?",
                        (result, time.time(), job['job_id']))

    async def connect(self):
        async with ClientSession(timeout=ClientTimeout(total=None, sock_connect=10)) as client:
            async with client.ws_connect(self.url, max_msg_size=12 * 1024 * 1024) as socket:
                hello = await asyncio.wait_for(socket.receive_json(), 10)
                channel = SignedChannel(self.secret, hello['challenge'], 'worker')
                send_lock = asyncio.Lock()

                async def send(body):
                    async with send_lock:
                        await socket.send_json(channel.sign(body))

                await send({'type': 'hello'})
                accepted = channel.verify(await asyncio.wait_for(socket.receive_json(), 10))
                if accepted != {'type': 'accepted'}:
                    raise ValueError('Controller handshake rejected')
                inventory = {'type': 'inventory', 'jobs': [], 'actions_setups': []}
                for row in self.db.execute("SELECT * FROM jobs WHERE status!='delivered'"):
                    if json.loads(row['payload'])['type'] == 'actions_setup':
                        inventory['actions_setups'].append(row['id'])
                    else:
                        inventory['jobs'].append({'job_id': row['id'], 'status': row['status']})
                await send(inventory)

                async def heartbeat():
                    while True:
                        if self.login_tunnel and time.time() >= getattr(self, 'login_expires', 0):
                            await self.close_login_tunnel()
                        from .windows_power import observation, desktop_in_use
                        try:
                            power = await asyncio.to_thread(observation, self.root, self.boot_at, self.boot_worker)
                        except (ValueError, KeyError, OSError):
                            logging.warning('Windows power telemetry unavailable; automatic shutdown is disabled')
                            power = None
                        if self.boot_worker and await asyncio.to_thread(desktop_in_use):
                            self.handoff = True
                        await send({'type': 'alive', **({'power': power} if power else {}),
                                    **({'draining': True} if self.handoff else {})})
                        if (self.handoff and not (self.execution and not self.execution.done())
                                and not self.db.execute("SELECT 1 FROM jobs WHERE status IN ('running','finished')").fetchone()):
                            return  # The existing interactive login task takes over after releasing the lock.
                        await asyncio.sleep(20)

                async def results():
                    sent = set()
                    while True:
                        for row in self.db.execute("SELECT * FROM jobs WHERE status='finished'"):
                            if row['id'] not in sent:
                                await send(self.result_message(row))
                                sent.add(row['id'])
                        await asyncio.sleep(1)

                async def receive():
                    async for packet in socket:
                        if packet.type != WSMsgType.TEXT:
                            continue
                        body = channel.verify(json.loads(packet.data))
                        if body.get('type') == 'account_login':
                            try:
                                await self.open_login(body)
                                self.login_expires = body['expires_at']
                                await send({'type': 'account_login_result', 'operation_id': body['operation_id'], 'opened': True})
                            except (ValueError, OSError):
                                await self.close_login_tunnel()
                                await send({'type': 'account_login_result', 'operation_id': body.get('operation_id'),
                                            'opened': False})
                        elif body.get('type') == 'account_login_close':
                            if body.get('operation_id') == self.login_operation:
                                await self.close_login_tunnel()
                        elif body.get('type') in ('power_claim', 'power_shutdown'):
                            await send(await self.power_command(body))
                        elif body.get('type') == 'ack':
                            self.db.execute("UPDATE jobs SET status='delivered',updated=? WHERE id=? AND status='finished'",
                                            (time.time(), body['job_id']))
                        elif body.get('type') == 'actions_setup':
                            result = self.accept_actions_setup(body)
                            if result:
                                await send(result)
                        elif body.get('type') == 'job':
                            validate_job(body)
                            existing = self.db.execute('SELECT * FROM jobs WHERE id=?', (body['job_id'],)).fetchone()
                            payload = json.dumps(body, sort_keys=True)
                            if existing:
                                if existing['payload'] != payload:
                                    raise ValueError('Job ID was reused for a different command')
                                if existing['result']:
                                    await send({'type': 'result', 'job_id': body['job_id'], 'result': json.loads(existing['result'])})
                                else:
                                    await send({'type': 'started', 'job_id': body['job_id']})
                                continue
                            if self.handoff:
                                raise ValueError('Boot worker is draining for interactive handoff; reconnect before dispatch')
                            if self.execution and not self.execution.done():
                                raise ValueError('Controller tried to run concurrent Windows jobs')
                            self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                                            (body['job_id'], payload, 'running', None, time.time()))
                            self.execution = asyncio.create_task(self.run_job(body))
                            await send({'type': 'started', 'job_id': body['job_id']})
                        else:
                            raise ValueError('Unknown controller message')

                tasks = [asyncio.create_task(f()) for f in (heartbeat, results, receive)]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await self.close_login_tunnel()

    async def run(self):
        delay = 1
        while True:
            started = time.monotonic()
            try:
                await self.connect()
                if self.handoff:
                    return
            except (OSError, ValueError, KeyError, asyncio.TimeoutError) as exc:
                logging.warning('Worker connection ended: %s', self.clean(str(exc)))
            except Exception as exc:
                logging.error('Worker connection error: %s', self.clean(str(exc)))
            if time.monotonic() - started > 60:
                delay = 1
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 2, 30)


def main():
    import argparse
    import msvcrt
    from .windows_power import boot_time
    parser = argparse.ArgumentParser()
    parser.add_argument('--boot', action='store_true')
    args = parser.parse_args()
    logs = ROOT / 'windows-worker/logs'
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / 'worker.log', maxBytes=2 * 1024 * 1024, backupCount=5)
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Worker starting in %s context', 'boot' if args.boot else 'interactive')
    state = ROOT / 'windows-worker/state'
    state.mkdir(parents=True, exist_ok=True)
    lock = (state / 'worker.lock').open('a+b')
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        from .windows_power import desktop_in_use
        if args.boot and exc.errno == errno.EACCES and desktop_in_use():
            lock.close()
            logging.info('Boot worker skipped: a worker already owns the ledger and a desktop user is logged in')
            return
        raise
    logging.info('Worker ledger lock acquired')
    config = json.loads((ROOT / 'windows-worker/config.json').read_text())
    secret = protect_secret(base64.b64decode(config['secret_dpapi']), decrypt=True).decode()
    logging.info('Worker credential loaded')
    try:
        boot_at = boot_time()
    except (OSError, ValueError, subprocess.SubprocessError):
        logging.warning('Windows boot identity unavailable; automatic shutdown is disabled')
        boot_at = None
    worker = Worker(ROOT, secret, config['url'], boot_worker=args.boot, boot_at=boot_at)
    try:
        asyncio.run(worker.run())
    finally:
        try:
            worker.db.close()
        finally:
            lock.close()
    if args.boot and worker.handoff:
        # The logon task may already have lost the race for the boot worker's lock.
        result = subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/schtasks.exe'),
                                 '/Run', '/TN', 'CodexPi Windows Worker'],
                                capture_output=True, timeout=10,
                                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        if result.returncode:
            raise RuntimeError('Windows worker handoff could not start the existing login task')
        logging.info('Boot worker released the ledger and requested the login task')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logging.error('Worker initialization failed (%s, Windows error %s)', type(exc).__name__, getattr(exc, 'winerror', None))
        raise
