"""Export one explicitly selected Windows project/session without changing it.

The private archive contains Git state, uncommitted/ignored project data, the
original native rollout and goal row. Never publish it to GitHub. Runtime/build
caches are enumerated as omissions; symlinks and changing sources fail closed.
"""
import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CACHES = {'.venv', 'venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'node_modules',
          'build', 'dist', '.mypy_cache'}


def git(project, *args):
    return subprocess.check_output(['git', '-C', str(project), *args],
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).decode('utf-8').rstrip('\r\n')


def regular(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f'Reparse point/symlink needs explicit migration handling: {path}')
    return info


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def native_state(codex_root, session_id):
    """Keep only this thread's indexed history/metadata, never another thread."""
    result = {}
    for filename, tables in {
        'thread_history_1.sqlite': {'thread_turns': 'thread_id', 'thread_items': 'thread_id',
            'thread_history_projection_state': 'thread_id', 'thread_realtime_items': 'thread_id'},
        'state_5.sqlite': {'threads': 'id', 'thread_dynamic_tools': 'thread_id',
                         'thread_attachments': 'thread_id'},
    }.items():
        path = codex_root / filename
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            result[filename] = {table: [dict(r) for r in db.execute(
                f'SELECT * FROM {table} WHERE {key}=?', (session_id,))]
                for table, key in tables.items() if table in present}
    return result


def export(project, session_id, codex_root, destination, references=()):
    session_id = str(uuid.UUID(session_id))
    project = project.resolve(strict=True)
    destination = destination.resolve()
    if project == Path.home().resolve() or project == Path(project.anchor):
        raise ValueError('Select the actual project, not a home or drive root')
    if destination.is_relative_to(project):
        raise ValueError('Keep the private export outside the source project')
    regular(project)
    regular(project / '.git')
    if not (project / '.git').is_dir() or git(project, 'rev-parse', '--show-toplevel').replace('\\', '/').lower() != project.as_posix().lower():
        raise ValueError('A standalone Git project is required')
    for name in ('index.lock', 'objects/info/alternates'):
        if (project / '.git' / name).exists():
            raise ValueError('Git is busy or references an external object store')
    rollouts = [p for directory in ('sessions', 'archived_sessions')
                for p in (codex_root / directory).rglob('*' + session_id + '.jsonl')]
    if len(rollouts) != 1:
        raise ValueError('Expected exactly one original native rollout')
    rollout = rollouts[0]
    with rollout.open(encoding='utf-8') as stream:
        metadata = json.loads(next(stream))['payload']
    if metadata['id'] != session_id:
        raise ValueError('Native rollout identity mismatch')
    with closing(sqlite3.connect((codex_root / 'goals_1.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM thread_goals WHERE thread_id=?', (session_id,)).fetchone()
        goal = dict(row) if row else None
    if goal and goal['status'] == 'active':
        raise ValueError('Pause this Windows goal before exporting; do not run it on both hosts')
    indexed_state = native_state(codex_root, session_id)
    before = {key: git(project, *args) for key, args in {
        'head': ('rev-parse', 'HEAD'), 'branch': ('branch', '--show-current'),
        'status': ('status', '--porcelain=v1', '--untracked-files=all'),
        'origin': ('remote', 'get-url', 'origin')}.items()}
    files, omitted = [], []
    for parent, directories, names in os.walk(project, followlinks=False):
        parent = Path(parent)
        for name in list(directories):
            path = parent / name
            regular(path)
            if '.git' not in path.relative_to(project).parts and (name in CACHES or name.endswith('.egg-info')):
                directories.remove(name)
                omitted.append({'path': path.relative_to(project).as_posix(), 'reason': 'regenerable runtime/build cache'})
        for name in sorted(names):
            path = parent / name
            regular(path)
            if not path.is_file():
                raise ValueError(f'Non-regular source file: {path}')
            files.append((path, 'project/' + path.relative_to(project).as_posix()))
    files.append((rollout, 'native/' + rollout.name))
    for number, path in enumerate(references):
        path = path.resolve(strict=True)
        regular(path)
        if not path.is_file():
            raise ValueError('References must be explicit files')
        files.append((path, f'references/{number:03d}-' + path.name))
    for name in ('AGENTS.md', '.codex/RTK.md'):
        path = Path.home() / name
        if path.is_file():
            regular(path)
            files.append((path, 'instructions/' + path.name))
    names = [name for _, name in files]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate archive name')
    # Refuse raw copies of live databases. Add SQLite backup handling when a
    # selected project actually contains one; never silently omit its state.
    for path, _ in files:
        if path.suffix.lower() in ('.db', '.sqlite', '.sqlite3'):
            raise ValueError(f'Project database needs a consistent snapshot before export: {path}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'session_id': session_id, 'source_project': str(project),
        'source_rollout': str(rollout), 'session_metadata': metadata, 'original_goal': goal,
        'git': before, 'omitted': omitted, 'files': [], 'created_at': time.time(),
        'limitations': ['Running processes, terminal state and provider-side caches are not exported.',
                       'Windows runtime/build caches must be recreated on the target.',
                       'Only listed project files and explicitly selected external references are included.']}
    snapshots = []
    # Exclusive creation leaves a failed partial archive for inspection, never
    # overwrites an earlier successful export or any source data.
    with destination.open('xb') as output:
        os.chmod(destination, 0o600)
        with tarfile.open(fileobj=output, mode='w:gz', compresslevel=1) as archive:
            for path, name in sorted(files, key=lambda item: item[1]):
                info = regular(path)
                sha = digest(path)
                archive.add(path, arcname=name, recursive=False)
                after = regular(path)
                if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or digest(path) != sha:
                    raise ValueError(f'Source changed during export: {path}')
                snapshots.append((path, info.st_size, info.st_mtime_ns))
                manifest['files'].append({'path': name, 'bytes': info.st_size, 'sha256': sha,
                                          'source': str(path)})
            payload = json.dumps(indexed_state, ensure_ascii=False).encode()
            entry = tarfile.TarInfo('native/indexed-state.json')
            entry.size, entry.mode = len(payload), 0o600
            archive.addfile(entry, io.BytesIO(payload))
            manifest['files'].append({'path': entry.name, 'bytes': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest(), 'source': 'selected-thread SQLite snapshots'})
            for path, size, modified in snapshots:
                current = regular(path)
                if (current.st_size, current.st_mtime_ns) != (size, modified):
                    raise ValueError(f'Source changed before export finished: {path}')
            if git(project, 'rev-parse', 'HEAD') != before['head'] or git(project, 'status', '--porcelain=v1', '--untracked-files=all') != before['status']:
                raise ValueError('Git state changed during export')
            with closing(sqlite3.connect((codex_root / 'goals_1.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute('SELECT * FROM thread_goals WHERE thread_id=?', (session_id,)).fetchone()
                if (dict(row) if row else None) != goal:
                    raise ValueError('Native Windows goal changed during export')
            payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            entry = tarfile.TarInfo('manifest.json')
            entry.size, entry.mode = len(payload), 0o600
            archive.addfile(entry, io.BytesIO(payload))
        output.flush()
        os.fsync(output.fileno())
    expected = {item['path']: item['sha256'] for item in manifest['files']}
    with tarfile.open(destination, mode='r|gz') as archive:
        for member in archive:
            if member.name == 'manifest.json':
                continue
            with archive.extractfile(member) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected.pop(member.name):
                    raise ValueError('Archive content does not match source manifest')
    if expected:
        raise ValueError('Archive is missing source files')
    return {'archive': str(destination), 'sha256': digest(destination), 'files': len(manifest['files']),
            'bytes': destination.stat().st_size, 'head': before['head'], 'session_id': session_id,
            'original_goal_status': goal['status'] if goal else None, 'omitted': omitted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('--codex-root', type=Path, default=Path.home() / '.codex')
    parser.add_argument('--reference', action='append', type=Path, default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.project, args.session, args.codex_root, args.output, args.reference), indent=2))


if __name__ == '__main__':
    main()
