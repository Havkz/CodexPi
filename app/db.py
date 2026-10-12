import contextlib
import json
from pathlib import Path
import sqlite3
import time

from .usage import number, windows


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
        if version > 4:
            raise RuntimeError('Database was created by a newer CodexPi version')
        if version == 0:
            with self.transaction():
                for statement in SCHEMA:
                    self.conn.execute(statement)
                self.conn.execute('PRAGMA user_version=1')
        if version < 2:
            with self.transaction():
                self.conn.execute('ALTER TABLE projects ADD COLUMN usage_limit TEXT')
                self.conn.execute('ALTER TABLE projects ADD COLUMN resume_result TEXT')
                self.conn.execute('PRAGMA user_version=2')
        if version < 3:
            with self.transaction():
                self.conn.execute('''CREATE TABLE usage_samples (
                    series TEXT NOT NULL, observed_at REAL NOT NULL,
                    remaining REAL NOT NULL CHECK(remaining BETWEEN 0 AND 100),
                    duration INTEGER NOT NULL, reset_at REAL,
                    PRIMARY KEY(series, observed_at)) WITHOUT ROWID''')
                self.conn.execute('PRAGMA user_version=3')
        if version < 4:
            with self.transaction():
                self.conn.execute('ALTER TABLE usage_samples RENAME TO legacy_usage_samples')
                self.conn.execute('''CREATE TABLE usage_samples (
                    account_id TEXT NOT NULL DEFAULT '', series TEXT NOT NULL, observed_at REAL NOT NULL,
                    remaining REAL NOT NULL CHECK(remaining BETWEEN 0 AND 100),
                    duration INTEGER NOT NULL, reset_at REAL,
                    PRIMARY KEY(account_id, series, observed_at)) WITHOUT ROWID''')
                # Legacy measurements remain unassigned until the original account is confirmed.
                self.conn.execute('INSERT INTO usage_samples SELECT ?,series,observed_at,remaining,duration,reset_at '
                                  'FROM legacy_usage_samples', ('',))
                self.conn.execute('DROP TABLE legacy_usage_samples')
                self.conn.execute('PRAGMA user_version=4')

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
        # Repeated native observations are not changes. Compare in SQLite so a
        # stale caller cannot skip a real transition; retain FULL durability.
        compared = {key: value for key, value in fields.items() if key != 'updated_at'}
        changed = ' OR '.join(f'{key} COLLATE BINARY IS NOT ?' for key in compared) or '1'
        fields['updated_at'] = time.time()
        sql = ','.join(f'{key}=?' for key in fields)
        self.conn.execute(f'UPDATE projects SET {sql} WHERE project_id=? AND ({changed})',
                          (*fields.values(), project_id, *compared.values()))

    def setting(self, key, default=None):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        self.conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value '
                          'WHERE settings.value IS NOT excluded.value',
                          (key, json.dumps(value)))

    def reorder(self, ids):
        rows = self.all()
        expected = {r['project_id'] for r in rows if r['queue_position'] is not None}
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError('Queue must include every queued project exactly once')
        with self.transaction():
            for position, project_id in enumerate(ids, 1):
                self.update(project_id, queue_position=position)

    def record_usage(self, account, account_id=None):
        stamp = account.get('checked_at')
        if not number(stamp) or stamp <= 0:
            raise ValueError('Usage observation requires a finite timestamp')
        active = self.setting('active_account', '')
        account_id = active if account_id is None else account_id
        snapshot = {**account, 'account_id': account_id} if account_id else account
        with self.transaction():
            if account_id:
                self.set_setting('account_usage/' + account_id, snapshot)
            if account_id == active:
                self.set_setting('account_usage', snapshot)
            for series, window in windows(account).items():
                previous = self.conn.execute('SELECT observed_at FROM usage_samples WHERE account_id=? AND series=? '
                    'ORDER BY observed_at DESC LIMIT 1', (account_id, series)).fetchone()
                # One real observation per minute, including while Unsnooze polls faster.
                # Clock rollback never rewrites an existing observation.
                if previous and stamp - previous[0] < 60:
                    continue
                self.conn.execute('INSERT INTO usage_samples VALUES (?,?,?,?,?,?)',
                    (account_id, series, stamp, window['remaining'], window['duration'], window['reset_at']))
            self.conn.execute('DELETE FROM usage_samples WHERE observed_at < ?', (stamp - 8 * 86400,))
            for series in ('daily', 'weekly'):
                self.conn.execute('DELETE FROM usage_samples WHERE account_id=? AND series=? AND observed_at IN '
                    '(SELECT observed_at FROM usage_samples WHERE account_id=? AND series=? '
                    'ORDER BY observed_at DESC LIMIT -1 OFFSET 12000)',
                    (account_id, series, account_id, series))

    def activate_account(self, account_id):
        with self.transaction():
            self.set_setting('active_account', account_id)
            cached = self.setting('account_usage/' + account_id, {})
            self.set_setting('account_usage', cached if cached.get('account_id') == account_id
                             else {'account_id': account_id, 'checked_at': None})

    def bind_legacy_usage(self, account_id):
        """Only after confirming the original single-account identity; never guess on switch."""
        if not account_id:
            raise ValueError('A confirmed original account is required')
        with self.transaction():
            if self.setting('legacy_usage_account'):
                if self.setting('legacy_usage_account') != account_id:
                    raise ValueError('Legacy history is already assigned to a different account')
                return
            self.conn.execute('UPDATE usage_samples SET account_id=? WHERE account_id=?', (account_id, ''))
            old = self.setting('account_usage', {})
            if old and not old.get('account_id'):
                self.set_setting('account_usage/' + account_id, {**old, 'account_id': account_id})
            self.set_setting('legacy_usage_account', account_id)

    def delete_account_usage(self, account_id):
        if not account_id or self.setting('active_account', '') == account_id:
            raise ValueError('Switch away from this account before removing it')
        with contextlib.nullcontext() if self.conn.in_transaction else self.transaction():
            self.conn.execute('DELETE FROM usage_samples WHERE account_id=?', (account_id,))
            self.conn.execute('DELETE FROM settings WHERE key=?', ('account_usage/' + account_id,))
            self.conn.execute('DELETE FROM settings WHERE key=?', ('account_telemetry/' + account_id,))

    def usage_history(self, now, account_id=None):
        account_id = self.setting('active_account', '') if account_id is None else account_id
        result = {}
        for series, span, bucket_seconds in (('daily', 86400, 300), ('weekly', 7 * 86400, 3600)):
            rows = [dict(row) for row in self.conn.execute(
                'SELECT observed_at,remaining,duration,reset_at FROM usage_samples '
                'WHERE account_id=? AND series=? AND observed_at BETWEEN ? AND ? ORDER BY observed_at',
                (account_id, series, now - span, now))]
            # Keep actual first/min/max/last observations, never averages/interpolated data.
            # Split outages before reducing so the chart cannot bridge missing measurements.
            groups, previous, segment = {}, None, 0
            for row in rows:
                if previous and (row['observed_at'] - previous['observed_at'] > 180 or row['duration'] != previous['duration']):
                    segment += 1
                row['segment'] = segment
                groups.setdefault((segment, int(row['observed_at'] // bucket_seconds)), []).append(row)
                previous = row
            kept = {}
            for group in groups.values():
                for row in (group[0], min(group, key=lambda r: r['remaining']),
                            max(group, key=lambda r: r['remaining']), group[-1]):
                    kept[row['observed_at']] = row
            result[series] = sorted(kept.values(), key=lambda r: r['observed_at'])
        return result

    def event(self, project_id, kind, payload):
        self.conn.execute('INSERT INTO events(project_id,kind,payload,created_at) VALUES (?,?,?,?)',
                          (project_id, kind, json.dumps(payload), time.time()))

    def compact_queue(self):
        for position, project in enumerate((p for p in self.all() if p['queue_position'] is not None), 1):
            self.update(project['project_id'], queue_position=position)

    def enqueue(self, project_id):
        if self.get(project_id)['queue_position'] is None:
            position = self.conn.execute('SELECT COALESCE(MAX(queue_position),0)+1 FROM projects').fetchone()[0]
            self.update(project_id, queue_position=position)

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
