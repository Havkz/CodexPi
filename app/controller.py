import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import re
import shlex
import signal
import time
import uuid

from .common import NATIVE_STATUS, Redactor, atomic_write, slugify
from .db import Database
from .native import GoalSource, Native, project_thread_config


async def command(*args, cwd=None, timeout=90, check=True):
    process = await asyncio.create_subprocess_exec(*map(str, args), cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=(os.name == 'posix'))
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
        raise
    result = {'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace'),
              'exit_code': process.returncode}
    if check and process.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed: {result["stderr"][-1500:]}')
    return result


class Controller:
    def __init__(self, root, config):
        self.root = Path(root)
        self.config = config
        self.db = Database(self.root / 'state/codexpi.db')
        self.redactor = Redactor(self.root)
        self.lock = asyncio.Lock()
        self.native = None
        self.source = GoalSource(self.root)
        self.bot = None
        self.worker = None
        self.worker_seen = 0
        self.worker_key = None
        self.worker_send_lock = asyncio.Lock()
        self.last_backup = 0
        self.last_git_poll = 0
        self.last_unsnooze_poll = 0
        self.last_idle_cleanup = 0
        self.unsnooze = {}
        self.health_errors = {}
        self.tui_connections = {}
        self.task = None

    @property
    def windows_online(self):
        return bool(self.worker is not None and not self.worker.closed and
                    time.monotonic() - self.worker_seen < 60)

    async def start(self):
        self.native = await Native(self.root / 'state/native.sock').connect()
        async with self.lock:
            await self.recover()
        self.task = asyncio.create_task(self.scheduler())

    def select(self, project_id):
        with self.db.transaction():
            ordered = [p['project_id'] for p in self.db.all() if p['queue_position'] is not None]
            ordered = [project_id] + [i for i in ordered if i != project_id]
            for position, ident in enumerate(ordered, 1):
                self.db.update(ident, queue_position=position)
            self.db.set_setting('selected', project_id)

    def record_goal(self, project, goal):
        status = NATIVE_STATUS[goal['status']]
        self.db.update(project['project_id'], goal_status=status, last_activity=time.time())
        if status != project['goal_status'] and status in ('stalled', 'usage limited', 'limited by budget'):
            self.db.event(project['project_id'], status, {'reason': project['block_reason']})
        if status == 'active':
            self.db.update(project['project_id'], operation=None)
            if project['goal_status'] != 'active':
                self.clear_block(project)
        if status == 'paused' and self.db.setting('selected') == project['project_id']:
            self.db.set_setting('selected', None)

    def clear_block(self, project):
        (Path(project['project_path']) / '.codexpi/block.json').unlink(missing_ok=True)
        self.db.update(project['project_id'], block_reason=None, windows_required=0, operation=None)

    async def create(self, name):
        name = name.strip()
        slug = slugify(name)
        async with self.lock:
            existing = self.db.conn.execute('SELECT * FROM projects WHERE display_name=?', (name,)).fetchone()
            if existing:
                project = dict(existing)
                if project['lifecycle'] == 'ready':
                    await self.attach_ready(project)
                    return project
                if project['lifecycle'] != 'creating':
                    raise ValueError('Project lifecycle recovery is still in progress')
            else:
                if self.db.conn.execute('SELECT 1 FROM projects WHERE slug=?', (slug,)).fetchone():
                    raise ValueError('That name normalizes to an existing project slug')
                path = self.root / 'projects' / slug
                if path.exists():
                    raise ValueError('Project directory already exists without a CodexPi mapping')
                ident = str(uuid.uuid4())
                with self.db.transaction():
                    self.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,
                        project_path,tmux_session_name,queue_position,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?)''', (ident, name, slug, str(path), 'codexpi-' + slug,
                        max([p['queue_position'] or 0 for p in self.db.all()] + [0]) + 1,
                        time.time(), time.time()))
                project = self.db.get(ident)
            try:
                await self.finish_creation(project)
                project = self.db.get(project['project_id'])
                await self.attach_ready(project)
                return project
            except Exception as exc:
                self.db.update(project['project_id'], operation=json.dumps(
                    {'kind': 'create', 'error': self.redactor.clean(str(exc))}))
                raise

    async def finish_creation(self, project):
        if self.bot is None or not self.bot.is_ready():
            raise RuntimeError('Discord bot is not connected; project creation will retry when reopened')
        path = Path(project['project_path'])
        path.mkdir(parents=True, exist_ok=True)
        marker = path / '.codexpi/project-id'
        if marker.exists() and marker.read_text() != project['project_id']:
            raise RuntimeError('Project ownership marker does not match')
        atomic_write(marker, project['project_id'])
        if not (path / '.env').exists():
            atomic_write(path / '.env', '')
        os.chmod(path / '.env', 0o600)
        if not (path / '.git').exists():
            await command('git', 'init', '-b', 'main', cwd=path)
            await command('git', 'config', 'user.name', self.config['github_account'], cwd=path)
            await command('git', 'config', 'user.email', self.config['github_email'], cwd=path)
            atomic_write(path / '.gitignore', '.env\n.env.*\n!.env.example\n.codexpi/\n__pycache__/\n.venv/\nnode_modules/\n', 0o644)
            atomic_write(path / 'README.md', '# ' + project['display_name'] + '\n\nManaged by CodexPi.\n', 0o644)
            atomic_write(path / 'AGENTS.md', (self.root / 'templates/AGENTS.md').read_text(), 0o644)
            await command('git', 'add', 'README.md', 'AGENTS.md', '.gitignore', cwd=path)
            await command('git', 'commit', '-m', 'Initialize private CodexPi project', cwd=path)
        repo = project['github_repo'] or self.config['github_account'] + '/' + project['slug']
        description = 'Managed by CodexPi project ' + project['project_id']
        check = await command('gh', 'repo', 'view', repo, '--json', 'visibility,description', check=False)
        if check['exit_code'] == 0:
            data = json.loads(check['stdout'])
            if data['visibility'] != 'PRIVATE' or data['description'] != description:
                raise ValueError('GitHub repository already exists without the matching private project identity')
        else:
            await command('gh', 'repo', 'create', repo, '--private', '--description', description)
        self.db.update(project['project_id'], github_repo=repo)
        origins = await command('git', 'remote', cwd=path)
        if 'origin' not in origins['stdout'].splitlines():
            await command('git', 'remote', 'add', 'origin', 'https://github.com/' + repo + '.git', cwd=path)
        else:
            origin = await command('git', 'remote', 'get-url', 'origin', cwd=path)
            if origin['stdout'].strip() != 'https://github.com/' + repo + '.git':
                raise RuntimeError('Existing Git origin does not match CodexPi project')
        await command('git', 'push', '-u', 'origin', 'main', cwd=path, timeout=180)
        channel = await self.bot.ensure_channel(project)
        self.db.update(project['project_id'], discord_channel_id=str(channel.id))
        if not project['codex_session_id']:
            result = await self.native.rpc('thread/start', {'cwd': str(path), 'ephemeral': False,
                'approvalPolicy': 'never', 'sandbox': 'workspace-write',
                'config': project_thread_config(path)})
            session = result['thread']['id']
            self.db.update(project['project_id'], codex_session_id=session)
            # Native threads are lazy: persist infrastructure context without starting a model turn
            # or fabricating a user goal, so the first TUI can actually resume after unloading.
            await self.native.rpc('thread/inject_items', {'threadId': session, 'items': [{
                'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text',
                'text': 'CodexPi initialized this project session. Wait for the user to provide /goal; no goal has been supplied yet.'}]}]})
        else:
            session = project['codex_session_id']
        await self.native.rpc('thread/name/set', {'threadId': session, 'name': project['display_name']})
        await self.native.rpc('thread/unsubscribe', {'threadId': session})
        commit = (await command('git', 'rev-parse', 'HEAD', cwd=path))['stdout'].strip()
        self.db.update(project['project_id'], lifecycle='ready', operation=None, last_commit=commit)

    async def pane_exists(self, project):
        result = await command('tmux', 'display-message', '-p', '-t', project['tmux_session_name'] + ':0.0',
                               '#{pane_dead}', check=False)
        return result['exit_code'] == 0 and result['stdout'].strip() == '0'

    async def attach_ready(self, project):
        if project['lifecycle'] != 'ready':
            raise ValueError('Project lifecycle recovery must finish before attaching')
        if await self.pane_exists(project):
            return
        args = ['env', 'UNSNOOZE_AUTO_RESUME=false', '/home/raspberry/.local/bin/unsnooze', '_run', 'codex',
                '--remote', 'unix://' + str(self.root / 'state/tui.sock'),
                '--no-alt-screen', 'resume', project['codex_session_id']]
        dead = await command('tmux', 'has-session', '-t', '=' + project['tmux_session_name'], check=False)
        if dead['exit_code'] == 0:
            await command('tmux', 'respawn-pane', '-t', project['tmux_session_name'] + ':0.0',
                          '-c', project['project_path'], shlex.join(args))
        else:
            await command('tmux', 'new-session', '-d', '-s', project['tmux_session_name'],
                          '-c', project['project_path'], '-x', '120', '-y', '36', shlex.join(args))
        await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'status', 'off')
        await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'remain-on-exit', 'on')

    async def slash(self, project, text):
        if not await self.pane_exists(project):
            raise RuntimeError('Codex TUI pane is unavailable')
        await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', '-l', text)
        # Codex coalesces fast keystrokes into paste bursts; submit after that burst closes.
        await asyncio.sleep(0.25)
        await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', 'Enter')

    async def pause(self, project, release=True, preserve_operation=False):
        goal = await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})
        if goal.get('goal') and goal['goal']['status'] != 'complete':
            await self.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'paused'})
            self.db.update(project['project_id'], goal_status='paused')
        # Pausing a native goal stops continuation, not its already-running turn.
        # Interrupt that turn and confirm native idleness before releasing the single-worker slot.
        await self.wait_idle(project)
        if not preserve_operation:
            self.db.update(project['project_id'], operation=None)
        if release and self.db.setting('selected') == project['project_id']:
            self.db.set_setting('selected', None)
        await self.cancel_wakes(project)

    async def wait_idle(self, project):
        deadline = time.monotonic() + 30
        while True:
            thread = (await self.native.rpc('thread/read', {
                'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
            if thread['status']['type'] in ('idle', 'notLoaded'):
                return
            if thread['status']['type'] != 'active':
                raise RuntimeError('Cannot confirm native worker idleness')
            turns = await self.native.rpc('thread/turns/list', {
                'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc'})
            for turn in turns['data']:
                if turn['status'] == 'inProgress':
                    await self.native.rpc('turn/interrupt', {'threadId': project['codex_session_id'], 'turnId': turn['id']})
            if time.monotonic() >= deadline:
                raise RuntimeError('Native turn did not stop; another project was not started')
            await asyncio.sleep(0.2)

    async def run_now(self, project_id):
        async with self.lock:
            project = self.db.get(project_id)
            if project['lifecycle'] != 'ready':
                raise ValueError('Project lifecycle recovery must finish before resuming')
            if project['goal_status'] == 'complete':
                raise ValueError('Completed goals are never automatically restarted')
            selected = self.db.setting('selected')
            if selected and selected != project_id:
                await self.pause(self.db.get(selected))
            self.db.set_setting('pause_all', False)
            self.select(project_id)
            await self.attach_ready(project)
            # Readiness is supplied by the native TUI's successful resume RPC, not a screen guess.
            self.db.update(project_id, operation=json.dumps({'kind': 'resume', 'requested_at': time.time()}))

    async def cancel_wakes(self, project):
        for item in self.unsnooze.get('sessions', []):
            if item.get('sessionId') == project['codex_session_id'] and item['status'] not in ('cancelled', 'resumed'):
                await command('unsnooze', 'cancel', item['key'], check=False)

    async def recover(self):
        from .lifecycle import recover
        await recover(self)
        rows = self.source.rows()
        selected = self.db.setting('selected')
        if self.db.setting('pause_all', False):
            selected = None
        # Reconcile nonselected native activity first; never violate the one-active DB constraint.
        for project in self.db.all():
            if project['lifecycle'] != 'ready':
                continue
            row = rows.get(project['codex_session_id'])
            if row and row['status'] == 'active' and project['project_id'] != selected:
                await self.pause(project, release=False)
                row['status'] = 'paused'
        for project in self.db.all():
            if project['lifecycle'] != 'ready':
                continue
            row = rows.get(project['codex_session_id'])
            if row:
                self.db.update(project['project_id'], goal_status=row['status'])
        selected = self.db.setting('selected')
        if selected and not self.db.setting('pause_all', False):
            project = self.db.get(selected)
            if project['lifecycle'] != 'ready':
                logging.getLogger('recovery').warning('Lifecycle journal retains selected project until quiescent')
            elif project['goal_status'] == 'active':
                await self.attach_ready(project)
                self.db.update(selected, operation=json.dumps({'kind': 'resume', 'requested_at': time.time()}))
            elif project['goal_status'] == 'usage limited':
                await self.attach_ready(project)
        logging.getLogger('recovery').info('SQLite and native goals reconciled')

    async def poll_goals(self):
        rows = self.source.rows()
        for project in self.db.all():
            if project['lifecycle'] != 'ready':
                continue
            row = rows.get(project['codex_session_id'])
            if not row:
                continue
            status = row['status']
            old = project['goal_status']
            if status == 'active' and self.db.setting('selected') != project['project_id']:
                await self.pause(project, release=False)
                self.db.event(project['project_id'], 'critical', {'message': 'Unselected native goal was paused'})
                continue
            block = Path(project['project_path']) / '.codexpi/block.json'
            reason = project['block_reason']
            if block.exists():
                value = json.loads(block.read_text())
                if not isinstance(value, dict) or not isinstance(value.get('reason'), str):
                    raise ValueError('Invalid block reason file')
                reason = self.redactor.clean(json.dumps({k: value[k] for k in
                    ('reason', 'details', 'requires_user') if k in value}))
            if status == 'complete':
                if old != 'complete' or not project['completion_notified']:
                    await self.complete(project)
                elif reason or block.exists() or project['windows_required']:
                    self.clear_block(project)
                continue
            self.db.update(project['project_id'], goal_status=status, block_reason=reason,
                           last_activity=row.get('updated_at_ms', 0) / (1000 if row.get('updated_at_ms', 0) > 1e12 else 1))
            if status != old and status in ('stalled', 'usage limited', 'limited by budget'):
                self.db.event(project['project_id'], status, {'reason': reason})
            operation = json.loads(project['operation'] or '{}')
            if (status == 'paused' and self.db.setting('selected') == project['project_id']
                    and operation.get('kind') != 'resume'):
                await self.wait_idle(project)
                self.db.set_setting('selected', None)
            if status == 'active' and old != 'active':
                self.clear_block(project)

    async def complete(self, project):
        path = Path(project['project_path'])
        dirty = await command('git', 'status', '--porcelain', cwd=path)
        if dirty['stdout'].strip():
            await self.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'blocked'})
            self.db.update(project['project_id'], goal_status='stalled', block_reason=json.dumps(
                {'reason': 'Completion verification failed', 'details': 'Working tree is not committed', 'requires_user': False}))
            self.db.event(project['project_id'], 'critical', {'message': 'Completion rejected: working tree is not committed'})
            return
        await command('git', 'push', 'origin', 'HEAD', cwd=path, timeout=180)
        await self.refresh_git(project)
        project = self.db.get(project['project_id'])
        if project['last_ci_status'] in ('failure', 'pending'):
            if project['last_ci_status'] == 'failure':
                self.db.event(project['project_id'], 'critical', {'message': 'Final CI failed'})
            return
        self.clear_block(project)
        with self.db.transaction():
            self.db.update(project['project_id'], goal_status='complete', queue_position=None,
                           completion_notified=1, operation=None)
            self.db.event(project['project_id'], 'complete', {'repo': project['github_repo'],
                          'commit': project['last_commit'], 'ci': project['last_ci_status']})
            if self.db.setting('selected') == project['project_id']:
                self.db.set_setting('selected', None)
                self.db.set_setting('advance_queue', True)
        await self.cancel_wakes(project)

    async def refresh_git(self, project):
        if project['lifecycle'] != 'ready':
            return
        commit = (await command('git', 'rev-parse', 'HEAD', cwd=project['project_path']))['stdout'].strip()
        runs = await command('gh', 'run', 'list', '--repo', project['github_repo'], '--commit', commit,
                             '--json', 'status,conclusion,url', '--limit', '50')
        data = json.loads(runs['stdout'])
        state = 'not configured' if not data else 'passed'
        if any(r['status'] != 'completed' for r in data):
            state = 'pending'
        if any(r['conclusion'] not in ('', None, 'success', 'skipped', 'neutral') for r in data):
            state = 'failure'
        self.db.update(project['project_id'], last_commit=commit, last_ci_status=state)
        if state == 'failure' and project['last_ci_status'] != 'failure':
            self.db.event(project['project_id'], 'critical', {'message': 'GitHub Actions failed', 'commit': commit})

    async def scheduler(self):
        while True:
            try:
                async with self.lock:
                    if self.native.ws is None or self.native.ws.closed:
                        await self.native.close()
                        self.native = await Native(self.root / 'state/native.sock').connect()
                        await self.recover()
                    from .lifecycle import recover
                    await recover(self)
                    await self.poll_goals()
                    if time.monotonic() - self.last_backup > 3600:
                        self.db.backup(self.root / 'backups/sqlite')
                        self.last_backup = time.monotonic()
                    selected = self.db.setting('selected')
                    if not selected and self.db.setting('advance_queue', False) and not self.db.setting('pause_all', False):
                        self.db.set_setting('advance_queue', False)
                        next_project = next((p for p in self.db.all() if p['lifecycle'] == 'ready' and p['queue_position'] is not None and
                                             p['goal_status'] == 'paused' and p['codex_session_id'] in self.source.rows()), None)
                        if next_project:
                            self.select(next_project['project_id'])
                            await self.attach_ready(next_project)
                            self.db.update(next_project['project_id'], operation=json.dumps({'kind': 'resume', 'requested_at': time.time()}))
                    await self.resume_ready()
                    await self.selective_wake()
                    await self.release_idle_tuis()
                if time.monotonic() - self.last_git_poll > 120:
                    try:
                        for project in self.db.all():
                            await self.refresh_git(project)
                    except Exception as exc:
                        self.health_errors['github'] = self.redactor.clean(str(exc))
                        raise
                    self.health_errors.pop('github', None)
                    self.last_git_poll = time.monotonic()
                if self.bot and self.bot.is_ready():
                    await self.bot.send_pending()
                self.health_errors.pop('scheduler', None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.health_errors['scheduler'] = self.redactor.clean(str(exc))
                logging.getLogger('scheduler').error('%s', self.redactor.clean(str(exc)))
            await asyncio.sleep(2)

    async def resume_ready(self):
        if self.db.setting('pause_all', False):
            return
        for project in self.db.all():
            operation = json.loads(project['operation']) if project['operation'] else {}
            if (project['lifecycle'] != 'ready' or operation.get('kind') != 'resume'
                    or self.db.setting('selected') != project['project_id']):
                continue
            if operation.get('source') == 'unsnooze':
                if project['queue_position'] != 1:
                    self.db.update(project['project_id'], operation=None)
                    continue
                # Consume the detector record only after journaling the wake. The normal
                # mapped TUI path survives a missing pane/reboot without an argv prompt.
                await self.cancel_wakes(project)
            connections = self.tui_connections.get(project['project_id'], {})
            if not connections or time.monotonic() - min(connections.values()) < 1:
                await self.attach_ready(project)
                continue
            if operation.get('sent_at'):
                if time.time() - operation['sent_at'] > 30:
                    raise RuntimeError('TUI did not acknowledge /goal resume; manual inspection required')
                continue
            await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', 'Escape')
            await self.slash(project, '/goal resume')
            self.db.update(project['project_id'], operation=json.dumps({**operation, 'sent_at': time.time()}))

    async def release_idle_tuis(self):
        if time.monotonic() - self.last_idle_cleanup < 10:
            return
        self.last_idle_cleanup = time.monotonic()
        goals = self.source.rows()
        for project in self.db.all():
            if (project['lifecycle'] != 'ready' or project['operation'] or
                    project['goal_status'] not in ('paused', 'stalled', 'limited by budget', 'complete') or
                    project['codex_session_id'] not in goals):
                continue
            # Keep an attached user's TUI and a new, not-yet-submitted goal intact.
            attached = await command('tmux', 'display-message', '-p', '-t',
                project['tmux_session_name'] + ':0.0', '#{session_attached}', check=False)
            if attached['exit_code'] or attached['stdout'].strip() != '0':
                continue
            thread = (await self.native.rpc('thread/read', {
                'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
            if thread['status']['type'] not in ('idle', 'notLoaded'):
                continue
            await self.cancel_wakes(project)
            await command('tmux', 'kill-session', '-t', '=' + project['tmux_session_name'])
            await self.native.rpc('thread/unsubscribe', {'threadId': project['codex_session_id']})
            logging.getLogger('scheduler').info('Released detached inactive TUI for %s', project['slug'])

    async def selective_wake(self):
        if time.monotonic() - self.last_unsnooze_poll < 10:
            return
        try:
            status = await command('unsnooze', 'status', '--json')
        except Exception as exc:
            self.health_errors['unsnooze'] = self.redactor.clean(str(exc))
            raise
        self.health_errors.pop('unsnooze', None)
        self.unsnooze = json.loads(status['stdout'])
        self.last_unsnooze_poll = time.monotonic()
        selected = self.db.setting('selected')
        if not selected or self.db.setting('pause_all', False):
            return
        project = self.db.get(selected)
        if (project['lifecycle'] != 'ready' or project['operation'] or
                project['goal_status'] != 'usage limited' or project['queue_position'] != 1):
            return
        for item in self.unsnooze.get('sessions', []):
            if (item.get('sessionId') == project['codex_session_id'] and item['status'] == 'stopped'
                    and item.get('resetSource') != 'fallback' and item.get('resetAt')
                    and item['resetAt'] <= time.time() * 1000):
                # 1.19.0 resume-now delegates asynchronously and may revive a lost
                # pane using `codex resume ID MESSAGE`, bypassing the slash command
                # and our admission gate. Reuse our durable mapped-TUI resume instead.
                self.db.update(selected, operation=json.dumps({'kind': 'resume',
                    'source': 'unsnooze', 'requested_at': time.time(),
                    'reset_at': item['resetAt'], 'unsnooze_key': item['key']}))
                break

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.native:
            await self.native.close()
        self.db.conn.close()
