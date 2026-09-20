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
        controller.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
            codex_session_id,tmux_session_name,github_repo,discord_channel_id,queue_position,
            goal_status,lifecycle,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('project-1', 'First', 'first', str(path), 'session-1', 'codexpi-first', 'owner/first', '456', 1,
             'active', 'ready', 1, 1))
        controller.db.set_setting('selected', 'project-1')
        state = {'repo': 'owner/first', 'channel': 'first', 'deleted': False, 'archived': False,
                 'native_status': 'active', 'native_name': 'First', 'cwd': str(path), 'calls': []}

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
            if args[:2] == ('gh', 'api'):
                if '--method' in args:
                    state['repo'] = 'owner/' + args[-1].removeprefix('name=')
                if args[2] == 'repos/renamed' or (args[2].startswith('repos/') and args[2][6:] != state['repo']):
                    return {'stdout': '', 'stderr': 'HTTP 404', 'exit_code': 1}
                return {'stdout': json.dumps({'id': 1234, 'private': True, 'full_name': state['repo'],
                    'description': 'Managed by CodexPi project project-1'}), 'stderr': '', 'exit_code': 0}
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
                controller.db.conn.execute('DELETE FROM jobs')
                path = Path(controller.db.get('project-1')['project_path'])
                (path / '.codexpi/project-id').write_text('someone-else')
                with self.assertRaisesRegex(ValueError, 'ownership'):
                    await lifecycle.begin(controller, 'project-1', 'delete', confirmation='First')
                self.assertEqual(state['calls'], [])
            controller.db.conn.close()


if __name__ == '__main__':
    unittest.main()
