import json
from contextlib import closing
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.common import Redactor, atomic_write, block_summary
from app.db import Database
from app.discord_bot import Bot, EMBED_COLORS, status_embed


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def test_block_sections_are_ordered_actionable_and_do_not_change_admission(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        db = Database(Path(directory) / 'test.db')
        self.enterContext(closing(db.conn))
        atomic_write(Path(directory) / '.env', 'TEST_SECRET=private-test-value\n')
        c = SimpleNamespace(db=db, redactor=Redactor(directory), unsnooze={})
        reason = {'reason': 'Two prerequisites', 'reasons': ['Dirty Windows checkout', 'Runtime missing'],
                  'explanation': 'Windows protects local changes; the required runtime is absent.',
                  'solution': ['Decide how to preserve the local changes.', 'Provide the full runtime.'],
                  'details': 'UNFILTERED LOG ' * 1000 + 'private-test-value', 'requires_user': True}
        project = {'display_name': 'Test', 'goal_status': 'stalled', 'codex_session_id': 's',
                   'github_repo': None, 'project_id': 'p', 'queue_position': 1,
                   'block_reason': json.dumps(reason)}
        before = json.dumps(project)
        summary = block_summary(project)
        self.assertEqual(summary['solution'], reason['solution'])
        event = {'kind': 'stalled', 'event_id': 1, 'created_at': time.time()}
        text = status_embed(c, project, event, {'reason': reason, 'embed_color': EMBED_COLORS[0]}).description
        self.assertLess(text.index('**Reasons**'), text.index('**Erklärung**'))
        self.assertLess(text.index('**Erklärung**'), text.index('**Lösung**'))
        self.assertIn('1. Dirty Windows checkout', text)
        self.assertIn('Provide the full runtime.', text)
        self.assertNotIn('UNFILTERED LOG', text)
        self.assertNotIn('private-test-value', text)
        self.assertIn('Kein automatisches Resume', text)
        self.assertEqual(json.dumps(project), before)
        self.assertTrue(json.loads(project['block_reason'])['requires_user'])
        legacy = block_summary({**project, 'block_reason': json.dumps({
            'reason': 'Decision missing', 'details': 'Evidence. Please choose A or B.', 'requires_user': True})})
        self.assertEqual(legacy['solution'], ['Please choose A or B.'])
        quota = block_summary({**project, 'goal_status': 'usage limited', 'usage_limit': '{"resetAt":1800000000000}'})
        self.assertEqual(quota['reset_at'], 1800000000000)
        self.assertNotIn('Runtime missing', quota['reasons'])
        self.assertTrue(quota['requires_user'])
        self.assertIsNone(block_summary({'goal_status': 'active', 'block_reason': None}))

    async def test_last_signed_windows_heartbeat_survives_disconnect_and_restart(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / 'test.db'
        db = Database(path)
        db.set_setting('windows_last_heartbeat', 1791370000)
        db.conn.close()
        db = Database(path)
        self.enterContext(closing(db.conn))
        controller = SimpleNamespace(db=db, redactor=Redactor(directory), worker_seen=0,
                                     windows_online=False, unsnooze={})
        project = {'display_name': 'Test', 'goal_status': 'stalled', 'codex_session_id': 's',
                   'github_repo': None, 'project_id': 'p', 'queue_position': 1}
        event = {'kind': 'stalled', 'event_id': 1, 'created_at': time.time()}
        payload = {'embed_color': EMBED_COLORS[0],
                   'reason': {'reason': 'Windows offline', 'requires_user': False}}
        text = status_embed(controller, project, event, payload).description
        self.assertIn('<t:1791370000:F>', text)
        self.assertIn('Offline', text)
        self.assertNotIn('unavailable', text)
        controller.windows_online = True
        self.assertIn('Online', status_embed(controller, project, event, payload).description)
        db.set_setting('windows_last_heartbeat', None)
        self.assertIn('unavailable', status_embed(controller, project, event, payload).description)

    async def test_embeds_and_crash_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write(root / '.env', 'EXAMPLE_SECRET=secret-test-value\n')
            db = Database(root / 'test.db')
            db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                tmux_session_name,codex_session_id,github_repo,discord_channel_id,queue_position,
                created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                ('p', 'Test Project', 'test-project', str(root), 'codexpi-test', 'session-test',
                 'example/test-project', '123', 1, time.time(), time.time()))
            controller = SimpleNamespace(db=db, redactor=Redactor(root), worker_seen=time.monotonic() - 64,
                unsnooze={'sessions': [{'sessionId': 'session-test', 'resetAt': 1800000000000}]})
            project = db.get('p')
            for index, kind in enumerate(('active', 'paused', 'stalled', 'usage limited',
                                          'limited by budget', 'complete', 'critical', 'stalled')):
                reason = {'reason': 'Windows offline' if index == 7 else 'Missing input',
                          'details': 'Please provide secret-test-value', 'requires_user': index != 7}
                payload = {'embed_color': EMBED_COLORS[index], 'commit': 'a' * 40, 'ci': 'passed',
                           'reason': reason if kind == 'stalled' else None}
                event = {'event_id': index + 1, 'kind': kind, 'created_at': time.time()}
                embed = status_embed(controller, project, event, payload)
                data = embed.to_dict()
                self.assertFalse(data.get('fields'))
                self.assertGreaterEqual(embed.description.count('│'), 3)
                self.assertEqual(data['color'], EMBED_COLORS[index])
                self.assertLess(len(embed), 6000)
                self.assertLess(len(embed.description), 4096)
                self.assertNotIn('secret-test-value', json.dumps(data))
                self.assertIn('timestamp', data)
                self.assertEqual(data['footer']['text'], f'CodexPi • Event {index + 1}')

            db.event('p', 'complete', {'commit': 'a' * 40, 'ci': 'passed'})
            history = []

            async def messages(**kwargs):
                for item in history:
                    yield item

            channel = SimpleNamespace(send=AsyncMock(), history=messages)
            bot = Bot(controller)
            bot._connection.user = SimpleNamespace(id=777)
            bot.fetch_channel = AsyncMock(return_value=channel)
            with patch('app.discord_bot.secrets.choice', return_value=EMBED_COLORS[0]) as random_color:
                await bot.send_pending()
                self.assertEqual(channel.send.await_count, 1)
                sent = channel.send.call_args.kwargs
                self.assertEqual(sent['view'].children[0].label, 'Close')
                self.assertEqual(sent['view'].children[0].custom_id, 'codexpi:close')
                history.append(SimpleNamespace(author=SimpleNamespace(id=777), content='', embeds=[sent['embed']]))
                db.conn.execute('UPDATE events SET sent_at=NULL')  # crash after send, before durable ACK
                await bot.send_pending()
                self.assertEqual(channel.send.await_count, 1)
                self.assertEqual(random_color.call_count, 1)
                self.assertIsNotNone(db.conn.execute('SELECT sent_at FROM events').fetchone()[0])
            await bot.close()
            db.conn.close()

    async def test_usage_notification_once_and_late_reset_edits_same_message(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / 'test.db')
            self.addCleanup(db.conn.close)
            db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
                tmux_session_name,codex_session_id,discord_channel_id,created_at,updated_at)
                VALUES ('p','Test','test',?,'tmux','session','123',1,1)''', (directory,))
            controller = SimpleNamespace(db=db, redactor=Redactor(directory), unsnooze={})
            bot = Bot(controller)
            bot._connection.user = SimpleNamespace(id=777)
            history = []
            async def messages(**kwargs):
                self.assertIsNone(kwargs['limit'])
                self.assertNotIn('after', kwargs)
                for old in history:
                    yield old
            async def send(**kwargs):
                history.append(SimpleNamespace(author=SimpleNamespace(id=777), content='',
                    embeds=[kwargs['embed']], edit=AsyncMock()))
            channel = SimpleNamespace(send=AsyncMock(side_effect=send), history=messages)
            bot.fetch_channel = AsyncMock(return_value=channel)
            db.event('p', 'usage limited', {})
            await bot.send_pending()
            await bot.send_pending()
            self.assertEqual(channel.send.await_count, 1)
            self.assertIn('unknown', history[0].embeds[0].description)
            self.assertIn('Unsnooze', history[0].embeds[0].description)
            db.set_setting('prompt_limit/p', {'turn_id': 'failed-user-turn'})
            event = db.conn.execute('SELECT payload FROM events').fetchone()
            payload = json.loads(event[0]) | {'usage_limit': {'resetAt': 1800000000000}}
            db.conn.execute('UPDATE events SET payload=?', (json.dumps(payload),))
            await bot.send_pending()
            await bot.send_pending()
            self.assertEqual(channel.send.await_count, 1)
            history[0].edit.assert_awaited_once()
            self.assertIn('<t:1800000000:F>', history[0].edit.await_args.kwargs['embed'].description)
            self.assertIn('failed prompt is not replayed', history[0].edit.await_args.kwargs['embed'].description)
            await bot.close()
            db.conn.close()


if __name__ == '__main__':
    unittest.main()
