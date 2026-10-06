"""Isolated infrastructure-DB restore drill on Pi; never starts or restores live services."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.common import atomic_write
from app.db import Database


def readonly(path, *, sealed=False):
    return sqlite3.connect(path.as_uri() + ('?immutable=1' if sealed else '?mode=ro'), uri=True)


def identities(db):
    fields = ('project_id', 'codex_session_id', 'project_path', 'github_repo',
              'discord_channel_id', 'tmux_session_name', 'queue_position', 'lifecycle', 'goal_status')
    projects = [tuple(row) for row in db.execute('SELECT ' + ','.join(fields) + ' FROM projects ORDER BY project_id')]
    settings = [tuple(row) for row in db.execute("SELECT key,value FROM settings WHERE key IN ('selected','pause_all') "
        "OR key LIKE 'manual_pause/%' OR key LIKE 'usage_wake/%' ORDER BY key")]
    return projects, settings


def services():
    return subprocess.check_output(['systemctl', '--user', 'show', 'codexpi', 'codexpi-native',
        'codexpi-unsnooze', '--property=MainPID,InvocationID,ActiveState'], text=True)


def main():
    if os.name != 'posix':
        raise RuntimeError('Run on the Pi; this verifier does not restore Windows credentials')
    os.umask(0o077)
    snapshots = sorted((ROOT / 'backups/sqlite').glob('codexpi-*.db'))
    if not snapshots:
        raise RuntimeError('No existing published SQLite snapshot')
    snapshot = snapshots[-1]
    wal = Path(str(snapshot) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Snapshot has WAL data; refuse an uncoordinated copy')
    original_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    before_services = services()
    with closing(readonly(snapshot, sealed=True)) as source, closing(readonly(ROOT / 'state/codexpi.db')) as live:
        expected = list(source.iterdump())
        source_identity = identities(source)
        if source_identity != identities(live):
            raise RuntimeError('Snapshot mappings/holds are stale; reconcile before any restore')
        with closing(readonly(Path.home() / '.codex/state_5.sqlite')) as native:
            for project in source_identity[0]:
                row = native.execute('SELECT cwd,rollout_path,archived FROM threads WHERE id=?', (project[1],)).fetchone()
                if not row or row[0] != project[2] or row[2] or not Path(row[1]).is_file():
                    raise RuntimeError('Native session/workspace/history does not match snapshot; reconcile first')
        if live.execute("SELECT 1 FROM projects WHERE operation IS NOT NULL OR lifecycle!='ready'").fetchone():
            raise RuntimeError('Pending lifecycle/resume operation; retry after it settles')
        if live.execute("SELECT 1 FROM jobs WHERE status IN ('pending','sent','running')").fetchone():
            raise RuntimeError('Unfinished Windows work; no coordinated restore claim possible')
        with tempfile.TemporaryDirectory(prefix='restore-drill-', dir=ROOT / 'state') as temp:
            target = Path(temp) / 'restored.db'
            shutil.copy2(snapshot, target)
            target.chmod(0o600)
            restored = Database(target)
            try:
                assert restored.conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert not restored.conn.execute('PRAGMA foreign_key_check').fetchall()
                assert list(restored.conn.iterdump()) == expected, 'Rows/schema changed during restored open'
                assert identities(restored.conn) == source_identity
                tables = {row[0]: restored.conn.execute('SELECT count(*) FROM "' + row[0].replace('"', '""') + '"').fetchone()[0]
                          for row in restored.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            finally:
                restored.conn.close()
        assert identities(live) == source_identity, 'Live mapping changed during drill; evidence invalid'
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == original_hash
    assert services() == before_services, 'Service changed during drill; inspect before acceptance'
    evidence = {'checked_at': time.time(), 'snapshot': str(snapshot.relative_to(ROOT)),
        'snapshot_sha256': original_hash, 'tables': tables, 'all_rows_and_schema_preserved': True,
        'integrity_and_foreign_keys': True, 'current_mapping_and_holds_match': True,
        'native_session_workspace_and_rollout_exist': True,
        'source_unchanged': True, 'service_processes_unchanged': True,
        'scope': 'Infrastructure SQLite restore only; no full-system/native/external recovery claim'}
    record = ROOT / 'state' / ('backup-restore-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    atomic_write(record, json.dumps(evidence, indent=2) + '\n', 0o600)
    print(json.dumps(evidence | {'record': str(record.relative_to(ROOT))}, indent=2))


if __name__ == '__main__':
    main()
