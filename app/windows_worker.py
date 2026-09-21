"""Outbound-only native Windows executor. This process never starts an AI agent."""
import asyncio
import base64
import contextlib
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path, PureWindowsPath
import random
import re
import sqlite3
import subprocess
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, WSMsgType

from .common import SignedChannel, atomic_write, read_env

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
    def __init__(self, root, secret, url):
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
        # Never repeat an interrupted command: it could already have changed external state.
        interrupted = json.dumps({'stdout': '', 'stderr': 'Worker restarted during execution; outcome unknown. '
            'Inspect side effects before issuing a new job.', 'exit_code': -1, 'artifacts': [], 'outcome_unknown': True})
        self.db.execute("UPDATE jobs SET status='finished',result=?,updated=? WHERE status='running'",
                        (interrupted, time.time()))
        self.execution = None

    def clean(self, text, project=None):
        text = text.replace(self.secret, '[REDACTED]')
        if project:
            for value in read_env(project / '.env').values():
                if value:
                    text = text.replace(value, '[REDACTED]')
        return re.sub(r'(?i)(?:gh[pousr]_[a-z0-9_]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9_-]{20,})',
                      '[REDACTED]', text)

    async def run_job(self, job):
        path = self.projects / job['slug']
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
            if initialized and await checked('git', 'status', '--porcelain'):
                raise ValueError('Windows checkout contains local changes; preserving them')
            if not initialized and await checked('git', 'ls-files'):
                raise ValueError('Existing checkout has no CodexPi ownership marker; preserving it')
            await checked('git', 'fetch', '--no-tags', 'origin', job['commit'])
            await checked('git', 'checkout', '--detach', job['commit'])
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
                await send({'type': 'inventory', 'jobs': [dict(row) for row in self.db.execute(
                    "SELECT id AS job_id,status FROM jobs WHERE status!='delivered'")]})

                async def heartbeat():
                    while True:
                        await send({'type': 'alive'})
                        await asyncio.sleep(20)

                async def results():
                    sent = set()
                    while True:
                        for row in self.db.execute("SELECT * FROM jobs WHERE status='finished'"):
                            if row['id'] not in sent:
                                await send({'type': 'result', 'job_id': row['id'], 'result': json.loads(row['result'])})
                                sent.add(row['id'])
                        await asyncio.sleep(1)

                async def receive():
                    async for packet in socket:
                        if packet.type != WSMsgType.TEXT:
                            continue
                        body = channel.verify(json.loads(packet.data))
                        if body.get('type') == 'ack':
                            self.db.execute("UPDATE jobs SET status='delivered',updated=? WHERE id=? AND status='finished'",
                                            (time.time(), body['job_id']))
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

    async def run(self):
        delay = 1
        while True:
            started = time.monotonic()
            try:
                await self.connect()
            except (OSError, ValueError, KeyError, asyncio.TimeoutError) as exc:
                logging.warning('Worker connection ended: %s', self.clean(str(exc)))
            except Exception as exc:
                logging.error('Worker connection error: %s', self.clean(str(exc)))
            if time.monotonic() - started > 60:
                delay = 1
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 2, 30)


def main():
    import msvcrt
    state = ROOT / 'windows-worker/state'
    state.mkdir(parents=True, exist_ok=True)
    lock = (state / 'worker.lock').open('a+b')
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    config = json.loads((ROOT / 'windows-worker/config.json').read_text())
    secret = protect_secret(base64.b64decode(config['secret_dpapi']), decrypt=True).decode()
    logs = ROOT / 'windows-worker/logs'
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / 'worker.log', maxBytes=2 * 1024 * 1024, backupCount=5)
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    worker = Worker(ROOT, secret, config['url'])
    asyncio.run(worker.run())


if __name__ == '__main__':
    main()
