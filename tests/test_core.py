import json
import contextlib
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import unittest

from app.common import SignedChannel, atomic_write, password_hash, password_valid, slugify
from app.db import Database


class CoreTests(unittest.TestCase):
    def test_native_unit_survives_child_oom_without_disabling_main_process_recovery(self):
        from configparser import ConfigParser
        unit = ConfigParser(interpolation=None, strict=False)
        unit.read(Path(__file__).resolve().parents[1] / 'config/codexpi-native.service')
        self.assertEqual(unit['Service']['OOMPolicy'], 'continue')
        self.assertEqual(unit['Service']['Restart'], 'always')
        self.assertEqual(unit['Service']['RestartSec'], '5')
        self.assertNotIn('MemoryMax', unit['Service'])

    def test_auth_and_replay(self):
        hashed = password_hash('test-only-password')
        self.assertTrue(password_valid('test-only-password', hashed))
        self.assertFalse(password_valid('wrong', hashed))
        key, challenge = secrets.token_hex(32), secrets.token_hex(32)
        worker = SignedChannel(key, challenge, 'worker')
        server = SignedChannel(key, challenge, 'controller')
        message = worker.sign({'type': 'alive'})
        tampered = json.loads(json.dumps(message))
        tampered['body']['type'] = 'job'
        with self.assertRaises(ValueError):
            server.verify(tampered)
        self.assertEqual(server.verify(message), {'type': 'alive'})
        with self.assertRaises(ValueError):
            server.verify(message)
        new_server = SignedChannel(key, secrets.token_hex(32), 'controller')
        with self.assertRaises(ValueError):
            new_server.verify(worker.sign({'type': 'alive'}))

    def test_db_constraints_rollback_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / 'state.db')
            self.assertEqual(db.conn.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(db.conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            for index in (1, 2):
                db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                  tmux_session_name,queue_position,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)''',
                  (str(index), str(index), str(index), f'/projects/{index}', str(index), index,
                   time.time(), time.time()))
            db.update('1', goal_status='active')
            db.set_setting('selected', '1')
            stamp, changes = db.get('1')['updated_at'], db.conn.total_changes
            db.update('1', goal_status='active', block_reason=None)
            db.set_setting('selected', '1')
            self.assertEqual(db.conn.total_changes, changes)
            self.assertEqual(db.get('1')['updated_at'], stamp)
            self.assertEqual(db.conn.execute('PRAGMA synchronous').fetchone()[0], 2)
            db.update('1', display_name='First')
            db.update('1', display_name='FIRST', block_reason='changed')
            self.assertEqual(db.get('1')['display_name'], 'FIRST')
            db.update('1', display_name='1', block_reason=None)
            self.assertIsNone(db.get('1')['block_reason'])
            with self.assertRaises(sqlite3.IntegrityError):
                db.update('2', goal_status='active')
            with self.assertRaises(ValueError):
                db.reorder(['1', '1'])
            db.reorder(['2', '1'])
            self.assertEqual(db.all()[0]['project_id'], '2')
            with self.assertRaises(RuntimeError):
                with db.transaction():
                    db.update('1', display_name='must-rollback')
                    raise RuntimeError('simulated crash before commit')
            self.assertEqual(db.get('1')['display_name'], '1')
            for _ in range(9):
                target = db.backup(Path(temp) / 'backups')
            self.assertEqual(len(list((Path(temp) / 'backups').glob('*.db'))), 7)
            with contextlib.closing(sqlite3.connect(target)) as restored:
                self.assertEqual(restored.execute('SELECT count(*) FROM projects').fetchone()[0], 2)
            db.conn.close()
            corrupt = Path(temp) / 'corrupt.db'
            atomic_write(corrupt, b'not a sqlite database')
            before = corrupt.read_bytes()
            with self.assertRaises(sqlite3.DatabaseError):
                Database(corrupt)
            self.assertEqual(corrupt.read_bytes(), before)

    def test_project_names(self):
        self.assertEqual(slugify('Military Radar'), 'military-radar')
        self.assertEqual(slugify('Straße'), 'strasse')
        for name in ('', '   ', '../', 'a\ncommand', 'x' * 81):
            with self.assertRaises(ValueError):
                slugify(name)


if __name__ == '__main__':
    unittest.main()
