import contextlib
import json
from pathlib import Path
import sqlite3
import time


SCHEMA = (
    '''CREATE TABLE projects (
        project_id TEXT PRIMARY KEY, display_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        slug TEXT NOT NULL UNIQUE, project_path TEXT NOT NULL UNIQUE,
        codex_session_id TEXT UNIQUE, tmux_session_name TEXT NOT NULL UNIQUE,
        github_repo TEXT UNIQUE, discord_channel_id TEXT UNIQUE, queue_position INTEGER,
        goal_status TEXT NOT NULL DEFAULT 'paused' CHECK(goal_status IN
          ('active','paused','stalled','usage limited','limited by budget','complete')),
        block_reason TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        last_commit TEXT, last_ci_status TEXT, windows_required INTEGER NOT NULL DEFAULT 0,
        last_activity REAL, lifecycle TEXT NOT NULL DEFAULT 'creating',
        operation TEXT, completion_notified INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE UNIQUE INDEX one_active_goal ON projects ((1)) WHERE goal_status='active' ''',
    '''CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)''',
    '''CREATE TABLE sessions (id_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL,
        expires REAL NOT NULL)''',
    '''CREATE TABLE login_attempts (address TEXT PRIMARY KEY, failures INTEGER NOT NULL,
        window_start REAL NOT NULL)''',
    '''CREATE TABLE events (event_id INTEGER PRIMARY KEY, project_id TEXT,
        kind TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
        sent_at REAL, FOREIGN KEY(project_id) REFERENCES projects ON DELETE CASCADE)''',
    '''CREATE TABLE jobs (job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
        payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        result TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects ON DELETE CASCADE)''',
)


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        self.conn.row_factory = sqlite3.Row
        try:
            integrity = self.conn.execute('PRAGMA integrity_check').fetchone()[0]
        except sqlite3.DatabaseError:
            self.conn.close()
            raise
        if integrity != 'ok':
            self.conn.close()
            raise RuntimeError('SQLite integrity check failed; refusing to overwrite database')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA synchronous=FULL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        version = self.conn.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise RuntimeError('Database was created by a newer CodexPi version')
        if version == 0:
            with self.transaction():
                for statement in SCHEMA:
                    self.conn.execute(statement)
                self.conn.execute('PRAGMA user_version=1')

    @contextlib.contextmanager
    def transaction(self):
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.conn.execute('COMMIT')
        except BaseException:
            self.conn.execute('ROLLBACK')
            raise

    def all(self):
        return [dict(r) for r in self.conn.execute(
            'SELECT * FROM projects ORDER BY queue_position IS NULL,queue_position,created_at')]

    def get(self, project_id):
        row = self.conn.execute('SELECT * FROM projects WHERE project_id=?', (project_id,)).fetchone()
        if row is None:
            raise KeyError('Unknown project')
        return dict(row)

    def by_session(self, session_id):
        row = self.conn.execute('SELECT * FROM projects WHERE codex_session_id=?', (session_id,)).fetchone()
        return dict(row) if row else None

    def update(self, project_id, **fields):
        columns = {row[1] for row in self.conn.execute('PRAGMA table_info(projects)')}
        if not fields or not set(fields) <= columns - {'project_id', 'created_at'}:
            raise ValueError('Invalid project update')
        fields['updated_at'] = time.time()
        sql = ','.join(f'{key}=?' for key in fields)
        self.conn.execute(f'UPDATE projects SET {sql} WHERE project_id=?', (*fields.values(), project_id))

    def setting(self, key, default=None):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        self.conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                          (key, json.dumps(value)))

    def reorder(self, ids):
        rows = self.all()
        expected = {r['project_id'] for r in rows if r['queue_position'] is not None}
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError('Queue must include every queued project exactly once')
        with self.transaction():
            for position, project_id in enumerate(ids, 1):
                self.update(project_id, queue_position=position)

    def event(self, project_id, kind, payload):
        self.conn.execute('INSERT INTO events(project_id,kind,payload,created_at) VALUES (?,?,?,?)',
                          (project_id, kind, json.dumps(payload), time.time()))

    def backup(self, directory, keep=7):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (time.strftime('codexpi-%Y%m%d-%H%M%S-') + str(time.time_ns()) + '.db')
        temp = target.with_suffix('.tmp')
        try:
            with contextlib.closing(sqlite3.connect(temp)) as backup:
                self.conn.backup(backup)
                if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed')
            import os
            with temp.open('r+b') as handle:
                os.fsync(handle.fileno())
            os.replace(temp, target)
            if os.name == 'posix':
                fd = os.open(directory, os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if temp.exists():
                temp.unlink()
        for old in sorted(directory.glob('codexpi-*.db'), reverse=True)[keep:]:
            old.unlink()
        return target
