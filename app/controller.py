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

import yaml

from .common import NATIVE_STATUS, Redactor, atomic_write, block_summary, capacity_wait, slugify
from .db import Database
from .native import GoalSource, Native, NativeError, idle_thread, process_in_pane, project_thread_config


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
        self.tui_peer_pids = {}
        self.task = None
        self.maintenance = False

    @property
    def account_switch_pending(self):
        from .accounts import switching
        return switching(self)

    def account_holds_goal(self, project):
        from .accounts import holds_goal
        return holds_goal(self, project)

    @property
    def windows_online(self):
        return bool(self.worker is not None and not self.worker.closed and self.worker_seen and
                    time.monotonic() - self.worker_seen < 60)

    async def start(self):
        from .accounts import notification
        # Type=simple starts before the app-server's socket is ready at boot.
        async with asyncio.timeout(30):
            while True:
                try:
                    self.native = await Native(self.root / 'state/native.sock', lambda value: notification(self, value)).connect()
                    break
                except NativeError:
                    await asyncio.sleep(0.5)
        async with self.lock:
            if not self.account_switch_pending:
                from .accounts import refresh
                try:
                    await refresh(self)
                except Exception:
                    self.health_errors['account_usage'] = 'The native account and its fresh quota could not be confirmed'
                    self.accounts_bootstrap_failed = True
            await self.recover()
        self.task = asyncio.create_task(self.scheduler())

    def select(self, project_id):
        with contextlib.nullcontext() if self.db.conn.in_transaction else self.db.transaction():
            ordered = [p['project_id'] for p in self.db.all() if p['queue_position'] is not None]
            ordered = [project_id] + [i for i in ordered if i != project_id]
            for position, ident in enumerate(ordered, 1):
                self.db.update(ident, queue_position=position)
            self.db.set_setting('selected', project_id)

    def record_goal(self, project, goal):
        status = NATIVE_STATUS[goal['status']]
        operation = json.loads(project['operation'] or '{}')
        owner = self.db.setting('usage_account/' + project['project_id'])
        new_limit = bool(status == 'usage limited' and operation.get('sent_at')
            and operation.get('account_id') == self.db.setting('active_account')
            and owner != operation.get('account_id') and operation.get('before_updated_at') is not None
            and goal.get('updatedAt', 0) > operation['before_updated_at'])
        self.record_status(project, status, new_limit=new_limit, last_activity=time.time())
        if status == 'active':
            if project['goal_status'] != 'active':
                self.clear_block(project)
        if (status == 'paused' and self.db.setting('selected') == project['project_id']
                and not self.account_holds_goal(project)):
            self.db.set_setting('selected', None)

    def record_status(self, project, status, *, prompt_limit=None, new_limit=False, **fields):
        # State and notification outbox must survive (or roll back) together,
        # including changes first observed during restart recovery.
        operation = json.loads(project['operation'] or '{}')
        changed = (status != project['goal_status'] or new_limit or prompt_limit is not None
                   and self.db.setting('active_account')
                   and self.db.setting('usage_account/' + project['project_id']) != self.db.setting('active_account'))
        summary = block_summary(project, fields.get('block_reason', project['block_reason']), status)
        question = status == 'stalled' and summary and summary['requires_user']
        if status == 'stalled' and summary:
            previous = block_summary(project)
            changed = changed or not previous or any(summary[key] != previous[key] for key in
                ('reasons', 'explanation', 'solution', 'requires_user'))
        if status != 'usage limited' or changed:
            fields['usage_limit'] = None
        if status != 'complete':
            fields['completion_notified'] = 0
        if (status == 'active' and (changed or json.loads(project['resume_result'] or '{}').get('status') == 'failed')
                and (not operation or operation.get('kind') == 'resume' and operation.get('error'))):
            fields.update(operation=None, resume_result=None)  # A later native resume supersedes a terminal failed attempt.
        if status in ('stalled', 'usage limited', 'limited by budget') and changed and operation.get('kind') == 'resume':
            fields['operation'] = None
            fields['resume_result'] = json.dumps({'id': operation.get('id'), 'status': status,
                'message': 'Native goal reports ' + status})
        with contextlib.nullcontext() if self.db.conn.in_transaction else self.db.transaction():
            self.db.update(project['project_id'], goal_status=status, **fields)
            if prompt_limit is not None:
                self.db.set_setting('prompt_limit/' + project['project_id'], prompt_limit)
            if changed and status in ('stalled', 'usage limited', 'limited by budget'):
                payload = {'reason': fields.get('block_reason', project['block_reason'])}
                if status == 'usage limited':
                    # No work starts under the new login until its barrier clears.
                    # Any late native limit while switching still belongs to the old turn.
                    switch = self.db.setting('account_switch', {})
                    owner = switch.get('old_account') if self.account_switch_pending else self.db.setting('active_account')
                    if owner:
                        payload['account_id'] = owner
                        self.db.set_setting('usage_account/' + project['project_id'], owner)
                    payload['failed_prompt'] = prompt_limit is not None
                self.db.event(project['project_id'], 'question' if question else status, payload)
                if status == 'usage limited':
                    self.persist_usage_resets()

    def clear_block(self, project):
        (Path(project['project_path']) / '.codexpi/block.json').unlink(missing_ok=True)
        self.db.update(project['project_id'], block_reason=None, windows_required=0)
        self.db.conn.execute('DELETE FROM settings WHERE key=?', ('native_block_check/' + project['project_id'],))

    def can_auto_resume(self, project):
        return (project['lifecycle'] == 'ready' and not self.db.setting('pause_all', False)
                and not self.db.setting('manual_pause/' + project['project_id'], False)
                and not self.db.setting('prompt_resume_required/' + project['project_id'], False)
                and not json.loads(project['block_reason'] or '{}').get('requires_user'))

    async def create(self, name):
        if getattr(self, 'maintenance', False):
            raise ValueError('Codex CLI update is in progress; reopen after maintenance completes')
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
        if self.db.setting('self_hosted_actions', False):
            from .actions_guard import install
            install(path)
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
        await self.open_tui(project, [project['codex_session_id']])

    async def mapped_tui_ready(self, project):
        connections = self.tui_connections.get(project['project_id'], {})
        if not connections:
            return False
        pane = await command('tmux', 'display-message', '-p', '-t',
                             project['tmux_session_name'] + ':0.0', '#{pane_pid}', check=False)
        if pane['exit_code'] or not pane['stdout'].strip().isdigit():
            return False
        pane_pid = int(pane['stdout'].strip())
        return any(since is not None and time.monotonic() - since >= 1 and
                   process_in_pane(self.tui_peer_pids.get(connection_id), pane_pid)
                   for connection_id, since in connections.items())

    async def browse(self):
        if getattr(self, 'maintenance', False):
            raise ValueError('Codex CLI update is in progress; reopen after maintenance completes')
        async with self.lock:
            # A fresh view opens the native picker every time; never overwrite a
            # previous browser TUI's draft or inject /resume into its composer.
            project = {'tmux_session_name': 'codexpi-browser-' + uuid.uuid4().hex[:12], 'project_path': str(self.root)}
            await self.open_tui(project, ['--all', '--include-non-interactive'])
            return {'tmux_session_name': project['tmux_session_name']}

    async def open_tui(self, project, resume_args):
        self.db.set_setting('last_tui_activity', time.time())
        if await self.pane_exists(project):
            await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'mouse', 'on')
            return
        args = ['env', 'UNSNOOZE_AUTO_RESUME=false', '/home/raspberry/.local/bin/unsnooze', '_run', 'codex',
                '-c', 'check_for_update_on_startup=false',
                '--remote', 'unix://' + str(self.root / 'state/tui.sock'),
                '--no-alt-screen', 'resume', *resume_args]
        dead = await command('tmux', 'has-session', '-t', '=' + project['tmux_session_name'], check=False)
        if dead['exit_code'] == 0:
            await command('tmux', 'respawn-pane', '-t', project['tmux_session_name'] + ':0.0',
                          '-c', project['project_path'], shlex.join(args))
        else:
            await command('tmux', 'new-session', '-d', '-s', project['tmux_session_name'],
                          '-c', project['project_path'], '-x', '120', '-y', '36', shlex.join(args))
        await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'status', 'off')
        await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'remain-on-exit', 'on')
        # Without mouse reporting, terminals can translate wheel events into prompt-history arrows.
        await command('tmux', 'set-option', '-t', project['tmux_session_name'], 'mouse', 'on')

    async def slash(self, project, text):
        if not await self.pane_exists(project):
            raise RuntimeError('Codex TUI pane is unavailable')
        await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', '-l', text)
        # Codex coalesces fast keystrokes into paste bursts; submit after that burst closes.
        await asyncio.sleep(0.25)
        await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', 'Enter')

    async def pause(self, project, release=True, preserve_operation=False, preserve_status=False, manual=False):
        if manual:
            # Persist intent before the native RPC: a crash cannot turn Pause into Resume.
            self.db.set_setting('manual_pause/' + project['project_id'], True)
        goal = await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})
        if (goal.get('goal') and goal['goal']['status'] != 'complete'
                and (not preserve_status or goal['goal']['status'] == 'active')):
            await self.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'paused'})
            self.db.update(project['project_id'], goal_status='paused')
        # Pausing a native goal stops continuation, not its already-running turn.
        # Interrupt that turn and confirm native idleness before releasing the single-worker slot.
        await self.wait_idle(project)
        from .prompts import active, cancel_active
        if active(self, project) or self.db.setting('prompt_limit/' + project['project_id']):
            self.db.update(project['project_id'], goal_status='paused', usage_limit=None)
        cancel_active(self, project)
        if not preserve_operation:
            operation = json.loads(project['operation'] or '{}')
            if operation.get('kind') == 'resume':
                self.finish_resume(project, operation, 'cancelled', 'Resume cancelled by pause')
            else:
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
            if thread['status']['type'] not in ('active', 'systemError'):
                raise RuntimeError('Cannot confirm native worker idleness')
            turns = await self.native.rpc('thread/turns/list', {
                'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc'})
            if thread['status']['type'] == 'systemError':
                # Provider failures can leave a terminal turn in systemError.
                # Require native terminal evidence, never infer idle from an error.
                if turns['data'] and all(t['status'] in ('completed', 'failed', 'interrupted') for t in turns['data']):
                    return
                raise RuntimeError('Cannot confirm native worker idleness')
            for turn in turns['data']:
                if turn['status'] == 'inProgress':
                    await self.native.rpc('turn/interrupt', {'threadId': project['codex_session_id'], 'turnId': turn['id']})
            if time.monotonic() >= deadline:
                raise RuntimeError('Native turn did not stop; another project was not started')
            await asyncio.sleep(0.2)

    async def run_now(self, project_id):
        return await self.resume(project_id, promote=True)

    async def set_queue_status(self, project_id, expected, target):
        from .prompts import key, queue_status
        async with self.lock:
            project = self.db.get(project_id)
            if self.account_switch_pending or getattr(self, 'maintenance', False):
                raise ValueError('Wait for account or CLI maintenance before changing queue status')
            current = queue_status(self, project)
            if expected not in ('paused', 'queued') or target not in ('paused', 'queued') or expected == target:
                raise ValueError('Only paused and queued can be switched')
            if current != expected:
                raise ValueError('Queue status changed; review it and confirm again')
            goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
            if (goal and goal['status'] != project['goal_status'] or
                    not await idle_thread(self.native, project['codex_session_id'])):
                raise ValueError('Native project state changed; refresh before changing queue status')
            with self.db.transaction():
                self.db.set_setting('manual_pause/' + project_id, target == 'paused')
                if project['goal_status'] == 'complete' and self.db.setting(key(project), []):
                    # Queue eligibility does not authorize execution of a new completed-goal prompt.
                    self.db.set_setting('prompt_resume_required/' + project_id, True)
            return {'ok': True, 'queue_status': target}

    async def resume(self, project_id, *, promote=False):
        async with self.lock:
            if self.account_switch_pending:
                raise ValueError('Wait for the pending Codex account change before resuming or promoting a project')
            project = self.db.get(project_id)
            if project['lifecycle'] != 'ready':
                raise ValueError('Project lifecycle recovery must finish before resuming')
            from .prompts import active, dispatch, key
            current_prompt = active(self, project)
            if current_prompt:
                if current_prompt.get('phase') != 'active' or not current_prompt.get('result'):
                    raise ValueError('Prompt delivery requires inspection; it will not be sent again')
                return {'ok': True, 'operation_id': current_prompt['id']}
            queue = self.db.setting(key(project), [])
            if queue and not project['operation']:
                if promote and (project['queue_position'] in (None, 1) or self.db.setting('selected') == project_id):
                    raise ValueError('Run now is only available when promoting another queued project')
                self.db.enqueue(project_id)
                project = self.db.get(project_id)
                selected = self.db.setting('selected')
                if promote and selected and selected != project_id:
                    await self.pause(self.db.get(selected), preserve_status=True)
                    selected = None
                ident = queue[0]['id']
                with self.db.transaction():
                    self.db.set_setting('manual_pause/' + project_id, False)
                    self.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_resume_required/' + project_id,))
                    self.db.update(project_id, resume_result=json.dumps({'id': ident, 'status': 'queued',
                        'message': 'Saved prompt queued; the current project keeps its execution slot'}))
                if promote or (not selected or selected == project_id) and project['queue_position'] == 1:
                    self.db.set_setting('pause_all', False)
                    self.select(project_id)
                    # An explicit new user prompt is not a restart of the completed goal.
                    await dispatch(self, self.db.get(project_id), self.native, allow_limited=True)
                return {'ok': True, 'operation_id': ident}
            if project['goal_status'] == 'complete':
                raise ValueError('Completed goals are never automatically restarted')
            operation = json.loads(project['operation'] or '{}')
            if (operation.get('kind') == 'resume' and not operation.get('error')
                    and not self.db.setting('manual_pause/' + project_id, False)
                    and (not promote or self.db.setting('selected') == project_id)):
                self.db.enqueue(project_id)
                return {'ok': True, 'operation_id': operation.get('id')}
            if operation and operation.get('kind') != 'resume':
                raise ValueError('Project has a pending lifecycle operation')
            if promote and (project['queue_position'] in (None, 1) or self.db.setting('selected') == project_id):
                raise ValueError('Run now is only available when promoting another queued project')
            goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
            if goal and goal['status'] == 'complete':
                raise ValueError('Completed goals are never automatically restarted')
            self.db.enqueue(project_id)
            project = self.db.get(project_id)
            selected = self.db.setting('selected')
            if promote and selected and selected != project_id:
                await self.pause(self.db.get(selected), preserve_status=True)
                selected = None
            operation = {'kind': 'resume', 'id': str(uuid.uuid4()), 'requested_at': time.time()}
            self.db.set_setting('manual_pause/' + project_id, False)
            if not promote and ((selected and selected != project_id) or project['queue_position'] != 1):
                self.db.update(project_id, operation=json.dumps(operation), resume_result=json.dumps({
                    'id': operation['id'], 'status': 'queued', 'message': 'Queued; the current project keeps its execution slot'}))
                return {'ok': True, 'operation_id': operation['id']}
            self.db.set_setting('pause_all', False)
            if promote:
                self.select(project_id)
            else:
                self.db.set_setting('selected', project_id)
            # Wait for the mapped TUI's post-history goal read, not just its resume RPC.
            self.db.update(project_id, operation=json.dumps(operation), resume_result=None)
            return {'ok': True, 'operation_id': operation['id']}

    def finish_resume(self, project, operation, status, message):
        self.db.update(project['project_id'], operation=None, resume_result=json.dumps({
            'id': operation.get('id'), 'status': status, 'message': message}))

    async def cancel_wakes(self, project, *, refresh=False):
        wait = self.db.setting('account_wait') or {}
        if wait.get('project_id') == project['project_id']:
            self.db.set_setting('account_wait', None)
        if refresh:
            self.unsnooze = json.loads((await command('unsnooze', 'status', '--json'))['stdout'])
        for item in self.unsnooze.get('sessions', []):
            if item.get('sessionId') == project['codex_session_id'] and item['status'] not in ('cancelled', 'resumed'):
                await command('unsnooze', 'cancel', item['key'])
                item['status'] = 'cancelled'

    async def recover(self):
        from .lifecycle import recover
        await recover(self)
        rows = self.source.rows()
        with self.db.transaction():
            for project in self.db.all():
                operation = json.loads(project['operation'] or '{}')
                row = rows.get(project['codex_session_id'])
                if (project['lifecycle'] == 'ready' and operation.get('kind') == 'resume'
                        and not operation.get('error') and row and row['status'] != 'complete'):
                    self.db.enqueue(project['project_id'])
            self.db.compact_queue()
        if not self.db.setting('manual_pause_policy_initialized', False):
            # Legacy paused rows did not distinguish a user pause from queue
            # suspension. Do not guess authority to restart those sessions.
            with self.db.transaction():
                for project in self.db.all():
                    pending = json.loads(project['operation'] or '{}')
                    if (project['goal_status'] == 'paused' and not self.account_holds_goal(project)
                            and not (pending.get('kind') == 'resume' and not pending.get('error'))):
                        self.db.set_setting('manual_pause/' + project['project_id'], True)
                self.db.set_setting('manual_pause_policy_initialized', True)
        selected = self.db.setting('selected')
        if self.db.setting('pause_all', False):
            selected = None
        # Reconcile nonselected native activity first; never violate the one-active DB constraint.
        for project in self.db.all():
            if project['lifecycle'] != 'ready':
                continue
            from .prompts import active, reconcile
            if active(self, project):
                if not selected or selected == project['project_id']:
                    self.db.enqueue(project['project_id'])
                    self.db.set_setting('selected', project['project_id'])
                    await reconcile(self, project)
                else:
                    await self.pause(project, release=False, manual=True)
                continue
            if self.db.setting('prompt_limit/' + project['project_id']) and await reconcile(self, project):
                continue
            row = rows.get(project['codex_session_id'])
            if (row and row['status'] not in ('paused', 'complete')
                    and self.db.setting('manual_pause/' + project['project_id'], False)):
                await self.pause(project, manual=True)
                row['status'] = 'paused'
                if selected == project['project_id']:
                    selected = None
            if row and row['status'] == 'active' and project['project_id'] != selected:
                await self.pause(project, release=False)
                row['status'] = 'paused'
        for project in sorted(self.db.all(), key=lambda p: rows.get(p['codex_session_id'], {}).get('status') != 'complete'):
            if project['lifecycle'] != 'ready':
                continue
            if await reconcile(self, project):
                continue
            row = rows.get(project['codex_session_id'])
            if row:
                # Completion still passes the existing Git/CI verification gate.
                if row['status'] == 'complete':
                    if project['goal_status'] != 'complete' or not project['completion_notified']:
                        await self.complete(project)
                else:
                    self.record_status(project, row['status'])
        selected = self.db.setting('selected')
        if selected and not self.db.setting('pause_all', False):
            project = self.db.get(selected)
            if project['lifecycle'] != 'ready':
                logging.getLogger('recovery').warning('Lifecycle journal retains selected project until quiescent')
            elif project['goal_status'] == 'active' and not active(self, project):
                if not self.can_auto_resume(project):
                    await self.pause(project)
                    return
                await self.attach_ready(project)
                if not project['operation']:
                    self.db.update(selected, operation=json.dumps({'kind': 'resume', 'source': 'recovery',
                        'id': str(uuid.uuid4()), 'requested_at': time.time()}))
            elif project['goal_status'] == 'usage limited':
                await self.attach_ready(project)
        logging.getLogger('recovery').info('SQLite and native goals reconciled')

    async def native_block_reason(self, project, row):
        key = 'native_block_check/' + project['project_id']
        previous = self.db.setting(key, {})
        stamp = row.get('updated_at_ms', 0)
        if previous.get('goal_updated_at') == stamp and time.time() - previous.get('checked_at', 0) < 30:
            cached = json.loads(previous.get('reason') or '{}')
            current = json.loads(project['block_reason'] or '{}')
            return project['block_reason'] if cached.get('native_turn_id') and current.get('native_turn_id') == cached['native_turn_id'] else previous.get('reason')
        check = {'checked_at': time.time(), 'goal_updated_at': stamp}
        self.db.set_setting(key, check)
        try:
            turns = (await self.native.rpc('thread/turns/list', {
                'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc'})).get('data', [])
        except NativeError as exc:
            logging.getLogger('scheduler').warning('Cannot read blocker for %s: %s', project['slug'], self.redactor.clean(exc))
            return None
        turn = turns[0] if turns else {}
        ended = turn.get('completedAt') or 0
        ended = ended / 1000 if ended > 1e12 else ended
        updated = stamp / 1000 if stamp > 1e12 else stamp
        error = turn.get('error') or {}
        # Never attach an old turn's failure to a newer blocked goal.
        if turn.get('status') != 'failed' or not updated or ended < int(updated) or not error.get('message'):
            return None
        overloaded = error.get('codexErrorInfo') == 'serverOverloaded'
        previous_reason = json.loads(project['block_reason'] or '{}')
        same_turn = previous_reason.get('native_turn_id') == turn.get('id')
        reason = {
            'reason': 'Codex model at capacity' if overloaded else 'Native Codex request failed',
            'explanation': ('The selected Codex model is temporarily at capacity, so Codex could not continue. '
                'This is not a Windows worker failure or a reported usage limit.') if overloaded else error['message'],
            'solution': ['CodexPi waits five minutes, then automatically resumes this project. No action is required.'] if overloaded else
                ['Open this project with codexpi --all, check the reported Codex error and resolve it before Resume.'],
            'details': error['message'], 'requires_user': False,
            'native_error_code': error.get('codexErrorInfo'), 'native_turn_id': turn.get('id')}
        if overloaded:
            reason.update(retry_at=previous_reason.get('retry_at', time.time() + 300) if same_turn else time.time() + 300,
                          retry_attempted=bool(same_turn and previous_reason.get('retry_attempted')))
        reason = self.redactor.clean(json.dumps(reason))
        self.db.set_setting(key, {**check, 'reason': reason})
        return reason

    async def poll_goals(self):
        rows = self.source.rows()
        # Reconcile finished goals before admitting another native active row.
        # A stale active DB row must not trip the single-project UNIQUE gate.
        for project in sorted(self.db.all(), key=lambda p: rows.get(p['codex_session_id'], {}).get('status') != 'complete'):
            if project['lifecycle'] != 'ready':
                continue
            from .prompts import reconcile
            if await reconcile(self, project):
                continue
            project = self.db.get(project['project_id'])
            row = rows.get(project['codex_session_id'])
            if not row:
                continue
            status = row['status']
            old = project['goal_status']
            if status == 'active' and (self.db.setting('selected') != project['project_id'] or
                                       self.db.setting('manual_pause/' + project['project_id'], False)):
                await self.pause(project, release=False)
                self.db.event(project['project_id'], 'critical', {'message': 'Unselected native goal was paused'})
                continue
            if status == 'paused' and old != 'paused' and not self.account_holds_goal(project):
                self.db.set_setting('manual_pause/' + project['project_id'], True)
            block = Path(project['project_path']) / '.codexpi/block.json'
            reason = project['block_reason']
            if block.exists():
                value = json.loads(block.read_text())
                if not isinstance(value, dict) or not isinstance(value.get('reason'), str):
                    raise ValueError('Invalid block reason file')
                reason = self.redactor.clean(json.dumps({k: value[k] for k in
                    ('reason', 'reasons', 'explanation', 'solution', 'question', 'details', 'requires_user') if k in value}))
            if status == 'stalled' and not block.exists() and (not reason or
                    json.loads(reason).get('reason') == 'Codex model at capacity'):
                reason = await self.native_block_reason(project, row) or reason
            if status == 'complete':
                if old != 'complete' or not project['completion_notified']:
                    await self.complete(project)
                elif reason or block.exists() or project['windows_required']:
                    self.clear_block(project)
                continue
            self.record_status(project, status, block_reason=reason,
                           last_activity=row.get('updated_at_ms', 0) / (1000 if row.get('updated_at_ms', 0) > 1e12 else 1))
            operation = json.loads(project['operation'] or '{}')
            if (status == 'paused' and self.db.setting('selected') == project['project_id']
                    and operation.get('kind') != 'resume' and not self.account_holds_goal(project)):
                await self.wait_idle(project)
                self.db.set_setting('selected', None)
            if status == 'active' and old != 'active':
                self.clear_block(project)

    async def complete(self, project):
        from .prompts import active, key
        if active(self, project) or self.db.setting(key(project), []):
            return  # An old completed goal is not delivery proof for newly queued work.
        if not await idle_thread(self.native, project['codex_session_id']):
            return  # A terminal goal alone does not prove its final turn settled.
        if self.db.conn.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('sent','running')",
                                (project['project_id'],)).fetchone():
            return
        # Persist the native outcome independently of release verification. Do
        # not publish the completion outbox/queue advancement until checks pass.
        with self.db.transaction():
            self.db.update(project['project_id'], goal_status='complete')
            if self.db.setting('selected') == project['project_id']:
                self.db.set_setting('selected', None)
        check_key = 'completion_check/' + project['project_id']
        check = self.db.setting(check_key, {})
        if time.time() - check.get('checked_at', 0) < 30:
            return  # Bounded network polling, not a push/API loop every two seconds.
        self.db.set_setting(check_key, {'checked_at': time.time(), 'message': 'Native goal finished; verifying Git, CI and delivery'})
        try:
            await self.verify_completion(self.db.get(project['project_id']))
        except Exception as exc:
            message = self.redactor.clean(str(exc))
            self.db.set_setting(check_key, {'checked_at': time.time(), 'message': 'Completion verification: ' + message})
            logging.getLogger('completion').warning('%s: %s', project['slug'], message)

    async def verify_completion(self, project):
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
                await self.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'blocked'})
                self.record_status(project, 'stalled', block_reason=json.dumps(
                    {'reason': 'Completion verification failed', 'details': 'Final CI failed', 'requires_user': False}))
            else:
                self.db.set_setting('completion_check/' + project['project_id'], {
                    'checked_at': time.time(), 'message': 'Native goal finished; waiting for final CI for ' + project['last_commit']})
            return
        from .deployment import complete as deploy
        if not await deploy(self, project):
            return
        project = self.db.get(project['project_id'])
        self.clear_block(project)
        with self.db.transaction():
            operation = json.loads(project['operation'] or '{}')
            if operation.get('kind') == 'resume':
                self.finish_resume(project, operation, 'complete', 'Native goal completed and final checks passed')
            self.db.update(project['project_id'], goal_status='complete', queue_position=None,
                           completion_notified=1, operation=None)
            self.db.event(project['project_id'], 'complete', {'repo': project['github_repo'],
                          'commit': project['last_commit'], 'ci': project['last_ci_status']})
            self.db.compact_queue()
            # Completion may have released its idle slot while CI was pending.
            # Never clear another project's selection or preempt its work.
            if self.db.setting('selected') in (None, project['project_id']):
                self.db.set_setting('selected', None)
                self.db.set_setting('advance_queue', True)
            self.db.conn.execute('DELETE FROM settings WHERE key=?', ('completion_check/' + project['project_id'],))
        await self.cancel_wakes(project)

    async def refresh_git(self, project):
        if project['lifecycle'] != 'ready':
            return
        commit = (await command('git', 'rev-parse', 'HEAD', cwd=project['project_path']))['stdout'].strip()
        tree = await command('git', 'ls-tree', '-r', '--name-only', '-z', commit, '--', '.github/workflows',
                             cwd=project['project_path'])
        workflows = {p for p in tree['stdout'].split('\0')
                     if p.count('/') == 2 and p.endswith(('.yml', '.yaml'))}
        from .actions import CONTROLLED_WORKFLOW, dispatch_ci
        endpoint = (f"repos/{project['github_repo']}/actions/workflows/codexpi-ci.yml/runs?per_page=100"
                    if CONTROLLED_WORKFLOW in workflows else
                    f"repos/{project['github_repo']}/actions/runs?head_sha={commit}&per_page=100")
        runs = await command('gh', 'api', '--paginate', '--slurp',
                             endpoint)
        latest = {}
        for page in json.loads(runs['stdout']):
            for run in page['workflow_runs']:
                if run['path'].split('@', 1)[0] == CONTROLLED_WORKFLOW:
                    # Dispatch metadata follows the branch; checkout follows the pinned input.
                    if run.get('display_title') != 'CodexPi CI · ' + commit:
                        continue
                elif run['head_sha'] != commit:
                    continue
                key = (run['workflow_id'], run['event'])
                previous = latest.get(key)
                if previous is None or (run['id'], run['run_attempt']) > (previous['id'], previous['run_attempt']):
                    latest[key] = run
        data = list(latest.values())
        observed = {r['path'].split('@', 1)[0] for r in data}
        missing = workflows - observed
        if CONTROLLED_WORKFLOW in missing:
            receipt = await dispatch_ci(self, project, commit)
            if receipt and receipt.get('phase') == 'uncertain':
                self.db.update(project['project_id'], last_commit=commit, last_ci_status='pending')
                raise RuntimeError('CI submission is uncertain; no automatic retry: ' + receipt['error'])
        elif CONTROLLED_WORKFLOW in observed:
            receipts = self.db.setting('ci_dispatch/' + project['project_id'], {})
            if commit in receipts and receipts[commit]['phase'] != 'confirmed':
                receipts[commit].update(phase='confirmed')
                receipts[commit].pop('error', None)
                self.db.set_setting('ci_dispatch/' + project['project_id'], receipts)
        pr_only = set()
        for workflow in missing:
            text = (await command('git', 'show', commit + ':' + workflow, cwd=project['project_path']))['stdout']
            try:
                config = yaml.safe_load(text)
                # YAML 1.1 interprets GitHub's unquoted "on" as boolean True.
                triggers = config.get('on', config.get(True)) if isinstance(config, dict) else None
                events = ({triggers} if isinstance(triggers, str) else set(triggers)
                          if isinstance(triggers, (dict, list)) and all(isinstance(k, str) for k in triggers) else set())
            except yaml.YAMLError:
                events = set()  # Unknown syntax stays pending, never invent success.
            if events and events <= {'pull_request', 'pull_request_target'}:
                pr_only.add(workflow)
        if pr_only:
            pulls = json.loads((await command('gh', 'api', '--paginate', '--slurp',
                f"repos/{project['github_repo']}/commits/{commit}/pulls?per_page=100"))['stdout'])
            if not any(p.get('state') == 'open' and p.get('head', {}).get('sha') == commit
                       for page in pulls for p in page):
                missing -= pr_only  # A plain push does not trigger PR-only CI.
        state = 'not configured' if not workflows and not data else 'passed'
        # No run is not proof of success (including disabled/manual/path-filtered workflows).
        if missing or any(r['status'] != 'completed' or not r['conclusion'] for r in data):
            state = 'pending'
        if any(r['status'] == 'completed' and r['conclusion'] and
               r['conclusion'] not in ('success', 'skipped', 'neutral') for r in data):
            state = 'failure'
        with self.db.transaction():
            try:
                current = self.db.get(project['project_id'])
            except KeyError:
                return  # Deleted while GitHub was responding.
            if current['lifecycle'] != 'ready':
                return
            self.db.update(project['project_id'], last_commit=commit, last_ci_status=state)

    async def scheduler(self):
        while True:
            try:
                from .actions import poll as actions_poll
                await actions_poll(self)
                async with self.lock:
                    if self.native.ws is None or self.native.ws.closed:
                        await self.native.close()
                        from .accounts import notification
                        self.native = await Native(self.root / 'state/native.sock', lambda value: notification(self, value)).connect()
                        await self.recover()
                    from .lifecycle import recover
                    await recover(self)
                    await self.poll_goals()
                    from .accounts import tick
                    await tick(self)
                    from .power import tick as power_tick
                    await power_tick(self)
                    if time.monotonic() - self.last_backup > 3600:
                        self.db.backup(self.root / 'backups/sqlite')
                        self.last_backup = time.monotonic()
                    if not self.account_switch_pending:
                        await self.retry_capacity()
                        await self.advance_queue()
                        await self.resume_ready()
                        await self.selective_wake()
                        await self.release_idle_tuis()
                        from .maintenance import daily_update
                        await daily_update(self)
                if time.monotonic() - self.last_git_poll > 120:
                    try:
                        for project in self.db.all():
                            await self.refresh_git(project)
                    except Exception as exc:
                        self.health_errors['github'] = self.redactor.clean(str(exc))
                        raise
                    self.health_errors.pop('github', None)
                    self.last_git_poll = time.monotonic()
                self.health_errors.pop('scheduler', None)
                if (self.db.setting('native_bridge_error') and self.native.connected_at
                        and time.monotonic() - self.native.connected_at >= 10
                        and not self.native.ws.closed and not self.native.reader.done()):
                    await self.native.rpc('thread/loaded/list', {}, timeout=15)
                    self.db.set_setting('native_bridge_error', None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.health_errors['scheduler'] = self.redactor.clean(str(exc))
                if isinstance(exc, NativeError):
                    error = self.db.setting('native_bridge_error') or {}
                    if error.get('message') != self.health_errors['scheduler']:
                        self.db.set_setting('native_bridge_error', {'message': self.health_errors['scheduler'],
                                                                   'failed_at': time.time()})
                logging.getLogger('scheduler').error('%s', self.redactor.clean(str(exc)))
            # Unrelated Git, TUI, or Unsnooze failures must not starve the outbox.
            try:
                if self.bot and self.bot.is_ready():
                    await self.bot.send_pending()  # Network waits must not starve signed worker heartbeats.
                self.health_errors.pop('discord', None)
            except Exception as exc:
                self.health_errors['discord'] = self.redactor.clean(str(exc))
            await asyncio.sleep(2)

    async def retry_capacity(self):
        if self.db.setting('pause_all', False) or self.account_switch_pending or getattr(self, 'maintenance', False):
            return
        project = next((p for p in self.db.all() if p['queue_position'] == 1), None)
        if not project or not (wait := capacity_wait(project)) or not self.can_auto_resume(project) or project['operation']:
            return
        selected = self.db.setting('selected')
        if selected and selected != project['project_id']:
            return
        if self.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone():
            return
        if any(p['goal_status'] == 'active' for p in self.db.all() if p['project_id'] != project['project_id']):
            return
        self.db.set_setting('selected', project['project_id'])
        if time.time() < wait['retry_at']:
            return
        goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if not goal or goal['status'] != 'blocked' or not await idle_thread(self.native, project['codex_session_id']):
            return
        turns = (await self.native.rpc('thread/turns/list', {
            'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc'})).get('data', [])
        if (not turns or turns[0].get('id') != wait['native_turn_id'] or turns[0].get('status') != 'failed'
                or (turns[0].get('error') or {}).get('codexErrorInfo') != 'serverOverloaded'):
            return
        with self.db.transaction():
            self.db.update(project['project_id'], block_reason=json.dumps({**wait, 'retry_attempted': True}),
                operation=json.dumps({'kind': 'resume', 'source': 'capacity', 'id': str(uuid.uuid4()),
                                      'requested_at': time.time()}), resume_result=None)
            self.db.conn.execute('DELETE FROM settings WHERE key=?', ('native_block_check/' + project['project_id'],))

    async def advance_queue(self):
        if self.db.setting('pause_all', False) or self.account_switch_pending:
            return
        selected = self.db.setting('selected')
        from .prompts import active, dispatch, key, queue_status
        head = next((p for p in self.db.all() if p['queue_position'] == 1), None)
        if selected and head and selected != head['project_id'] and self.can_auto_resume(head):
            pending = json.loads(head['operation'] or '{}')
            if (head['goal_status'] not in ('usage limited', 'limited by budget')
                    and (not pending and self.db.setting(key(head), [])
                         or pending.get('kind') == 'resume' and not pending.get('error'))):
                current = self.db.get(selected)
                current_operation = json.loads(current['operation'] or '{}')
                prompt = active(self, current)
                if (current['lifecycle'] != 'ready' or current_operation and current_operation.get('kind') != 'resume'
                        or prompt and prompt.get('phase') != 'active'
                        or self.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone()):
                    return
                # Reordering is durable intent; quiesce the old session before admitting the new head.
                await self.pause(current, preserve_status=True)
                selected = None
        if selected:
            project = self.db.get(selected)
            if capacity_wait(project) and self.can_auto_resume(project):
                return  # Capacity cooldown retains its slot, just like a usage-reset wait.
            operation = json.loads(project['operation'] or '{}')
            if (not self.db.setting('auto_continue', False) or project['lifecycle'] != 'ready'
                    or project['operation'] and not (operation.get('kind') == 'resume' and operation.get('error'))
                    or project['goal_status'] not in ('stalled', 'limited by budget')
                    or self.db.setting('manual_pause/' + selected, False)):
                return
            if self.db.conn.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('sent','running')", (selected,)).fetchone():
                return
            goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
            if not goal or goal['status'] not in ('blocked', 'budgetLimited'):
                return
            if not await idle_thread(self.native, project['codex_session_id']):
                return
            await self.wait_idle(project)
            await self.cancel_wakes(project)
            with self.db.transaction():
                # A failed resume is terminal, not a lifecycle lock. Preserve its
                # result only after native blocker/idleness proof; never resend it.
                if operation.get('kind') == 'resume' and operation.get('error'):
                    self.finish_resume(project, operation, 'failed', operation['error'])
                self.db.set_setting('selected', None)
                self.db.set_setting('advance_queue', 'blocked')
        advance = self.db.setting('advance_queue', False)
        # Explicitly queued prompts/resumes need no auto-continue opt-in. A selected
        # active/limited/blocked project still retains its slot above.
        for candidate in self.db.all():
            if (candidate['queue_position'] is None or candidate['lifecycle'] != 'ready'
                    or self.db.setting('prompt_resume_required/' + candidate['project_id'], False)
                       and not (self.db.setting('auto_continue', False) and queue_status(self, candidate) == 'queued')
                    or self.db.setting('manual_pause/' + candidate['project_id'], False)):
                continue
            operation = json.loads(candidate['operation'] or '{}')
            if operation.get('kind') == 'resume' and not operation.get('error') and self.can_auto_resume(candidate):
                self.select(candidate['project_id'])
                return
            if self.db.setting(key(candidate), []):
                await dispatch(self, candidate, self.native, allow_queued=True)
                return
        if not advance or advance == 'blocked' and not self.db.setting('auto_continue', False):
            return
        rows = self.source.rows()
        next_project = next((p for p in self.db.all() if p['queue_position'] is not None
            and p['goal_status'] == 'paused' and p['codex_session_id'] in rows
            and (not p['operation'] or (json.loads(p['operation']).get('kind') == 'resume'
                 and not json.loads(p['operation']).get('error')))
            and self.can_auto_resume(p)), None)
        if next_project:
            operation = json.loads(next_project['operation'] or '{}') or {
                'kind': 'resume', 'source': 'auto-continue' if advance == 'blocked' else 'queue',
                'id': str(uuid.uuid4()), 'requested_at': time.time()}
            # Persist intent before the atomic selection; recovery can reuse it.
            self.db.update(next_project['project_id'], operation=json.dumps(operation), resume_result=None)
            self.select(next_project['project_id'])
            self.db.set_setting('advance_queue', False)
            await self.attach_ready(next_project)

    async def resume_ready(self):
        if self.db.setting('pause_all', False) or self.account_switch_pending:
            return
        for project in self.db.all():
            operation = json.loads(project['operation']) if project['operation'] else {}
            if (project['lifecycle'] != 'ready' or operation.get('kind') != 'resume'
                    or self.db.setting('selected') != project['project_id']):
                continue
            if operation.get('error'):
                continue
            if operation.get('account_id') and operation['account_id'] != self.db.setting('active_account'):
                self.finish_resume(project, operation, 'cancelled', 'Resume belongs to a different Codex account')
                continue
            if (self.db.setting('manual_pause/' + project['project_id'], False) or
                    operation.get('source') == 'auto-continue' and not self.db.setting('auto_continue', False) or
                    operation.get('source') in ('capacity', 'unsnooze', 'queue', 'auto-continue', 'windows', 'recovery', 'account-switch', 'account-reset') and not self.can_auto_resume(project)):
                self.finish_resume(project, operation, 'cancelled', 'Automatic resume is no longer authorized')
                continue
            try:
                if not operation.get('started_at'):
                    # Queue waiting is unbounded; only the selected restoration attempt times out.
                    operation['started_at'] = time.time()
                    self.db.update(project['project_id'], operation=json.dumps(operation))
                goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
                if operation.get('source') == 'unsnooze':
                    reason = json.loads(project['block_reason'] or '{}')
                    if project['queue_position'] != 1 or reason.get('requires_user'):
                        self.finish_resume(project, operation, 'cancelled', 'Automatic resume is no longer authorized')
                        continue
                    await self.cancel_wakes(project)
                ready = await self.mapped_tui_ready(project)
                if ready and await self.pane_exists(project):
                    thread = (await self.native.rpc('thread/read', {
                        'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
                    if thread['id'] != project['codex_session_id'] or thread['cwd'] != project['project_path']:
                        raise RuntimeError('Restored native session identity or workspace does not match the project')
                    if not goal:
                        self.finish_resume(project, operation, 'restored', 'Session restored. No native goal exists; enter /goal in this project TUI.')
                        continue
                    if goal['status'] == 'active' and thread['status']['type'] == 'active':
                        self.record_goal(project, goal)
                        self.finish_resume(project, operation, 'active', 'Native goal is running in the mapped session')
                        continue
                    terminal_confirmed = (operation.get('ack_at') or
                        goal['status'] != operation.get('before_status', goal['status']) or
                        operation.get('before_updated_at') is not None and
                        goal.get('updatedAt', 0) > operation['before_updated_at'] or
                        project['goal_status'] == 'active')
                    if (goal['status'] in ('usageLimited', 'blocked', 'budgetLimited')
                            and operation.get('sent_at') and terminal_confirmed):
                        self.record_goal(project, goal)
                        self.finish_resume(project, operation, NATIVE_STATUS[goal['status']], 'Native goal reports ' + NATIVE_STATUS[goal['status']])
                        continue
                    if goal['status'] == 'complete':
                        self.finish_resume(project, operation, 'verifying', 'Native goal has completed; final Git/CI verification is handled separately')
                        continue
                    if not operation.get('sent_at'):
                        # Journal before sending: a crash must not repeat a potentially delivered slash.
                        operation['sent_at'] = time.time()
                        operation['before_status'] = goal['status']
                        operation['before_updated_at'] = goal.get('updatedAt')
                        with self.db.transaction():
                            self.db.update(project['project_id'], operation=json.dumps(operation))
                            if operation.get('source') == 'unsnooze':
                                from .accounts import wake_key
                                self.db.set_setting(wake_key(self, project), {
                                    'reset_at': operation['reset_at'], 'operation_id': operation['id']})
                        await command('tmux', 'send-keys', '-t', project['tmux_session_name'] + ':0.0', 'Escape')
                        await self.slash(project, '/goal resume')
                elif not operation.get('sent_at'):
                    if (time.time() - operation['started_at'] > 10 and not operation.get('tui_reopened_at')
                            and await self.pane_exists(project) and await idle_thread(self.native, project['codex_session_id'])
                            and not self.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone()):
                        pane = await command('tmux', 'display-message', '-p', '-t',
                            project['tmux_session_name'] + ':0.0', '#{session_attached} #{pane_pid}', check=False)
                        fields = pane['stdout'].strip().split()
                        if (not pane['exit_code'] and len(fields) == 2 and fields[0] == '0' and fields[1].isdigit()
                                and not any(process_in_pane(pid, int(fields[1])) for pid in self.tui_peer_pids.values())):
                            capture = await command('tmux', 'capture-pane', '-p', '-S', '-2000', '-t',
                                                    project['tmux_session_name'] + ':0.0')
                            atomic_write(self.root / 'state/tui-recovery' / (operation['id'] + '.txt'), capture['stdout'])
                            operation['tui_reopened_at'] = time.time()
                            self.db.update(project['project_id'], operation=json.dumps(operation))
                            # Recheck attachment in tmux itself; a new terminal must not lose its draft.
                            await command('tmux', 'if-shell', '-F', '-t', project['tmux_session_name'] + ':0.0',
                                '#{==:#{session_attached},0}',
                                shlex.join(['kill-session', '-t', '=' + project['tmux_session_name']]))
                    await self.attach_ready(project)
                if time.time() - operation.get('sent_at', operation['started_at']) > 60:
                    detail = ('The mapped pane has no confirmed TUI connection for this session' if not ready else
                              '/goal resume was submitted once, but the native goal still reports ' + goal['status'])
                    if goal and goal['status'] == 'blocked' and (summary := block_summary(project)):
                        detail += '; last recorded blocker: ' + '; '.join(summary['reasons'][:2])
                    raise RuntimeError('Resume timed out: ' + detail + '; inspect the project TUI before retrying')
            except Exception as exc:
                operation['error'] = self.redactor.clean(str(exc))
                self.db.update(project['project_id'], operation=json.dumps(operation), resume_result=json.dumps({
                    'id': operation.get('id'), 'status': 'failed', 'message': operation['error']}))

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
        selected = self.db.setting('selected')
        project = self.db.get(selected) if selected else None
        # The upstream CLI takes ~2 CPU seconds on Pi; keep fast reset polling
        # only while a selected goal can need a wake. Idle health stays timestamped.
        interval = 10 if project and (project['goal_status'] == 'usage limited' or self.db.setting('account_wait')) else 60
        if self.last_unsnooze_poll and time.monotonic() - self.last_unsnooze_poll < interval:
            return
        # Account availability is metadata, never a substitute for native goal status.
        try:
            if self.db.setting('active_account') or getattr(self, 'accounts_bootstrap_failed', False):
                from .accounts import refresh
                await refresh(self)
                self.accounts_bootstrap_failed = False
            else:
                limits = await self.native.rpc('account/rateLimits/read', {}, timeout=15)
                self.db.record_usage({key: limits.get(key) for key in
                    ('ordinaryUsageAllowed', 'rateLimits', 'rateLimitsByLimitId')} | {'checked_at': time.time()})
            self.health_errors.pop('account_usage', None)
        except Exception as exc:
            self.health_errors['account_usage'] = self.redactor.clean(str(exc))
        try:
            status = await command('unsnooze', 'status', '--json')
        except Exception as exc:
            self.health_errors['unsnooze'] = self.redactor.clean(str(exc))
            raise
        self.health_errors.pop('unsnooze', None)
        self.unsnooze = json.loads(status['stdout'])
        self.last_unsnooze_poll = time.monotonic()
        self.persist_usage_resets()
        if self.db.setting('pause_all', False):
            return
        from .accounts import resume_account_wait
        if await resume_account_wait(self):
            return
        # Reordering never changes selection/preempts a running project. After a
        # real reset, however, an idle quota waiter must not pin selection to an
        # obsolete queue position and prevent the restored head from waking.
        head = next((p for p in self.db.all() if p['queue_position'] == 1), None)
        if not head:
            return
        previous_project = project
        project = head
        if (project['lifecycle'] != 'ready' or project['operation'] or
                project['goal_status'] != 'usage limited' or project['queue_position'] != 1):
            return
        if not self.can_auto_resume(project):
            return
        project = self.db.get(project['project_id'])  # Includes the reset just persisted above.
        metadata = json.loads(project['usage_limit'] or '{}')
        account_id = self.db.setting('active_account')
        if account_id and self.db.setting('usage_account/' + project['project_id']) != account_id:
            return  # A different login's native limit/reset is not this account's wake.
        if account_id:
            from .accounts import fresh_usage
            if not fresh_usage(self.db.setting('account_usage', {}), account_id):
                return
        reset = metadata.get('resetAt')
        if (metadata.get('resetSource') not in ('unsnooze', 'native-account') or not reset
                or reset > time.time() * 1000):
            return
        from .accounts import wake_key
        previous = self.db.setting(wake_key(self, project), {})
        if reset <= previous.get('reset_at', 0):
            return  # One automatic attempt per real reset, including after crashes.
        goal = (await self.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if not goal or goal['status'] != 'usageLimited':
            return
        if selected != project['project_id']:
            if previous_project:
                if (previous_project['lifecycle'] != 'ready' or previous_project['operation']
                        or previous_project['goal_status'] != 'usage limited'):
                    return
                previous_goal = (await self.native.rpc('thread/goal/get', {
                    'threadId': previous_project['codex_session_id']})).get('goal')
                if not previous_goal or previous_goal['status'] != 'usageLimited':
                    return
                if not await idle_thread(self.native, previous_project['codex_session_id']):
                    return
            if self.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone():
                return
            from .prompts import active
            if any(active(self, p) for p in self.db.all()):
                return
            if not await idle_thread(self.native, project['codex_session_id']):
                return
            self.select(project['project_id'])
            selected = project['project_id']
        item = next((s for s in self.unsnooze.get('sessions', []) if
                     s.get('sessionId') == project['codex_session_id'] and s.get('status') == 'stopped'), {})
        operation = {'kind': 'resume', 'id': str(uuid.uuid4()), 'source': 'unsnooze',
                     'requested_at': time.time(), 'reset_at': reset, 'reset_source': metadata['resetSource'],
                     'unsnooze_key': item.get('key')}
        if account_id:
            operation['account_id'] = account_id
        # Same durable mapped-TUI path for either authoritative reset source.
        # Never call resume-now: its daemon can reopen an ungated argv prompt.
        self.db.update(selected, operation=json.dumps(operation))

    def persist_usage_resets(self):
        account = self.db.setting('account_usage', {})
        account_id = self.db.setting('active_account')
        limits = account.get('rateLimits') or {}
        resets = [w['resetsAt'] * 1000 for w in (limits.get('primary'), limits.get('secondary'))
                  if w and w.get('usedPercent', 0) >= 100 and w.get('resetsAt')]
        if account_id and (account.get('account_id') != account_id or
                not isinstance(account.get('checked_at'), (int, float)) or
                not 0 <= time.time() - account['checked_at'] <= 90):
            resets = []  # A stale/different login's snapshot cannot supply this event's reset.
        for project in self.db.all():
            if project['lifecycle'] != 'ready' or project['goal_status'] != 'usage limited':
                continue
            account_id = self.db.setting('active_account')
            if account_id and self.db.setting('usage_account/' + project['project_id']) != account_id:
                continue
            tracked = next((s for s in self.unsnooze.get('sessions', []) if
                s.get('sessionId') == project['codex_session_id'] and s.get('status') == 'stopped'
                and s.get('resetSource') != 'fallback' and s.get('resetAt')), None) if not account_id else None
            # Unsnooze has no account identity; its legacy reset cannot cross a managed login change.
            candidates = ([{'resetAt': tracked['resetAt'], 'resetSource': 'unsnooze'}] if tracked else [])
            if resets:
                candidates.append({'resetAt': max(resets), 'resetSource': 'native-account'})
            metadata = max(candidates, key=lambda m: m['resetAt']) if candidates else None
            if metadata:
                if account_id:
                    metadata['account_id'] = account_id
                with contextlib.nullcontext() if self.db.conn.in_transaction else self.db.transaction():
                    self.db.update(project['project_id'], usage_limit=json.dumps(metadata))
                    if account_id:
                        self.db.set_setting('usage_limits/' + account_id + '/' + project['project_id'], metadata)
                    event = self.db.conn.execute("SELECT event_id,payload FROM events WHERE project_id=? AND kind='usage limited' ORDER BY event_id DESC LIMIT 1",
                        (project['project_id'],)).fetchone()
                    if event:
                        payload = json.loads(event['payload'])
                        if account_id and payload.get('account_id') != account_id:
                            continue  # Never rewrite an older account's notification.
                        if payload.get('usage_limit') != metadata:
                            payload.pop('reset_notified', None)
                        payload['usage_limit'] = metadata
                        self.db.conn.execute('UPDATE events SET payload=? WHERE event_id=?', (json.dumps(payload), event['event_id']))

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.native:
            await self.native.close()
        self.db.conn.close()
