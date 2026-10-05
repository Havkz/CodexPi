import json
from contextlib import closing
from pathlib import Path
import io
import asyncio
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import runpy
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest

from app.migration import inspect_archive, extract_project, restore_native, digest
from app import migration
from app.controller import Controller, command
from app.db import Database


export = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'Setup/export-migration.py'))['export']


class MigrationTests(unittest.TestCase):
    def test_private_export_preserves_dirty_git_session_and_goal(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            project, codex = root / 'project', root / 'native'
            project.mkdir()
            (codex / 'sessions').mkdir(parents=True)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(project), *args], stderr=subprocess.DEVNULL)
            git('init')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'user.name', 'Migration fixture')
            (project / '.git/info/exclude').write_text('.venv/\n')
            tracked = project / 'work.txt'
            tracked.write_text('committed\n')
            git('add', 'work.txt')
            git('commit', '-m', 'fixture')
            git('remote', 'add', 'origin', 'https://github.com/example/private.git')
            tracked.write_text('uncommitted\n')
            (project / 'new.txt').write_text('not yet tracked\n')
            (project / '.venv').mkdir()
            (project / '.venv/cache').write_text('rebuild me')
            sid = '00000000-0000-4000-8000-000000000001'
            rollout = codex / 'sessions' / ('rollout-' + sid + '.jsonl')
            history = json.dumps({'type': 'session_meta', 'payload': {'id': sid, 'cwd': str(project)}}) + '\n'
            rollout.write_text(history)
            with closing(sqlite3.connect(codex / 'goals_1.sqlite')) as db:
                db.execute('CREATE TABLE thread_goals(thread_id TEXT, status TEXT, objective TEXT)')
                db.execute('INSERT INTO thread_goals VALUES (?,?,?)', (sid, 'paused', 'original objective'))
                db.commit()
            before = git('status', '--porcelain=v1')
            with closing(sqlite3.connect(codex / 'thread_history_1.sqlite')) as db:
                db.execute('CREATE TABLE thread_items(thread_id TEXT, item_json TEXT, started_at_ms INTEGER, completed_at_ms INTEGER)')
                db.execute('INSERT INTO thread_items VALUES (?,?,?,?)', (sid, '{"text":"original item"}', 1, 2))
                db.commit()
            target = root / 'export.tar.gz'
            result = export(project, sid, codex, target)
            self.assertEqual(result['original_goal_status'], 'paused')
            with tarfile.open(target) as archive:
                self.assertEqual(archive.extractfile('project/work.txt').read(), tracked.read_bytes())
                self.assertEqual(archive.extractfile('project/new.txt').read(), (project / 'new.txt').read_bytes())
                self.assertEqual(archive.extractfile('native/' + rollout.name).read(), rollout.read_bytes())
                manifest = json.load(archive.extractfile('manifest.json'))
                self.assertEqual(manifest['original_goal']['objective'], 'original objective')
                self.assertTrue(any(item['path'].startswith('project/.git/objects/') for item in manifest['files']))
                self.assertNotIn('project/.venv/cache', archive.getnames())
            self.assertEqual(git('status', '--porcelain=v1'), before)
            self.assertEqual(rollout.read_text(), history)
            # One end-to-end data check also covers import integrity, collision
            # refusal, paused goal preservation and hostile archive rejection.
            verified = inspect_archive(target, result['sha256'])
            imported = root / 'imported'
            extract_project(target, verified, imported, 'project-1')
            self.assertEqual((imported / 'work.txt').read_bytes(), tracked.read_bytes())
            self.assertEqual((imported / '.git/HEAD').read_bytes(), (project / '.git/HEAD').read_bytes())
            with self.assertRaisesRegex(ValueError, 'already exists'):
                extract_project(target, verified, imported, 'project-1')
            native_target = root / 'pi-native'
            native_target.mkdir()
            with closing(sqlite3.connect(native_target / 'goals_1.sqlite')) as db:
                db.execute('CREATE TABLE thread_goals(thread_id TEXT, status TEXT, objective TEXT)')
            with closing(sqlite3.connect(native_target / 'thread_history_1.sqlite')) as db:
                db.execute('CREATE TABLE thread_items(thread_id TEXT, item_json TEXT)')
            pi = {'project_path': str(imported)}
            restored = restore_native(verified, pi, native_target)
            self.assertEqual(restored.read_bytes(), rollout.read_bytes())
            self.assertEqual(restore_native(verified, pi, native_target), restored)
            with closing(sqlite3.connect(native_target / 'thread_history_1.sqlite')) as db:
                self.assertEqual(db.execute('SELECT item_json FROM thread_items').fetchone()[0], '{"text":"original item"}')
            compat = json.loads((imported / '.codexpi/migration/compatibility.json').read_text())
            self.assertEqual(compat['thread_items']['snapshot_only_columns'], ['completed_at_ms', 'started_at_ms'])
            with closing(sqlite3.connect(native_target / 'goals_1.sqlite')) as db:
                self.assertEqual(db.execute('SELECT status,objective FROM thread_goals').fetchone(),
                                 ('paused', 'original objective'))
                db.execute("UPDATE thread_goals SET objective='other live state'")
                db.commit()
            with self.assertRaisesRegex(ValueError, 'overwrite existing'):
                restore_native(verified, pi, native_target)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                inspect_archive(target, '0' * 64)
            hostile = root / 'hostile.tar.gz'
            with tarfile.open(hostile, 'w:gz') as archive:
                item = tarfile.TarInfo('../escape')
                item.size = 1
                archive.addfile(item, io.BytesIO(b'x'))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                inspect_archive(hostile, digest(hostile))
            async def journal_check():
                pi_root = root / 'CodexPi'
                (pi_root / 'backups/migrations').mkdir(parents=True)
                (pi_root / 'projects').mkdir()
                (pi_root / 'templates').mkdir()
                (pi_root / 'templates/AGENTS.md').write_text('Keep the single-project queue.')
                bundle = pi_root / 'backups/migrations/export.tar.gz'
                shutil.copyfile(target, bundle)
                home = root / 'pi-home'
                (home / '.codex').mkdir(parents=True)
                with closing(sqlite3.connect(home / '.codex/goals_1.sqlite')) as db:
                    db.execute('CREATE TABLE thread_goals(thread_id TEXT, status TEXT, objective TEXT)')
                with closing(sqlite3.connect(home / '.codex/thread_history_1.sqlite')) as db:
                    db.execute('CREATE TABLE thread_items(thread_id TEXT, item_json TEXT)')
                c = Controller.__new__(Controller)
                c.root, c.db, c.lock = pi_root, Database(pi_root / 'state/codexpi.db'), asyncio.Lock()
                c.config, c.source = {'github_account': 'example'}, SimpleNamespace(rows=lambda: {})
                c.cancel_wakes = AsyncMock()
                c.bot = SimpleNamespace(is_ready=lambda: True, ensure_channel=AsyncMock(
                    side_effect=[RuntimeError('Discord interrupted'), SimpleNamespace(id=123)]))
                calls = []
                async def rpc(method, params):
                    calls.append(method)
                    if method == 'thread/resume':
                        return {'thread': {'id': sid, 'cwd': params['cwd']}}
                    if method == 'thread/goal/get':
                        return {'goal': {'status': 'paused', 'objective': 'original objective'}}
                    return {}
                c.native = SimpleNamespace(rpc=rpc)
                repo = {'id': 123, 'private': True, 'permissions': {'admin': True},
                        'full_name': 'example/private', 'description': 'original'}
                async def commands(*args, **kwargs):
                    if args[:2] == ('gh', 'api'):
                        if '--method' in args:
                            repo['description'] = args[-1].removeprefix('description=')
                        return {'stdout': json.dumps(repo)}
                    return await command(*args, **kwargs)
                data = {'name': 'Imported', 'archive': str(bundle), 'sha256': result['sha256']}
                try:
                    with patch('app.migration.command', commands), patch('app.migration.Path.home', return_value=home):
                        with self.assertRaisesRegex(RuntimeError, 'Discord interrupted'):
                            await migration.request(c, data)
                        pending = c.db.by_session(sid)
                        self.assertEqual(pending['lifecycle'], 'importing')
                        self.assertTrue(c.db.setting('manual_pause/' + pending['project_id']))
                        self.assertEqual(json.loads(pending['operation'])['phase'], 'session')
                        migrated = await migration.request(c, data)
                        self.assertEqual(migrated['lifecycle'], 'ready')
                        self.assertEqual(migrated['goal_status'], 'paused')
                        self.assertEqual((await migration.request(c, data))['project_id'], migrated['project_id'])
                        self.assertEqual(calls.count('thread/resume'), 1)
                        self.assertNotIn('thread/goal/set', calls)
                        self.assertNotIn('turn/start', calls)
                        self.assertFalse(c.db.setting('selected'))
                        self.assertEqual(len(c.db.all()), 1)
                finally:
                    c.db.conn.close()
            asyncio.run(journal_check())
            with self.assertRaises(FileExistsError):
                export(project, sid, codex, target)
            with closing(sqlite3.connect(codex / 'goals_1.sqlite')) as db:
                db.execute("UPDATE thread_goals SET status='active'")
                db.commit()
            with self.assertRaisesRegex(ValueError, 'Pause this Windows goal'):
                export(project, sid, codex, root / 'active.tar.gz')
