import base64
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from app.accounts import AccountVault, auth_identity
from app.common import atomic_write
from app.db import Database
from tests.test_usage import account


def login(user, token='test-access-token'):
    claims = base64.urlsafe_b64encode(json.dumps({'sub': user, 'email': user + '@example.test'}).encode()).decode().rstrip('=')
    return json.dumps({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                      'tokens': {'id_token': 'header.' + claims + '.signature', 'access_token': token,
                                 'refresh_token': 'test-refresh-token', 'account_id': 'workspace'}})


class AccountTests(unittest.TestCase):
    def test_private_slots_refresh_identity_and_do_not_copy_sessions_or_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / 'codex-home'
            atomic_write(codex_home / 'config.toml', 'unrelated = true\n')
            atomic_write(codex_home / 'sessions/history.jsonl', 'preserve native history\n')
            first, second = login('first'), login('second')
            atomic_write(codex_home / 'auth.json', first)
            vault = AccountVault(root, codex_home)
            one = vault.checkpoint({'type': 'chatgpt', 'email': 'first@example.test', 'planType': 'plus'})
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                vault.checkpoint({'type': 'chatgpt'}, expected_id='0' * 64)
            atomic_write(codex_home / 'auth.json', second)
            two = vault.checkpoint({'type': 'chatgpt', 'email': 'second@example.test'})
            self.assertNotEqual(one['account_id'], two['account_id'])
            vault.install(one['account_id'])
            self.assertEqual((codex_home / 'auth.json').read_text(), first)
            refreshed = login('first', 'new-test-access-token')
            atomic_write(codex_home / 'auth.json', refreshed)
            vault.checkpoint({'type': 'chatgpt'}, expected_id=one['account_id'])
            self.assertEqual(vault.path(one['account_id']).read_text(), refreshed)
            self.assertNotIn('token', json.dumps(one))
            self.assertEqual((codex_home / 'config.toml').read_text(), 'unrelated = true\n')
            self.assertEqual((codex_home / 'sessions/history.jsonl').read_text(), 'preserve native history\n')
            for bad in ('../auth', '', None, 'a' * 65):
                with self.assertRaises(ValueError):
                    vault.path(bad)
            for bad in (b'not-json', b'{}', b'[]'):
                with self.assertRaisesRegex(ValueError, 'sign in again'):
                    auth_identity(bad)
            atomic_write(vault.path(one['account_id']), second)
            with self.assertRaisesRegex(ValueError, 'does not match'):
                vault.install(one['account_id'])
            self.assertEqual((codex_home / 'auth.json').read_text(), refreshed)
            atomic_write(vault.path(one['account_id']), refreshed)
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(vault.directory.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(vault.path(one['account_id']).stat().st_mode), 0o600)
                two_path = vault.path(two['account_id'])
                two_path.unlink()
                two_path.symlink_to(codex_home / 'auth.json')
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    vault.install(two['account_id'])
                two_path.unlink()
            vault.remove(two['account_id'])
            self.assertTrue(vault.path(one['account_id']).exists())
            self.assertEqual(auth_identity((codex_home / 'auth.json').read_bytes())[0], one['account_id'])

    def test_usage_is_account_scoped_persistent_and_removal_keeps_other_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'database.db'
            db = Database(path)
            try:
                db.record_usage(account(1800000, daily=25))
                legacy = db.usage_history(1800000)
                db.bind_legacy_usage('first')
                db.activate_account('first')
                self.assertEqual(db.usage_history(1800000), legacy)
                db.record_usage(account(1800060, daily=30))
                first = db.usage_history(1800060)
                db.record_usage(account(1800060, daily=90), 'second')
                self.assertEqual(db.usage_history(1800060), first)
                self.assertEqual(db.setting('account_usage')['rateLimits']['primary']['usedPercent'], 30)
                db.activate_account('second')
                self.assertEqual(db.usage_history(1800060)['daily'][-1]['remaining'], 10)
                db.activate_account('unknown')
                self.assertIsNone(db.setting('account_usage')['checked_at'])
                self.assertEqual(db.usage_history(1800060)['daily'], [])
                db.activate_account('first')
                db.delete_account_usage('second')
                self.assertEqual(db.usage_history(1800060), first)
                self.assertEqual(db.usage_history(1800060, 'second')['daily'], [])
                with self.assertRaises(ValueError):
                    db.delete_account_usage('first')
                with self.assertRaises(ValueError):
                    db.bind_legacy_usage('second')
            finally:
                db.conn.close()
            db = Database(path)
            try:
                self.assertEqual(db.setting('active_account'), 'first')
                self.assertEqual(db.usage_history(1800060), first)
            finally:
                db.conn.close()


if __name__ == '__main__':
    unittest.main()
