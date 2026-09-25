import contextlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.db import Database
from app.usage import windows


def account(stamp, daily=25, weekly=60, reset=2000000):
    return {'checked_at': stamp, 'rateLimits': {'limitId': 'codex',
        'primary': {'usedPercent': daily, 'windowDurationMins': 300, 'resetsAt': reset},
        'secondary': {'usedPercent': weekly, 'windowDurationMins': 10080, 'resetsAt': reset + 86400}}}


class UsageTests(unittest.TestCase):
    def test_windows_are_remaining_not_used_and_unknown_never_means_full(self):
        self.assertEqual(windows(account(1, 100, 0))['daily']['remaining'], 0)
        self.assertEqual(windows(account(1, 100, 0))['weekly']['remaining'], 100)
        for invalid in (None, True, '20', -1, 101, float('nan'), float('inf')):
            self.assertNotIn('daily', windows(account(1, invalid)))
        for limits in (None, [], 'unknown', {'primary': 'bad'}, {'limitId': 'reviews'}):
            self.assertEqual(windows({'rateLimits': limits}), {})
        snapshot = account(1)
        snapshot['rateLimits']['primary']['windowDurationMins'] = 60
        self.assertNotIn('daily', windows(snapshot))
        snapshot['rateLimits']['primary']['windowDurationMins'] = 1440
        snapshot['rateLimits']['primary']['resetsAt'] = 'unknown'
        self.assertIsNone(windows(snapshot)['daily']['reset_at'])

    def test_migration_sampling_restart_backup_retention_and_truthful_reduction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.db'
            db = Database(path)
            # Exercise the actual v2 -> v3 migration without changing project data.
            db.set_setting('keep', 'unchanged')
            db.conn.execute('DROP TABLE usage_samples')
            db.conn.execute('PRAGMA user_version=2')
            db.conn.close()
            db = Database(path)
            self.assertEqual(db.setting('keep'), 'unchanged')
            start = 1800000
            for offset, used in [(0, 20), (60, 30), (120, 100), (180, 0), (240, 5), (300, 10), (900, 11)]:
                db.record_usage(account(start + offset, used))
            db.record_usage(account(start + 901, 12))  # Throttled, not a synthetic sample.
            db.record_usage(account(start + 899, 13))  # Clock rollback cannot rewrite history.
            rows = db.usage_history(start + 901)['daily']
            self.assertEqual([r['remaining'] for r in rows[:4]], [80, 0, 100, 95])
            self.assertNotEqual(rows[-1]['segment'], rows[-2]['segment'])  # Outage not joined.
            self.assertTrue(all(r['remaining'] in (80, 70, 0, 100, 95, 90, 89) for r in rows))
            self.assertEqual(db.conn.execute('SELECT count(*) FROM usage_samples').fetchone()[0], 14)
            db.conn.close()
            db = Database(path)
            self.assertEqual(db.usage_history(start + 901)['daily'], rows)
            backup = db.backup(Path(directory) / 'backups')
            with contextlib.closing(sqlite3.connect(backup)) as saved:
                self.assertEqual(saved.execute('SELECT count(*) FROM usage_samples').fetchone()[0], 14)
            # A reset time passing is not evidence of a refill. Only supplied observations count.
            db.record_usage(account(start + 960, 100, reset=start))
            self.assertEqual(db.usage_history(start + 1000)['daily'][-1]['remaining'], 0)
            db.record_usage({'checked_at': start + 1200, 'rateLimits': None})
            self.assertEqual(db.usage_history(start + 1300)['daily'][-1]['remaining'], 0)
            with self.assertRaises(ValueError):
                db.record_usage(account(float('nan')))
            # Hard count ceiling even for existing too-dense input; age retention also applies.
            now = start + 10 * 86400
            with db.transaction():
                db.conn.executemany('INSERT INTO usage_samples VALUES (?,?,?,?,?)',
                    [('weekly', now - n, n % 101, 10080, now + 86400) for n in range(1, 12010)])
            db.record_usage(account(now))
            self.assertEqual(db.conn.execute("SELECT count(*) FROM usage_samples WHERE series='weekly'").fetchone()[0], 12000)
            self.assertGreaterEqual(db.conn.execute('SELECT min(observed_at) FROM usage_samples').fetchone()[0], now - 8 * 86400)
            reduced = db.usage_history(now)['weekly']
            self.assertLess(len(reduced), 24)
            self.assertTrue(all('segment' in row for row in reduced))
            self.assertLess(len(json.dumps(db.usage_history(now))), 8000)
            db.conn.close()


if __name__ == '__main__':
    unittest.main()
