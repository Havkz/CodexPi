"""Explicit, journaled import of one private Windows project/native session.

No model turn is started. Original bytes remain in the checksummed archive;
native DB inserts are scoped to a previously absent, manually held thread.
"""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tarfile
import time
import uuid

from .common import atomic_write, slugify
from .controller import command
from .native import project_thread_config


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_archive(path, expected):
    if not re.fullmatch('[a-f0-9]{64}', expected) or digest(path) != expected:
        raise ValueError('Migration archive checksum mismatch')
    with tarfile.open(path) as archive:
        names = set()
        for member in archive:
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or '..' in name.parts
                    or '\\' in member.name or ':' in member.name or member.name in names
                    or str(name) != member.name):
                raise ValueError('Unsafe or duplicate migration archive member')
            names.add(member.name)
        manifest = json.load(archive.extractfile('manifest.json'))
        entries = manifest['files']
        if (manifest['format'] != 1 or len({e['path'] for e in entries}) != len(entries)
                or names != {'manifest.json', *(e['path'] for e in entries)}):
            raise ValueError('Migration manifest member mismatch')
        for entry in entries:
            if (PurePosixPath(entry['path']).parts[0] not in ('project', 'native', 'references', 'instructions')
                    or archive.getmember(entry['path']).size != entry['bytes']):
                raise ValueError('Invalid migration file metadata')
            with archive.extractfile(entry['path']) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                    raise ValueError('Migration member checksum mismatch')
    if str(uuid.UUID(manifest['session_id'])) != manifest['session_id']:
        raise ValueError('Invalid migration session ID')
    if (manifest.get('original_goal') or {}).get('status') == 'active':
        raise ValueError('The original Windows goal must not be active')
    if any(e['path'].startswith('project/.codexpi/') for e in entries):
        raise ValueError('Already-managed project needs a separate ownership transfer')
    return manifest


def extract_project(archive_path, manifest, target, ident):
    # An incomplete staging directory is retained for inspection. Retrying uses
    # a fresh unique directory; no recursive delete or overwrite is needed.
    stage = target.parent / ('.import-' + ident + '-' + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    with tarfile.open(archive_path) as archive:
        for entry in manifest['files']:
            parts = PurePosixPath(entry['path']).parts
            relative = Path(*parts[1:]) if parts[0] == 'project' else Path('.codexpi/migration', *parts)
            out = stage / relative
            out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.extractfile(entry['path']) as source, out.open('xb') as dest:
                shutil.copyfileobj(source, dest)
                dest.flush()
                os.fsync(dest.fileno())
            out.chmod(0o600)
            if digest(out) != entry['sha256']:
                raise ValueError('Extracted migration bytes mismatch')
    atomic_write(stage / '.codexpi/project-id', ident)
    atomic_write(stage / '.codexpi/migration/manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    if os.name == 'posix':
        for directory, _, _ in os.walk(stage, topdown=False):
            fd = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    if target.exists() or target.is_symlink():
        raise ValueError('Migration target already exists')
    stage.rename(target)
    if os.name == 'posix':
        fd = os.open(target.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def verify_project_files(manifest, path):
    for entry in manifest['files']:
        if entry['path'].startswith('project/.git/'):
            continue  # Git validates its objects; local config/index are adapted.
        parts = PurePosixPath(entry['path']).parts
        source = path.joinpath(*parts[1:]) if parts[0] == 'project' else path.joinpath('.codexpi/migration', *parts)
        if not source.is_file() or digest(source) != entry['sha256']:
            raise ValueError('Migrated file differs from original archive: ' + entry['path'])


def restore_native(manifest, project, codex_root):
    """Insert only absent selected-thread rows. Never replace a live DB/file."""
    sid = manifest['session_id']
    private = Path(project['project_path']) / '.codexpi/migration'
    source = private / 'native' / Path(manifest['source_rollout'].replace('\\', '/')).name
    with source.open() as stream:
        if json.loads(next(stream))['payload']['id'] != sid:
            raise ValueError('Native rollout identity mismatch')
    target = codex_root / 'sessions/migrated' / source.name
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not target.exists():
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        target.chmod(0o600)
    elif digest(target) != digest(source):
        raise ValueError('Native migration rollout already exists with different content')
    snapshots = json.loads((private / 'native/indexed-state.json').read_text())
    # The state_5 index is rebuilt by native thread/resume with Linux cwd and
    # enforced permissions. Its original row remains in the private snapshot.
    snapshots = {'thread_history_1.sqlite': snapshots.get('thread_history_1.sqlite', {})}
    goal = manifest.get('original_goal')
    if goal:
        snapshots['goals_1.sqlite'] = {'thread_goals': [{**goal, 'status': 'paused'}]}
    allowed = {'thread_goals', 'thread_turns', 'thread_items',
               'thread_history_projection_state', 'thread_realtime_items'}
    compatibility = {}
    for filename, tables in snapshots.items():
        with closing(sqlite3.connect(codex_root / filename, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            for table, rows in tables.items():
                if table not in allowed:
                    raise ValueError('Unexpected native migration table')
                if not rows:
                    continue
                columns = list(rows[0])
                actual = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                missing = set(columns) - actual
                optional = {'started_at_ms', 'completed_at_ms'} if table == 'thread_items' else set()
                if not missing <= optional or any(r.get('thread_id') != sid for r in rows):
                    raise ValueError('Native migration schema/identity mismatch')
                if missing:
                    # Display timing fields added by newer Windows builds are
                    # retained verbatim in indexed-state.json. Never alter an
                    # upstream-owned schema or discard any item_json/history.
                    compatibility[table] = {'snapshot_only_columns': sorted(missing)}
                    columns = [column for column in columns if column in actual]
                    rows = [{key: row[key] for key in columns} for row in rows]
                existing = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE thread_id=?', (sid,))]
                if existing:
                    projected = [{key: r[key] for key in columns} for r in existing]
                    if sorted(map(lambda r: json.dumps(r, sort_keys=True), projected)) != sorted(map(lambda r: json.dumps(r, sort_keys=True), rows)):
                        raise ValueError('Native migration would overwrite existing thread data')
                    continue
                db.executemany(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                               [tuple(row[c] for c in columns) for row in rows])
            db.commit()
    atomic_write(private / 'compatibility.json', json.dumps(compatibility, indent=2))
    return target


async def request(controller, data):
    async with controller.lock:
        path = Path(data['archive'])
        base = (controller.root / 'backups/migrations').resolve()
        if path.is_symlink() or path.resolve().parent != base or not path.is_file():
            raise ValueError('Import requires a private archive in backups/migrations')
        manifest = await asyncio.to_thread(inspect_archive, path, data['sha256'])
        sid = manifest['session_id']
        existing = controller.db.by_session(sid)
        if existing:
            journal = controller.db.setting('migration/' + existing['project_id'], {})
            if journal.get('sha256') != data['sha256']:
                raise ValueError('Session already mapped to another import')
            if existing['lifecycle'] == 'ready':
                return existing
            await finish(controller, existing)
            return controller.db.get(existing['project_id'])
        if any(p['goal_status'] == 'active' or p['operation'] for p in controller.db.all()):
            raise ValueError('Wait for active work/lifecycle operations before migration')
        codex_root = Path.home() / '.codex'
        for folder in ('sessions', 'archived_sessions'):
            if any((codex_root / folder).rglob('*' + sid + '.jsonl')):
                raise ValueError('Native session already exists on this Pi')
        if sid in controller.source.rows():
            raise ValueError('Native goal already exists on this Pi')
        name, ident = data['name'].strip(), str(uuid.uuid4())
        slug = slugify(name)
        target = controller.root / 'projects' / slug
        if target.exists() or target.is_symlink():
            raise ValueError('Migration project path already exists')
        origin = manifest['git']['origin']
        match = re.fullmatch(r'https://github\.com/([^/]+/[^/]+)\.git', origin)
        if not match or match[1].split('/')[0].lower() != controller.config['github_account'].lower():
            raise ValueError('Import must explicitly link an owned GitHub repository')
        repo = json.loads((await command('gh', 'api', 'repos/' + match[1]))['stdout'])
        if not repo['private'] or not repo.get('permissions', {}).get('admin'):
            raise ValueError('Import requires an owned private GitHub repository')
        if not controller.bot or not controller.bot.is_ready():
            raise ValueError('Discord is not connected')
        controller.db.backup(controller.root / 'backups/sqlite')
        operation = {'kind': 'import', 'phase': 'prepared', 'archive': str(path),
                     'sha256': data['sha256'], 'repo_id': repo['id'],
                     'original_description': repo['description'], 'requested_at': time.time()}
        with controller.db.transaction():
            controller.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                tmux_session_name,codex_session_id,github_repo,queue_position,lifecycle,operation,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (ident, name, slug, str(target), 'codexpi-' + slug,
                sid, match[1], max([p['queue_position'] or 0 for p in controller.db.all()] + [0]) + 1,
                'importing', json.dumps(operation), time.time(), time.time()))
            controller.db.set_setting('manual_pause/' + ident, True)
            controller.db.set_setting('migration/' + ident, operation)
        await finish(controller, controller.db.get(ident))
        return controller.db.get(ident)


async def finish(controller, project):
    from .lifecycle import save
    ident, path = project['project_id'], Path(project['project_path'])
    operation = json.loads(project['operation'])
    archive = Path(operation['archive'])
    manifest = await asyncio.to_thread(inspect_archive, archive, operation['sha256'])
    if operation['phase'] == 'prepared':
        if not path.exists():
            await asyncio.to_thread(extract_project, archive, manifest, path, ident)
        elif (path / '.codexpi/project-id').read_text() != ident:
            raise ValueError('Migration directory ownership mismatch')
        await asyncio.to_thread(verify_project_files, manifest, path)
        head = (await command('git', 'rev-parse', 'HEAD', cwd=path))['stdout'].strip()
        if head != manifest['git']['head']:
            raise ValueError('Migrated Git HEAD mismatch')
        await command('git', 'fsck', '--full', cwd=path)
        # Windows exports cannot express POSIX execute bits. Restore only the
        # executable regular files recorded by this project's original Git index.
        index = (await command('git', 'ls-files', '--stage', '-z', cwd=path))['stdout']
        for entry in index.split('\0'):
            if entry.startswith('100755 '):
                tracked = path / entry.split('\t', 1)[1]
                if not tracked.resolve().is_relative_to(path.resolve()) or not tracked.is_file() or tracked.is_symlink():
                    raise ValueError('Unsafe executable index path during migration')
                tracked.chmod(0o700)
        # Exclude management metadata locally without changing the source tree.
        exclude = path / '.git/info/exclude'
        original = exclude.read_text() if exclude.exists() else ''
        if '\n.codexpi/\n' not in original:
            atomic_write(exclude, original + '\n.codexpi/\n')
        status_args = ('status', '--porcelain=v1', '--untracked-files=all')
        status = (await command('git', *status_args, cwd=path))['stdout'].rstrip('\r\n')
        if status != manifest['git']['status']:
            # Git-for-Windows often inherits autocrlf from system/global config,
            # which is deliberately not copied over the Pi's account config.
            # Probe without changing a single worktree byte; accept only the
            # exact original dirty/index state, then scope the setting locally.
            for setting in ('true', 'input', 'false'):
                probe = (await command('git', '-c', 'core.autocrlf=' + setting,
                                       *status_args, cwd=path))['stdout'].rstrip('\r\n')
                if probe == manifest['git']['status']:
                    await command('git', 'config', '--local', 'core.autocrlf', setting, cwd=path)
                    break
            else:
                raise ValueError('Migrated dirty/index state does not match Windows source')
        save(controller, project, operation, 'directory')
    if operation['phase'] == 'directory':
        rollout = await asyncio.to_thread(restore_native, manifest, project, Path.home() / '.codex')
        # Persist before loading: recovery must not reinsert derived history after
        # native resume has legitimately appended to the original rollout.
        operation['rollout'] = str(rollout)
        save(controller, project, operation, 'native-data')
    if operation['phase'] == 'native-data':
        result = await controller.native.rpc('thread/resume', {'threadId': manifest['session_id'],
            'path': operation['rollout'], 'cwd': str(path), 'runtimeWorkspaceRoots': [str(path)],
            'excludeTurns': True, 'approvalPolicy': 'never', 'sandbox': 'workspace-write',
            'config': project_thread_config(path)})
        if result['thread']['id'] != manifest['session_id'] or result['thread']['cwd'] != str(path):
            raise ValueError('Native session identity/cwd restoration failed')
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': manifest['session_id']})).get('goal')
        if manifest.get('original_goal') and (not goal or goal['status'] != 'paused'
                or goal['objective'] != manifest['original_goal']['objective']):
            raise ValueError('Original native goal restoration failed')
        # Real history is not rewritten. This new, explicit migration context
        # maps source paths and adds the existing CodexPi operating rules.
        context = ('This existing Windows session was migrated to CodexPi, retaining its native ID and history. '
            'The current project root is ' + str(path) + '. Original root: ' + manifest['source_project'] + '. '
            'Original referenced inputs, goal and metadata are in .codexpi/migration/manifest.json; '
            'use its source-to-path mapping for Windows-only paths. The goal is intentionally manually paused. '
            'Past usage-limit status is historical, not a fresh account observation. '
            'Do not run live trading or broaden previous user authorization. '
            'Windows processes, credentials outside listed files, and provider-side caches are not transferred.\n\n'
            + (controller.root / 'templates/AGENTS.md').read_text())
        await controller.native.rpc('thread/inject_items', {'threadId': manifest['session_id'], 'items': [{
            'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': context}]}]})
        await controller.native.rpc('thread/name/set', {'threadId': manifest['session_id'], 'name': project['display_name']})
        await controller.native.rpc('thread/unsubscribe', {'threadId': manifest['session_id']})
        save(controller, project, operation, 'session')
    if operation['phase'] == 'session':
        await asyncio.to_thread(verify_project_files, manifest, path)
        repo = json.loads((await command('gh', 'api', 'repositories/' + str(operation['repo_id'])))['stdout'])
        marker = 'Managed by CodexPi project ' + ident
        if (not repo['private'] or repo['full_name'].lower() != project['github_repo'].lower()
                or repo['description'] not in (operation['original_description'], marker)):
            raise ValueError('Migration repository changed outside this operation')
        if repo['description'] != marker:
            await command('gh', 'api', 'repositories/' + str(operation['repo_id']), '--method', 'PATCH', '-f', 'description=' + marker)
        channel = await controller.bot.ensure_channel(project)
        controller.db.update(ident, discord_channel_id=str(channel.id))
        await controller.cancel_wakes(project, refresh=True)
        with controller.db.transaction():
            controller.db.update(ident, lifecycle='ready', goal_status='paused', operation=None,
                                 last_commit=manifest['git']['head'])
            controller.db.set_setting('migration/' + ident, {**operation, 'phase': 'complete',
                'verified_at': time.time(), 'original_goal_status': (manifest.get('original_goal') or {}).get('status')})
            controller.db.event(ident, 'imported', {'session_id': manifest['session_id'], 'sha256': operation['sha256']})
