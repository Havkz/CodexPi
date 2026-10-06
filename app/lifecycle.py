"""Durable, idempotent project lifecycle steps. SQLite is the operation journal."""
import json
import os
from pathlib import Path
import re
import time

import discord

from .common import atomic_write, slugify
from .controller import command


def owned_path(controller, project, path):
    path = Path(path)
    parents = ((controller.root / 'projects').resolve(), controller.root.parent.resolve())
    if (not path.is_absolute() or path.is_symlink() or path.parent.resolve() not in parents
            or path.resolve() in (controller.root.resolve(), controller.root.parent.resolve())):
        raise ValueError('Project path is outside managed project roots')
    marker = path / '.codexpi/project-id'
    if path.exists() and (not marker.is_file() or marker.is_symlink()
                          or marker.read_text() != project['project_id']):
        raise ValueError('Project directory ownership mismatch')
    if path.exists() and ((path / '.git').is_symlink() or not (path / '.git').is_dir()):
        raise ValueError('Project requires an owned, non-symlink Git directory')
    return path


def move_owned(source, target, ident):
    """Same-filesystem atomic move; never overwrite a preexisting unrelated target."""
    if source == target:
        return
    if source.exists():
        if target.exists() or target.is_symlink():
            raise ValueError('Lifecycle target already exists')
        source.rename(target)
        if os.name == 'posix':
            for parent in {source.parent, target.parent}:
                fd = os.open(parent, os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
    if (not target.is_dir() or target.is_symlink()
            or (target / '.codexpi/project-id').read_text() != ident):
        raise ValueError('Moved project ownership could not be verified')


async def channel(controller, project):
    if not project['discord_channel_id']:
        return None
    if not controller.bot or not controller.bot.is_ready():
        raise RuntimeError('Discord is unavailable; lifecycle operation will retry')
    try:
        item = await controller.bot.fetch_channel(int(project['discord_channel_id']))
    except discord.NotFound:
        return None
    if (item.category_id != int(controller.config['discord_category']) or
            item.topic != 'CodexPi project ' + project['project_id']):
        raise ValueError('Discord project channel ownership mismatch')
    return item


def save(controller, project, operation, phase):
    operation.update(phase=phase, retry_at=0)
    operation.pop('error', None)
    controller.db.update(project['project_id'], operation=json.dumps(operation))


async def begin(controller, ident, kind, *, name=None, confirmation=None, defer=False, delete_github=False):
    if type(delete_github) is not bool or delete_github and kind != 'delete':
        raise ValueError('delete_github must be an explicit boolean for Delete only')
    async with controller.lock:
        project = controller.db.get(ident)
        pending = json.loads(project['operation'] or '{}')
        if project['lifecycle'] != 'ready' or (pending and not (kind == 'delete' and pending.get('kind') == 'resume')):
            raise ValueError('Project already has a pending operation; wait for recovery')
        path = owned_path(controller, project, project['project_path'])
        if not path.exists():
            raise ValueError('Project directory is missing')
        if controller.db.conn.execute("SELECT 1 FROM jobs WHERE project_id=? AND status!='finished' AND (?!='delete' OR status!='pending')",
                                      (ident, kind)).fetchone():
            raise ValueError('Wait for pending Windows jobs before changing project lifecycle')
        operation = {'kind': kind, 'phase': 'prepared', 'old': project, 'requested_at': time.time()}
        if kind == 'rename':
            if not isinstance(name, str):
                raise ValueError('New project name is required')
            name = name.strip()
            slug = slugify(name)
            if name == project['display_name']:
                return project
            if controller.db.conn.execute('SELECT 1 FROM projects WHERE project_id!=? AND (display_name=? OR slug=?)',
                                          (ident, name, slug)).fetchone():
                raise ValueError('Project name or slug already exists')
            target = path.parent / slug
            owned_path(controller, project, target)
            if target != path and target.exists():
                raise ValueError('New project directory already exists')
            repo = controller.config['github_account'] + '/' + slug
            current = json.loads((await command('gh', 'api', 'repos/' + project['github_repo']))['stdout'])
            if (not current['private'] or current['description'] != 'Managed by CodexPi project ' + ident
                    or current['full_name'].lower() != project['github_repo'].lower()):
                raise ValueError('GitHub repository ownership mismatch')
            if repo.lower() != project['github_repo'].lower():
                check = await command('gh', 'api', 'repos/' + repo, check=False)
                if check['exit_code'] == 0:
                    raise ValueError('Target GitHub repository already exists')
                if 'HTTP 404' not in check['stderr']:
                    raise RuntimeError('Cannot safely check GitHub repository name availability')
            operation['repo_id'] = current['id']
            operation['new'] = {'display_name': name, 'slug': slug, 'project_path': str(target),
                                'github_repo': repo, 'tmux_session_name': 'codexpi-' + slug}
        elif kind == 'delete':
            if confirmation != project['display_name']:
                raise ValueError('Type the exact project name to confirm deletion')
            target = controller.root / 'backups/deleted' / ident
            if target.exists() or target.is_symlink():
                raise ValueError('Recovery backup already exists; refusing to overwrite it')
            operation['backup'] = str(target)
            operation['delete_github'] = delete_github
            if delete_github:
                response = await command('gh', 'api', 'repos/' + project['github_repo'], '--include')
                body = response['stdout']
                current = json.loads(body[body.index('{'):])
                verify_repository(controller, project, current)
                scopes = re.search(r'^x-oauth-scopes:\s*(.*)$', body, re.I | re.M)
                if scopes and 'delete_repo' not in {s.strip() for s in scopes[1].split(',')}:
                    raise ValueError('GitHub token on the Pi lacks delete_repo; grant that scope or leave repository deletion unchecked')
                if current.get('permissions', {}).get('admin') is not True:
                    raise ValueError('GitHub repository deletion requires administration permission')
                operation['repo_id'] = current['id']
        else:
            raise ValueError('Unsupported lifecycle action')
        await channel(controller, project)  # permission/ownership preflight before any mutation
        controller.db.backup(controller.root / 'backups/sqlite')
        with controller.db.transaction():
            if kind == 'delete':
                from .worker_server import cancel_pending
                cancel_pending(controller, ident, 'Project deletion cancelled the undelivered Windows job')
            controller.db.update(ident, lifecycle='renaming' if kind == 'rename' else 'deleting', operation=json.dumps(operation))
        if defer:
            return {'ok': True}  # TUI receives its acknowledgement before recovery stops its pane.
        try:
            await finish(controller, controller.db.get(ident))
        except Exception as exc:
            record_error(controller, ident, exc)
            raise RuntimeError('Operation recorded for recovery: ' + controller.redactor.clean(str(exc))) from exc
        return {'ok': True}


def record_error(controller, ident, exc):
    project = controller.db.get(ident)
    operation = json.loads(project['operation'])
    operation.update(error=controller.redactor.clean(str(exc)), retry_at=time.time() + 30)
    controller.db.update(ident, operation=json.dumps(operation))


def verify_repository(controller, project, repository):
    if (type(repository.get('id')) is not int or repository.get('private') is not True
            or repository.get('description') != 'Managed by CodexPi project ' + project['project_id']
            or repository.get('full_name', '').lower() != project['github_repo'].lower()
            or repository['full_name'].split('/')[0].lower() != controller.config['github_account'].lower()):
        raise ValueError('GitHub repository ownership mismatch; nothing was deleted')


async def delete_repository(controller, project, operation):
    endpoint = 'repositories/' + str(operation['repo_id'])
    check = await command('gh', 'api', endpoint, check=False)
    if check['exit_code']:
        if 'HTTP 404' not in check['stderr'] or not operation.get('repo_delete_requested'):
            raise RuntimeError('Cannot confirm the exact repository for deletion')
        # A lost DELETE acknowledgement can be retried only by its immutable ID.
        user = json.loads((await command('gh', 'api', 'user'))['stdout'])
        if user.get('login', '').lower() != controller.config['github_account'].lower():
            raise ValueError('GitHub recovery authentication does not match the project owner')
        return
    current = json.loads(check['stdout'])
    verify_repository(controller, project, current)
    if current['id'] != operation['repo_id']:
        raise ValueError('GitHub immutable repository identity changed')
    operation['repo_delete_requested'] = True
    save(controller, project, operation, operation['phase'])
    await command('gh', 'api', endpoint, '--method', 'DELETE')
    gone = await command('gh', 'api', endpoint, check=False)
    if not gone['exit_code'] or 'HTTP 404' not in gone['stderr']:
        raise RuntimeError('GitHub did not confirm repository removal')


async def finish(controller, project):
    from . import deployment
    operation = json.loads(project['operation'])
    if operation['kind'] == 'close-channel':
        item = await channel(controller, project)
        if item:
            await item.delete(reason='CodexPi completed project closed by user')
        controller.db.update(project['project_id'], discord_channel_id=None, operation=None)
        return
    kind, old = operation['kind'], operation['old']
    ident, session = project['project_id'], project['codex_session_id']
    if operation['phase'] == 'prepared':
        await deployment.stop(controller, project)
        if session:
            await controller.pause(project, release=kind != 'deploy', preserve_operation=True)
            thread = (await controller.native.rpc('thread/read', {'threadId': session}))['thread']
            if thread['status']['type'] != 'notLoaded':
                await controller.native.rpc('thread/backgroundTerminals/clean', {'threadId': session})
        await command('tmux', 'kill-session', '-t', '=' + old['tmux_session_name'], check=False)
        remaining = await command('tmux', 'has-session', '-t', '=' + old['tmux_session_name'], check=False)
        if remaining['exit_code'] == 0:
            raise RuntimeError('Project tmux session did not stop')
        if session:
            await controller.native.rpc('thread/unsubscribe', {'threadId': session})
            # The wrapper can register a final stop while its pane exits. Refresh
            # after quiescing; never rely on the scheduler's older cached records.
            await controller.cancel_wakes(project, refresh=True)
        save(controller, project, operation, 'quiesced')
    if kind == 'deploy':
        await deployment.finish(controller, project, operation)
        return
    if kind == 'rename':
        new = operation['new']
        if operation['phase'] == 'quiesced':
            current = json.loads((await command('gh', 'api', 'repositories/' + str(operation['repo_id'])))['stdout'])
            if not current['private'] or current['full_name'].lower() not in (old['github_repo'].lower(), new['github_repo'].lower()):
                raise ValueError('Repository changed outside the lifecycle operation')
            if current['full_name'] != new['github_repo']:
                await command('gh', 'api', 'repositories/' + str(operation['repo_id']),
                              '--method', 'PATCH', '-f', 'name=' + new['slug'])
            save(controller, project, operation, 'repository')
        if operation['phase'] == 'repository':
            source = owned_path(controller, project, old['project_path'])
            target = owned_path(controller, project, new['project_path'])
            move_owned(source, target, ident)
            await command('git', 'remote', 'set-url', 'origin', 'https://github.com/' + new['github_repo'] + '.git', cwd=target)
            save(controller, project, operation, 'directory')
        if operation['phase'] == 'directory':
            if session:
                await deployment.relocate_session(controller, {**project, **new})
                await controller.native.rpc('thread/name/set', {'threadId': session, 'name': new['display_name']})
            save(controller, project, operation, 'session')
        if operation['phase'] == 'session':
            item = await channel(controller, project)
            if item:
                await item.edit(name=new['slug'], reason='CodexPi user-confirmed project rename')
            save(controller, project, operation, 'channel')
        if operation['phase'] == 'channel':
            plan = controller.db.setting(deployment.key(project))
            if plan and plan.get('status') == 'active':
                await deployment.start(controller, {**project, **new}, plan)
            with controller.db.transaction():
                controller.db.update(ident, **new, lifecycle='ready', operation=None)
                controller.db.event(ident, 'renamed', {'from': old['display_name'], 'to': new['display_name']})
    elif kind == 'delete':
        if operation['phase'] == 'quiesced':
            if session:
                # 0.155.1 lists omit empty sessions, even with archived/source filters.
                # The exact native thread/read result still exposes its persisted rollout path.
                thread = (await controller.native.rpc('thread/read', {'threadId': session}))['thread']
                if not thread.get('path'):
                    raise RuntimeError('Native persisted session path is unavailable')
                if Path(thread['path']).parent.name != 'archived_sessions':
                    await controller.native.rpc('thread/archive', {'threadId': session})
                thread = (await controller.native.rpc('thread/read', {'threadId': session}))['thread']
                if Path(thread.get('path') or '').parent.name != 'archived_sessions':
                    raise RuntimeError('Native session archival could not be verified')
            save(controller, project, operation, 'session')
        if operation['phase'] == 'session':
            source = owned_path(controller, project, old['project_path'])
            backup = Path(operation['backup'])
            expected = controller.root / 'backups/deleted' / ident
            if backup != expected or backup.is_symlink() or backup.parent.is_symlink():
                raise ValueError('Unsafe recovery backup path')
            backup.mkdir(parents=True, exist_ok=True)
            atomic_write(backup / 'manifest.json', json.dumps({'project': old, 'deleted_at': time.time(),
                          'github_preserved': True, 'github_delete_requested': operation.get('delete_github', False),
                          'deployment': controller.db.setting(deployment.key(project))}, indent=2))
            move_owned(source, backup / 'project', ident)
            save(controller, project, operation, 'directory')
        if operation['phase'] == 'directory':
            if operation.get('delete_github'):
                await delete_repository(controller, old, operation)
                manifest_path = Path(operation['backup']) / 'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                manifest.update(github_preserved=False, github_deleted_at=time.time(), github_repo_id=operation['repo_id'])
                atomic_write(manifest_path, json.dumps(manifest, indent=2))
            save(controller, project, operation, 'repository')
        if operation['phase'] == 'repository':
            item = await channel(controller, project)
            if item:
                await item.delete(reason='CodexPi user-confirmed project deletion')
            save(controller, project, operation, 'channel')
        if operation['phase'] == 'channel':
            if controller.db.setting(deployment.key(project)):
                unit = deployment.unit_path(controller, project)
                unit.unlink(missing_ok=True)
                await command('systemctl', '--user', 'daemon-reload')
            with controller.db.transaction():
                if controller.db.setting('selected') == ident:
                    controller.db.set_setting('selected', None)
                controller.db.set_setting('deleted/' + ident, {'backup': operation['backup'], 'repo': old['github_repo'],
                    'github_deleted': operation.get('delete_github', False), 'repo_id': operation.get('repo_id')})
                controller.db.conn.execute('DELETE FROM projects WHERE project_id=?', (ident,))
                controller.db.conn.execute('DELETE FROM settings WHERE key=?', (deployment.key(project),))
                controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('manual_pause/' + ident,))
                controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('usage_wake/' + ident,))
                controller.db.conn.execute('DELETE FROM settings WHERE key IN (?,?,?,?)',
                                          ('prompts/' + ident, 'prompt_active/' + ident, 'prompt_receipts/' + ident,
                                           'prompt_limit/' + ident))
                controller.db.compact_queue()


async def recover(controller):
    for project in controller.db.all():
        operation = json.loads(project['operation'] or '{}')
        if operation.get('kind') not in ('rename', 'delete', 'deploy', 'close-channel', 'import') or operation.get('retry_at', 0) > time.time():
            continue
        try:
            if operation['kind'] == 'import':
                from .migration import finish as finish_import
                await finish_import(controller, project)
            else:
                await finish(controller, project)
        except Exception as exc:
            record_error(controller, project['project_id'], exc)
