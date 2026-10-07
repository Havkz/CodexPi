import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import discord

from app.common import Redactor
from app.controller import Controller
from app.db import Database
from app import lifecycle


class Crash(BaseException):
    pass


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_controller(self, temp):
        root = Path(temp) / 'CodexPi'
        root.mkdir()
        path = root / 'projects/first'
        (path / '.codexpi').mkdir(parents=True)
        (path / '.git').mkdir()
        (path / '.codexpi/project-id').write_text('project-1')
        (path / '.env').write_text('PRIVATE=test-secret')
        controller = Controller.__new__(Controller)
        controller.root, controller.db = root, Database(root / 'state/test.db')
        controller.lock, controller.redactor = asyncio.Lock(), Redactor(root)
        controller.config = {'github_account': 'owner', 'discord_category': '123'}
        controller.unsnooze = {}
        controller.health_errors = {}
        controller.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
            codex_session_id,tmux_session_name,github_repo,discord_channel_id,queue_position,
            goal_status,lifecycle,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('project-1', 'First', 'first', str(path), 'session-1', 'codexpi-first', 'owner/first', '456', 1,
             'active', 'ready', 1, 1))
        controller.db.set_setting('selected', 'project-1')
        state = {'repo': 'owner/first', 'channel': 'first', 'deleted': False, 'archived': False,
                 'native_status': 'active', 'native_name': 'First', 'cwd': str(path), 'calls': [],
                 'repo_deleted': False, 'scopes': 'repo, delete_repo'}

        class Native:
            async def rpc(self, method, params):
                state['calls'].append((method, params))
                if method == 'thread/goal/get':
                    return {'goal': {'status': state['native_status']}}
                if method == 'thread/goal/set':
                    state['native_status'] = params['status']
                if method == 'thread/read':
                    return {'thread': {'status': {'type': 'idle'}, 'path': '/native/' +
                        ('archived_sessions' if state['archived'] else 'sessions') + '/session-1.jsonl'}}
                if method == 'thread/name/set':
                    state['native_name'] = params['name']
                if method == 'thread/settings/update':
                    state['cwd'] = params['cwd']
                if method == 'thread/archive':
                    assert not state['archived'], 'archive must be idempotently checked after a crash'
                    state['archived'] = True
                return {}

        class Channel:
            category_id, topic = 123, 'CodexPi project project-1'
            async def edit(self, name, reason):
                state['channel'] = name
            async def delete(self, reason):
                state['deleted'] = True

        class Bot:
            def is_ready(self):
                return True
            async def fetch_channel(self, ident):
                if state['deleted']:
                    raise discord.NotFound(SimpleNamespace(status=404, reason='gone'), 'gone')
                return Channel()

        async def command(*args, **kwargs):
            state['calls'].append((args, kwargs))
            if args[:2] == ('unsnooze', 'status'):
                return {'stdout': '{"sessions":[]}', 'stderr': '', 'exit_code': 0}
            if args[:2] == ('gh', 'api'):
                if args[2] == 'user':
                    return {'stdout': '{"login":"owner"}', 'stderr': '', 'exit_code': 0}
                if args[2].startswith('repositories/') and state['repo_deleted']:
                    return {'stdout': '', 'stderr': 'HTTP 404', 'exit_code': 1}
                if '--method' in args and args[-1] == 'DELETE':
                    state['repo_deleted'] = True
                    return {'stdout': '', 'stderr': '', 'exit_code': 0}
                if '--method' in args and 'PATCH' in args:
                    state['repo'] = 'owner/' + args[-1].removeprefix('name=')
                if args[2] == 'repos/renamed' or (args[2].startswith('repos/') and args[2][6:] != state['repo']):
                    return {'stdout': '', 'stderr': 'HTTP 404', 'exit_code': 1}
                prefix = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: ' + state['scopes'] + '\n\n' if '--include' in args else ''
                return {'stdout': prefix + json.dumps({'id': 1234, 'private': True, 'full_name': state['repo'],
                    'permissions': {'admin': True}, 'description': 'Managed by CodexPi project project-1'}), 'stderr': '', 'exit_code': 0}
            return {'stdout': '', 'stderr': '', 'exit_code': 1 if args[:2] == ('tmux', 'has-session') else 0}

        controller.native, controller.bot = Native(), Bot()
        return controller, state, command

    async def test_rename_and_delete_recover_after_every_effect(self):
        for kind, phases in [('rename', ['quiesced', 'repository', 'directory', 'session', 'channel']),
                             ('delete', ['quiesced', 'session', 'directory', 'channel'])]:
            for phase in phases:
                with self.subTest(kind=kind, phase=phase), tempfile.TemporaryDirectory() as temp:
                    controller, state, command = self.make_controller(temp)
                    original = controller.db.get('project-1')
                    save = lifecycle.save
                    def fail_before_save(c, p, op, completed):
                        if completed == phase:
                            raise Crash('simulated process death after side effect')
                        save(c, p, op, completed)
                    with patch('app.lifecycle.command', command), patch('app.controller.command', command):
                        with patch('app.lifecycle.save', fail_before_save), self.assertRaises(Crash):
                            await lifecycle.begin(controller, 'project-1', kind, name='Renamed', confirmation='First')
                        # Reopen the authoritative SQLite state, not an in-memory operation object.
                        db_path = controller.db.path
                        controller.db.conn.close()
                        controller.db = Database(db_path)
                        await lifecycle.recover(controller)
                    if kind == 'rename':
                        current = controller.db.get('project-1')
                        self.assertEqual(current['lifecycle'], 'ready', current['operation'])
                        self.assertEqual(current['codex_session_id'], original['codex_session_id'])
                        self.assertEqual(current['goal_status'], 'paused')
                        self.assertEqual(current['display_name'], 'Renamed')
                        self.assertEqual(current['github_repo'], state['repo'])
                        self.assertEqual(state['repo'], 'owner/renamed')
                        self.assertEqual(state['channel'], 'renamed')
                        self.assertEqual(state['native_name'], 'Renamed')
                        self.assertEqual(state['cwd'], current['project_path'])
                        self.assertTrue((Path(current['project_path']) / '.env').exists())
                        self.assertFalse(Path(original['project_path']).exists())
                    else:
                        self.assertEqual(controller.db.all(), [])
                        self.assertTrue(state['deleted'])
                        self.assertTrue(state['archived'])
                        self.assertEqual(state['repo'], 'owner/first')
                        self.assertFalse(state['repo_deleted'])
                        backup = controller.root / 'backups/deleted/project-1/project'
                        self.assertEqual((backup / '.env').read_text(), 'PRIVATE=test-secret')
                        self.assertFalse(Path(original['project_path']).exists())
                    self.assertIsNone(controller.db.setting('selected'))
                    controller.db.conn.close()

    async def test_confirmation_ownership_and_pending_jobs_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            controller, state, command = self.make_controller(temp)
            with patch('app.lifecycle.command', command):
                with self.assertRaisesRegex(ValueError, 'exact project name'):
                    await lifecycle.begin(controller, 'project-1', 'delete', confirmation='wrong')
                self.assertEqual(state['calls'], [])
                controller.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,created_at,updated_at) VALUES(?,?,?,?,?)',
                                           ('pending', 'project-1', '{}', 1, 1))
                with self.assertRaisesRegex(ValueError, 'Windows jobs'):
                    await lifecycle.begin(controller, 'project-1', 'rename', name='Renamed')
                for status in ('sent', 'running'):
                    controller.db.conn.execute('UPDATE jobs SET status=?', (status,))
                    with self.assertRaisesRegex(ValueError, 'Windows jobs'):
                        await lifecycle.begin(controller, 'project-1', 'delete', confirmation='First')
                    self.assertEqual(controller.db.get('project-1')['lifecycle'], 'ready')
                controller.db.conn.execute('DELETE FROM jobs')
                path = Path(controller.db.get('project-1')['project_path'])
                (path / '.codexpi/project-id').write_text('someone-else')
                with self.assertRaisesRegex(ValueError, 'ownership'):
                    await lifecycle.begin(controller, 'project-1', 'delete', confirmation='First')
                self.assertEqual(state['calls'], [])
            controller.db.conn.close()

    async def test_optional_repository_delete_is_explicit_owned_and_crash_recoverable(self):
        for interrupted in ('403', 'lost_ack'):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as temp:
                c, state, original = self.make_controller(temp)
                fault = True
                async def command(*args, **kwargs):
                    nonlocal fault
                    if args[:3] == ('gh', 'api', 'repositories/1234') and args[-1] == 'DELETE' and fault:
                        fault = False
                        if interrupted == '403':
                            raise RuntimeError('GitHub HTTP 403')
                        await original(*args, **kwargs)
                        raise Crash('DELETE accepted but acknowledgement lost')
                    return await original(*args, **kwargs)
                with patch('app.lifecycle.command', command), patch('app.controller.command', original):
                    with self.assertRaisesRegex(ValueError, 'explicit boolean'):
                        await lifecycle.begin(c, 'project-1', 'delete', confirmation='First', delete_github='true')
                    self.assertEqual(state['calls'], [])
                    state['scopes'] = 'repo'
                    with self.assertRaisesRegex(ValueError, 'delete_repo'):
                        await lifecycle.begin(c, 'project-1', 'delete', confirmation='First', delete_github=True)
                    self.assertEqual(c.db.get('project-1')['lifecycle'], 'ready')
                    self.assertFalse(state['repo_deleted'])
                    state['scopes'] = 'repo, delete_repo'
                    with self.assertRaises(RuntimeError if interrupted == '403' else Crash):
                        await lifecycle.begin(c, 'project-1', 'delete', confirmation='First', delete_github=True)
                    project = c.db.get('project-1')
                    self.assertEqual(project['lifecycle'], 'deleting')
                    self.assertEqual(json.loads(project['operation'])['repo_id'], 1234)
                    self.assertTrue((c.root / 'backups/deleted/project-1/project/.env').exists())
                    self.assertFalse(state['deleted'])
                    op = json.loads(project['operation'])
                    op['retry_at'] = 0
                    c.db.update('project-1', operation=json.dumps(op))
                    db_path = c.db.path
                    c.db.conn.close()
                    c.db = Database(db_path)
                    await lifecycle.recover(c)
                self.assertTrue(state['repo_deleted'])
                self.assertTrue(state['deleted'])
                self.assertEqual(c.db.all(), [])
                manifest = json.loads((c.root / 'backups/deleted/project-1/manifest.json').read_text())
                self.assertFalse(manifest['github_preserved'])
                self.assertEqual(manifest['github_repo_id'], 1234)
                c.db.conn.close()

    async def test_delete_supersedes_resume_for_paused_and_limited_projects(self):
        for status in ('paused', 'usage limited'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp:
                c, state, command = self.make_controller(temp)
                state['native_status'] = 'paused' if status == 'paused' else 'usageLimited'
                c.db.set_setting('usage_wake/project-1', {'reset_at': 1})
                c.db.set_setting('usage_wake/account-a/project-1', {'reset_at': 1})
                c.db.set_setting('usage_limits/account-b/project-1', {'resetAt': 1})
                c.db.set_setting('usage_account/project-1', 'account-a')
                c.db.set_setting('account_wait', {'project_id': 'project-1', 'account_id': 'account-b'})
                c.db.set_setting('usage_wake/account-a/unrelated', {'reset_at': 2})
                c.db.set_setting('prompts/project-1', [{'id': 'queued-user-prompt'}])
                c.db.set_setting('prompt_active/project-1', {'id': 'old-turn'})
                c.db.set_setting('prompt_limit/project-1', {'turn_id': 'old-turn'})
                c.db.update('project-1', goal_status=status,
                            operation=json.dumps({'kind': 'resume', 'source': 'unsnooze', 'sent_at': 1}))
                c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,created_at,updated_at) VALUES(?,?,?,?,?)',
                                  ('undelivered', 'project-1', '{}', 1, 1))
                with patch('app.lifecycle.command', command), patch('app.controller.command', command):
                    await lifecycle.begin(c, 'project-1', 'delete', confirmation='First', defer=True)
                    job = c.db.conn.execute('SELECT * FROM jobs').fetchone()
                    self.assertEqual(job['status'], 'finished')
                    self.assertTrue(json.loads(job['result'])['cancelled'])
                    await lifecycle.recover(c)
                    await c.resume_ready()
                self.assertEqual(c.db.all(), [])
                self.assertIsNone(c.db.setting('usage_wake/project-1'))
                self.assertIsNone(c.db.setting('usage_wake/account-a/project-1'))
                self.assertIsNone(c.db.setting('usage_limits/account-b/project-1'))
                self.assertIsNone(c.db.setting('usage_account/project-1'))
                self.assertIsNone(c.db.setting('account_wait'))
                self.assertEqual(c.db.setting('usage_wake/account-a/unrelated'), {'reset_at': 2})
                self.assertIsNone(c.db.setting('prompts/project-1'))
                self.assertIsNone(c.db.setting('prompt_active/project-1'))
                self.assertIsNone(c.db.setting('prompt_limit/project-1'))
                self.assertTrue(state['archived'])
                self.assertTrue(state['deleted'])
                self.assertEqual(state['repo'], 'owner/first')
                self.assertIsNone(c.db.setting('selected'))
                c.db.conn.close()


if __name__ == '__main__':
    unittest.main()
