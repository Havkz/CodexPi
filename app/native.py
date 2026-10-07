"""Native Codex RPC and the scheduler's local TUI admission gate."""
import asyncio
import contextlib
import importlib.util
import json
import logging
import socket
import struct
import time
from pathlib import Path

from aiohttp import ClientSession, UnixConnector, WSMsgType, web

from .common import NATIVE_STATUS


class NativeError(RuntimeError):
    pass


def process_in_pane(pid, pane_pid):
    """Bind a Unix TUI peer to the current pane, including launcher children."""
    seen = set()
    while pid and pid > 1 and pid not in seen:
        if pid == pane_pid:
            return True
        seen.add(pid)
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            pid = int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
        except (OSError, ValueError, StopIteration):
            return False
    return False


def project_thread_config(path):
    # Scope unattended Git writes to this project's metadata; retain the workspace sandbox.
    return {'features.multi_agent': False, 'sandbox_workspace_write.network_access': True,
            'sandbox_workspace_write.writable_roots': [str(Path(path) / '.git')]}


def turn_params(project, params):
    params = {**params, 'cwd': project['project_path'], 'runtimeWorkspaceRoots': [project['project_path']],
              'approvalPolicy': 'never', 'sandboxPolicy': {'type': 'workspaceWrite',
              'writableRoots': [str(Path(project['project_path']) / '.git')], 'networkAccess': True,
              'excludeTmpdirEnvVar': False, 'excludeSlashTmp': False}}
    params.pop('permissions', None)
    return params


async def idle_thread(native, session):
    """Read-only proof; never interrupt a turn merely to schedule a reset wake."""
    thread = (await native.rpc('thread/read', {'threadId': session, 'includeTurns': False}))['thread']
    status = thread['status']['type']
    if status in ('idle', 'notLoaded'):
        return True
    if status != 'systemError':
        return False
    turns = (await native.rpc('thread/turns/list', {'threadId': session, 'limit': 1,
                                                 'sortDirection': 'desc'}))['data']
    return bool(turns) and turns[0]['status'] in ('completed', 'failed', 'interrupted')


def validate_model_selection(params):
    # Exact 0.155.1 build_model_selection_edits shape. Never allow a caller-selected
    # file, parent table, profile, merge, or mixed batch to change security settings.
    if (not isinstance(params, dict) or set(params) - {'edits', 'filePath', 'expectedVersion', 'reloadUserConfig'}
            or params.get('filePath') is not None
            or params.get('expectedVersion') is not None and not isinstance(params['expectedVersion'], str)
            or type(params.get('reloadUserConfig', False)) is not bool):
        raise ValueError('Only native model/reasoning selection config writes are allowed')
    edits = params.get('edits')
    if not isinstance(edits, list) or len(edits) != 2:
        raise ValueError('Model selection requires exactly model and reasoning effort')
    values = {}
    for edit in edits:
        if (not isinstance(edit, dict) or set(edit) != {'keyPath', 'value', 'mergeStrategy'}
                or edit['mergeStrategy'] != 'replace' or not isinstance(edit['keyPath'], str)
                or edit['keyPath'] not in ('model', 'model_reasoning_effort') or edit['keyPath'] in values):
            raise ValueError('Invalid model selection edit')
        values[edit['keyPath']] = edit['value']
    model, effort = values['model'], values['model_reasoning_effort']
    if (not isinstance(model, str) or not model.strip() or len(model) > 200
            or any(ord(char) < 32 for char in model)
            or effort is not None and (not isinstance(effort, str)
                or effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'))):
        raise ValueError('Invalid model or reasoning effort')


class Native:
    def __init__(self, socket, event=None, disconnected=None):
        self.socket = str(socket)
        self.event = event
        self.disconnected = disconnected
        self.pending = {}
        self.sequence = 0
        self.client = None
        self.ws = None
        self.reader = None
        self.closing = False

    async def connect(self, initialize=True):
        self.client = ClientSession(connector=UnixConnector(path=self.socket))
        try:
            self.ws = await self.client.ws_connect('http://localhost/', max_msg_size=32 * 1024 * 1024)
            self.reader = asyncio.create_task(self.read())
            if initialize:
                await self.rpc('initialize', {'clientInfo': {'name': 'codexpi', 'version': '0.1'},
                                             'capabilities': {'experimentalApi': True}})
                await self.ws.send_json({'method': 'initialized', 'params': {}})
            return self
        except BaseException:
            await self.close()
            raise

    async def read(self):
        try:
            async for packet in self.ws:
                if packet.type != WSMsgType.TEXT:
                    continue
                value = json.loads(packet.data)
                if 'method' not in value and value.get('id') in self.pending:
                    future = self.pending.pop(value['id'])
                    if not future.done():
                        future.set_result(value)
                elif self.event:
                    await self.event(value)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(NativeError('Native Codex connection closed'))
            self.pending.clear()
            if self.disconnected and not self.closing:
                await self.disconnected()

    async def rpc(self, method, params, timeout=90):
        if self.ws is None or self.ws.closed:
            raise NativeError('Native Codex is unavailable')
        self.sequence += 1
        request_id = 'codexpi-' + str(self.sequence)
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.ws.send_json({'id': request_id, 'method': method, 'params': params})
            value = await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)
        if 'error' in value:
            raise NativeError(str(value['error'].get('message', 'Native request failed')))
        return value.get('result', {})

    async def close(self):
        self.closing = True
        if self.ws:
            await self.ws.close()
        if self.reader:
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader
        if self.client:
            await self.client.close()


class GoalSource:
    """Reuse upstream parsing and event comparison; never retain objective text."""
    def __init__(self, root):
        script = root / 'Setup/upstream/goal-hooks/hooks/goal_status_report.py'
        spec = importlib.util.spec_from_file_location('goal_status_report', script)
        self.upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.upstream)
        self.upstream.preview_text = lambda *args, **kwargs: ''
        self.root = root
        self.state = root / 'state/goal-hooks'
        self.state.mkdir(parents=True, exist_ok=True)

    def rows(self):
        paths = [Path('/home/raspberry/.codex/goals_1.sqlite'),
                 Path('/home/raspberry/.codex/sqlite/goals_1.sqlite')]
        rows = self.upstream.read_goal_rows(paths, self.state)
        aliases = {key.lower(): value for key, value in NATIVE_STATUS.items()}
        aliases.update({'usage_limited': 'usage limited', 'budget_limited': 'limited by budget'})
        for row in rows.values():
            status = row['status']
            if status not in aliases:
                raise NativeError('Unknown native goal status; scheduler stopped: ' + status)
            row['status'] = aliases[status]
            row.pop('objective_preview', None)
        return rows


async def tui_proxy(request):
    controller = request.app['controller']
    client = web.WebSocketResponse(max_msg_size=32 * 1024 * 1024)
    await client.prepare(request)
    request.app['sockets'].add(client)

    async def event(value):
        await client.send_json(value)

    async def disconnected():
        logging.getLogger('tui').warning('Native transport closed for TUI connection %s', id(client))
        await client.close(code=1011, message=b'Native bridge connection closed; reopen codexpi')

    try:
        upstream = await Native(controller.root / 'state/native.sock', event, disconnected).connect(initialize=False)
    except Exception:
        request.app['sockets'].discard(client)
        await client.close(code=1011, message=b'Native bridge unavailable')
        return client
    tasks = set()
    resumed = set()
    connection_id = id(client)
    peer = request.transport.get_extra_info('socket') if request.transport else None
    peer_pid = None
    if peer is not None and hasattr(socket, 'SO_PEERCRED') and peer.family == socket.AF_UNIX:
        try:
            peer_pid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0]
        except OSError:
            pass  # A closing/unknown peer can never authorize pane input.
    controller.tui_peer_pids[connection_id] = peer_pid

    async def forward(value):
        request_id = value.get('id')
        method = value.get('method')
        params = value.get('params') or {}
        try:
            if getattr(controller, 'maintenance', False):
                raise ValueError('Codex CLI maintenance in progress; reopen codexpi afterwards')
            if method in ('thread/resume', 'turn/start', 'turn/steer', 'thread/goal/set', 'thread/goal/clear',
                          'thread/name/set', 'thread/settings/update', 'config/batchWrite', 'thread/shellCommand'):
                controller.db.set_setting('last_tui_activity', time.time())
            if method in ('thread/start', 'thread/fork'):
                raise ValueError('New projects must be created using codexpi and /rename')
            if (method in ('review/start', 'thread/realtime/start', 'thread/archive', 'thread/delete',
                           'thread/unarchive', 'thread/rollback', 'config/value/write') or
                    (method and method.startswith(('process/', 'command/exec', 'experimentalFeature/enablement/'))) or
                    (method and method.startswith('thread/queue/') and method != 'thread/queue/list')):
                raise ValueError('This operation bypasses the CodexPi single-project queue')
            if method == 'thread/list':
                result = await upstream.rpc(method, params)
                result['data'] = [thread for thread in result.get('data', [])
                    if (project := controller.db.by_session(thread['id'])) and project['lifecycle'] == 'ready']
                if not params.get('cursor') and not params.get('archived'):
                    ids = {thread['id'] for thread in result['data']}
                    # Native lists omit newly created, empty threads. Read their real
                    # persisted metadata; do not invent preview/history records.
                    for project in controller.db.all():
                        if project['lifecycle'] != 'ready' or project['codex_session_id'] in ids:
                            continue
                        thread = (await upstream.rpc('thread/read', {'threadId': project['codex_session_id'],
                                                                    'includeTurns': False}))['thread']
                        if not params.get('searchTerm') or params['searchTerm'].lower() in (
                                str(thread.get('name', '')) + ' ' + str(thread.get('preview', ''))).lower():
                            result['data'].append(thread)
            elif method == 'thread/unsubscribe':
                result = await upstream.rpc(method, params)
                project = controller.db.by_session(params.get('threadId'))
                if project:
                    resumed.discard(project['project_id'])
                    controller.tui_connections.get(project['project_id'], {}).pop(connection_id, None)
            elif method == 'config/batchWrite':
                async with controller.lock:
                    if not any(p['project_id'] in resumed and p['lifecycle'] == 'ready' for p in controller.db.all()):
                        raise ValueError('Model selection requires a mapped ready TUI session')
                    validate_model_selection(params)
                    result = await upstream.rpc(method, params)
            elif method == 'thread/name/set':
                project = controller.db.by_session(params.get('threadId'))
                if not project:
                    raise ValueError('Session is not managed by CodexPi')
                if params.get('name') != project['display_name']:
                    from .lifecycle import begin
                    await begin(controller, project['project_id'], 'rename', name=params.get('name'), defer=True)
                    result = {}
                else:
                    result = await upstream.rpc(method, params)
            elif method in ('thread/goal/set', 'turn/start', 'turn/steer', 'thread/resume', 'thread/goal/clear',
                            'thread/goal/get', 'thread/settings/update', 'thread/compact/start',
                            'thread/shellCommand', 'thread/inject_items'):
                async with controller.lock:
                    project = controller.db.by_session(params.get('threadId'))
                    if not project:
                        raise ValueError('Session is not managed by CodexPi')
                    if project['lifecycle'] != 'ready':
                        raise ValueError('Project lifecycle operation is in progress')
                    if method == 'thread/resume':
                        if params.get('history') or params.get('path'):
                            raise ValueError('Resume must use the mapped native session ID')
                        params = {**params, 'cwd': project['project_path'], 'runtimeWorkspaceRoots': [project['project_path']],
                                  'approvalPolicy': 'never', 'sandbox': 'workspace-write',
                                  'config': {**(params.get('config') or {}), **project_thread_config(project['project_path'])}}
                        params.pop('permissions', None)
                    if method in ('thread/settings/update', 'turn/start'):
                        params = turn_params(project, params)
                    selected = controller.db.setting('selected')
                    if method == 'thread/goal/set':
                        status = params.get('status')
                        if status == 'paused':
                            controller.db.set_setting('manual_pause/' + project['project_id'], True)
                        if status is None:
                            goal = (await upstream.rpc('thread/goal/get', {'threadId': params['threadId']})).get('goal')
                            status = goal['status'] if goal else 'active'
                        if status == 'active':
                            controller.db.set_setting('manual_pause/' + project['project_id'], False)
                            if controller.db.setting('pause_all', False) or (selected and selected != project['project_id']):
                                # Store the exact objective but never start a second model turn.
                                params = {**params, 'status': 'paused'}
                                import uuid
                                controller.db.update(project['project_id'], operation=json.dumps({
                                    'kind': 'resume', 'source': 'queue', 'id': str(uuid.uuid4()),
                                    'requested_at': time.time()}))
                            else:
                                controller.select(project['project_id'])
                    if method in ('turn/steer', 'thread/compact/start',
                                  'thread/shellCommand', 'thread/inject_items') and (selected != project['project_id']
                            or controller.db.setting('pause_all', False)
                            or controller.db.setting('manual_pause/' + project['project_id'], False)):
                        raise ValueError('Project is queued. Use Run now in the dashboard to work on it.')
                    if method == 'turn/start':
                        from .prompts import submit
                        result = await submit(controller, project, params, upstream)
                    else:
                        result = await upstream.rpc(method, params)
                    if method == 'thread/resume':
                        resumed.add(project['project_id'])
                        controller.tui_connections.setdefault(project['project_id'], {})[connection_id] = time.monotonic()
                        logging.getLogger('tui').info('TUI %s (peer PID %s) resumed mapped session %s',
                                                     connection_id, peer_pid, project['codex_session_id'])
                    if method == 'thread/goal/set':
                        current = controller.db.get(project['project_id'])
                        operation = json.loads(current['operation'] or '{}')
                        if params.get('status') == 'active' and operation.get('kind') == 'resume' and operation.get('sent_at'):
                            operation['ack_at'] = time.time()
                            controller.db.update(project['project_id'], operation=json.dumps(operation))
                        if result['goal']['status'] == 'paused':
                            await controller.wait_idle(project)
                            if controller.db.setting('manual_pause/' + project['project_id'], False):
                                operation = json.loads(project['operation'] or '{}')
                                if operation.get('kind') == 'resume':
                                    controller.finish_resume(project, operation, 'cancelled', 'Resume cancelled by native pause')
                                await controller.cancel_wakes(project)
                        controller.record_goal(project, result['goal'])
                    if method == 'thread/goal/clear':
                        controller.db.set_setting('manual_pause/' + project['project_id'], True)
                        await controller.wait_idle(project)
                        from .prompts import cancel_active
                        cancel_active(controller, project)
                        operation = json.loads(project['operation'] or '{}')
                        if operation.get('kind') == 'resume':
                            controller.finish_resume(project, operation, 'cancelled', 'Native goal was cleared')
                        controller.db.update(project['project_id'], goal_status='paused', operation=None, usage_limit=None)
                        await controller.cancel_wakes(project)
                        if selected == project['project_id']:
                            controller.db.set_setting('selected', None)
            elif method is not None and request_id is not None:
                result = await upstream.rpc(method, params)
            else:
                await upstream.ws.send_json(value)
                return
            await client.send_json({'id': request_id, 'result': result})
        except Exception as exc:
            await client.send_json({'id': request_id, 'error': {'code': -32000,
                                    'message': controller.redactor.clean(str(exc))}})

    try:
        async for packet in client:
            if packet.type == WSMsgType.TEXT:
                task = asyncio.create_task(forward(json.loads(packet.data)))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    finally:
        logging.getLogger('tui').info('TUI %s disconnected; mapped projects %s; close code %s',
                                    connection_id, sorted(resumed), client.close_code)
        request.app['sockets'].discard(client)
        controller.tui_peer_pids.pop(connection_id, None)
        for project_id in resumed:
            controller.tui_connections.get(project_id, {}).pop(connection_id, None)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await upstream.close()
    return client
