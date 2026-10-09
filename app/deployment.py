"""Explicit 24/7 Pi delivery, completed through the existing lifecycle journal."""
import asyncio
import json
from pathlib import Path, PurePosixPath
import re
import time

from .common import atomic_write
from .controller import command
from .native import project_thread_config


def key(project):
    return 'deployment/' + project['project_id']


def unit_path(controller, project):
    ident = project['project_id']
    if not re.fullmatch('[a-zA-Z0-9-]{1,80}', ident):
        raise ValueError('Invalid deployment identity')
    directory = controller.root.parent / '.config/systemd/user'
    for path in (directory, directory.parent, directory.parent.parent):
        if path.is_symlink():
            raise ValueError('Service configuration directory must not be a symlink')
    path = directory / ('codexpi-project-' + ident + '.service')
    if path.is_symlink() or (path.exists() and not path.read_text().startswith('# CodexPi project ' + ident + '\n')):
        raise ValueError('Systemd service ownership mismatch')
    return path


def validate_argv(argv, source):
    if (not isinstance(argv, list) or not argv or len(argv) > 128 or any(
            not isinstance(a, str) or len(a) > 4096 or any(ord(c) < 32 for c in a) or
            str(source) in a for a in argv) or not argv[0]):
        raise ValueError('Use argv strings and project-relative paths; no control characters or old absolute project paths')


def quote(value):
    # systemd syntax, not shell syntax; prevent specifier/environment expansion.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def render(project, plan):
    path = PurePosixPath(project['project_path'])
    argv = list(plan['argv'])
    if '/' in argv[0] and not PurePosixPath(argv[0]).is_absolute():
        argv[0] = str(path / argv[0])
    return ('# CodexPi project ' + project['project_id'] + '\n[Unit]\n'
            'Description=CodexPi project ' + project['project_id'] + '\n'
            'StartLimitIntervalSec=60\nStartLimitBurst=3\n[Service]\nType=exec\n'
            'WorkingDirectory=' + str(path).replace('%', '%%') + '\n'
            'EnvironmentFile=-' + quote(str(path / '.env')) + '\n'
            'ExecStart=' + ' '.join(map(quote, argv)) + '\n'
            'Restart=on-failure\nRestartSec=5\nTimeoutStopSec=30\nKillMode=control-group\n'
            'NoNewPrivileges=yes\nUMask=0077\n[Install]\nWantedBy=default.target\n')


async def request(controller, body):
    async with controller.lock:
        project = controller.db.get(body['project_id'])
        if (controller.db.setting('selected') != project['project_id'] or project['goal_status'] != 'active'
                or project['lifecycle'] != 'ready' or project['operation'] or controller.db.setting('pause_all', False)):
            raise ValueError('Only the selected, executing project may request deployment')
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if not goal or goal['status'] != 'active':
            raise ValueError('An active native goal is required')
        if body.get('goal_requires_24x7') is not True or not isinstance(body.get('reason'), str) or not body['reason'].strip():
            raise ValueError('Explicit confirmation and the goal requirement for 24/7 deployment are required')
        from .lifecycle import owned_path
        source = owned_path(controller, project, project['project_path'])
        target = owned_path(controller, project, controller.root.parent / project['slug'])
        if source != target and target.exists():
            raise ValueError('Deployment destination already exists')
        validate_argv(body.get('argv'), source)
        validate_argv(body.get('check'), source)
        unit_path(controller, project)
        old = controller.db.setting(key(project), {})
        plan = {**old, 'argv': body['argv'], 'check': body['check'], 'reason': controller.redactor.clean(body['reason']),
                'status': 'requested', 'requested_at': time.time()}
        controller.db.set_setting(key(project), plan)
        return {'ok': True, 'message': 'Deployment scheduled after native completion, clean commit, push and CI verification',
                'target': str(target)}


async def stop(controller, project):
    plan = controller.db.setting(key(project))
    if not plan:
        return
    path = unit_path(controller, project)
    if not path.exists():
        if plan.get('installed'):
            raise ValueError('Managed service file is missing; inspect before moving its directory')
        return
    await command('systemctl', '--user', 'disable', '--now', path.name)
    state = await command('systemctl', '--user', 'show', path.name, '--property=ActiveState', '--value')
    if state['stdout'].strip() not in ('inactive', 'failed'):
        raise RuntimeError('Deployed service did not stop')


async def start(controller, project, plan):
    path = unit_path(controller, project)
    atomic_write(path, render(project, plan))
    await command('systemd-analyze', '--user', 'verify', str(path))
    await command('systemctl', '--user', 'daemon-reload')
    await command('systemctl', '--user', 'enable', '--now', path.name)
    # A successful start request alone is not a successful deployment.
    await asyncio.sleep(2)
    await command('systemctl', '--user', 'is-active', '--quiet', path.name)
    await command(*plan['check'], cwd=project['project_path'], timeout=30)
    await command('systemctl', '--user', 'is-active', '--quiet', path.name)


async def relocate_session(controller, project):
    if not project['codex_session_id']:
        return
    session, path = project['codex_session_id'], project['project_path']
    await controller.native.rpc('thread/resume', {'threadId': session, 'cwd': path, 'excludeTurns': True,
        'runtimeWorkspaceRoots': [path], 'excludeTurns': True, 'config': project_thread_config(path)})
    await controller.native.rpc('thread/settings/update', {'threadId': session, 'cwd': path,
        'sandboxPolicy': {'type': 'workspaceWrite', 'writableRoots': [str(Path(path) / '.git')],
                          'networkAccess': True, 'excludeTmpdirEnvVar': False, 'excludeSlashTmp': False}})
    await controller.native.rpc('thread/unsubscribe', {'threadId': session})


async def finish(controller, project, operation):
    from .lifecycle import move_owned, owned_path, save
    target = {**project, 'project_path': operation['target']}
    if operation['phase'] == 'quiesced':
        move_owned(owned_path(controller, project, operation['old']['project_path']),
                   owned_path(controller, project, target['project_path']), project['project_id'])
        save(controller, project, operation, 'directory')
    if operation['phase'] == 'directory':
        await relocate_session(controller, target)
        save(controller, project, operation, 'session')
    if operation['phase'] == 'session':
        plan = controller.db.setting(key(project))
        error = None
        try:
            await start(controller, target, plan)
        except Exception as exc:
            error = controller.redactor.clean(str(exc))
            # Recover the new mapping even when application health fails, so the
            # native worker can be resumed to repair it. No completion notification.
            await stop(controller, target)
            await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'blocked'})
        plan.update(status='failed' if error else 'active', installed=unit_path(controller, target).exists(), error=error,
                    verified_at=None if error else time.time(), verified_commit=None if error else project['last_commit'])
        with controller.db.transaction():
            controller.db.set_setting(key(project), plan)
            controller.db.update(project['project_id'], project_path=target['project_path'], lifecycle='ready',
                                 operation=operation['old']['operation'])
        if error:
            controller.record_status(controller.db.get(project['project_id']), 'stalled', block_reason=json.dumps(
                {'reason': 'Deployment verification failed', 'details': error, 'requires_user': False}))


async def complete(controller, project):
    """Called under the controller lock, after final Git/CI checks."""
    plan = controller.db.setting(key(project))
    if not plan:
        return True
    if plan.get('status') == 'active' and plan.get('verified_commit') == project['last_commit']:
        try:
            await command('systemctl', '--user', 'is-active', '--quiet', unit_path(controller, project).name)
            await command(*plan['check'], cwd=project['project_path'], timeout=30)
        except Exception as exc:
            await stop(controller, project)
            await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'blocked'})
            plan.update(status='failed', error=controller.redactor.clean(str(exc)), verified_at=None, verified_commit=None)
            controller.db.set_setting(key(project), plan)
            controller.record_status(project, 'stalled', block_reason=json.dumps(
                {'reason': 'Deployment verification failed', 'details': plan['error'], 'requires_user': False}))
            return False
        return True
    from .lifecycle import finish as finish_lifecycle, owned_path, record_error
    if controller.db.conn.execute("SELECT 1 FROM jobs WHERE project_id=? AND status!='finished'",
                                  (project['project_id'],)).fetchone():
        raise ValueError('Pending Windows jobs prevent deployment')
    target = owned_path(controller, project, controller.root.parent / project['slug'])
    if str(target) != project['project_path'] and target.exists():
        raise ValueError('Deployment destination already exists')
    controller.db.backup(controller.root / 'backups/sqlite')
    operation = {'kind': 'deploy', 'phase': 'prepared', 'old': project, 'target': str(target), 'requested_at': time.time()}
    controller.db.update(project['project_id'], lifecycle='deploying', operation=json.dumps(operation))
    try:
        await finish_lifecycle(controller, controller.db.get(project['project_id']))
    except Exception as exc:
        record_error(controller, project['project_id'], exc)
        return False
    return controller.db.setting(key(project))['status'] == 'active'
