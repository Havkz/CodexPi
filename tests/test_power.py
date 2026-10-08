import asyncio
from datetime import datetime, timezone
from contextlib import closing
import json
import errno
import logging
from pathlib import Path
import tempfile
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from app.controller import Controller
from app.db import Database
from app import power
from app.windows_worker import Worker


class PowerTests(unittest.IsolatedAsyncioTestCase):
    def controller(self, directory):
        c = Controller.__new__(Controller)
        c.db = Database(Path(directory) / 'state.db')
        c.config = {'lan_subnet': '192.168.2.0/24'}
        c.worker, c.worker_seen = None, 0
        c.native = SimpleNamespace(rpc=AsyncMock(return_value={'thread': {
            'id': 'session', 'cwd': directory, 'status': {'type': 'idle'}}}))
        c.db.conn.execute('''INSERT INTO projects(project_id,display_name,slug,project_path,
            codex_session_id,tmux_session_name,queue_position,goal_status,windows_required,
            block_reason,lifecycle,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('project', 'project', 'project', directory, 'session', 'pane', 1, 'stalled', 1,
             json.dumps({'reason': 'Windows offline', 'requires_user': False}), 'ready', 1, 1))
        c.db.set_setting('selected', 'project')
        c.db.set_setting('windows_power_observation', self.observation())
        return c

    def observation(self, **fields):
        return {'mac': '74-56-3C-2B-FD-0F', 'address': '192.168.2.200', 'boot_at': time.time() - 1000,
                'startup_ready': True, 'boot_worker': True, 'user_active': False, **fields}

    async def test_wake_once_recovery_signed_ownership_job_batch_and_user_takeover(self):
        with patch('app.power.socket.socket') as factory:
            power.wake('74-56-3C-2B-FD-0F', '192.168.2.255')
            packet, address = factory.return_value.__enter__.return_value.sendto.call_args.args
            self.assertEqual(packet, b'\xff' * 6 + bytes.fromhex('74563c2bfd0f') * 16)
            self.assertEqual(address, ('192.168.2.255', 9))
        with tempfile.TemporaryDirectory() as directory, closing((c := self.controller(directory)).db.conn):
            with patch('app.power.wake') as wake, patch('app.worker_server.send', AsyncMock()) as send:
                await power.tick(c)
                wake.assert_not_called()  # Default off.
                c.db.set_setting('auto_boot_windows', True)
                await power.tick(c)
                requested = c.db.setting('windows_power')
                await power.tick(c)  # Persisted state survives reconnect/restart without another packet.
                recovered = Controller.__new__(Controller)
                recovered.__dict__ = c.__dict__.copy()
                recovered.db = Database(Path(directory) / 'state.db')
                with closing(recovered.db.conn):
                    await power.tick(recovered)
                wake.assert_called_once_with('74-56-3C-2B-FD-0F', '192.168.2.255')
                c.worker, c.worker_seen = SimpleNamespace(closed=False), time.monotonic()
                boot_at = time.time()
                await power.observe(c, self.observation(boot_at=boot_at))
                await power.observe(c, self.observation(boot_at=boot_at))
                send.assert_awaited_once()
                power.result(c, {'id': requested['id'], 'command': 'claim', 'accepted': True, 'boot_at': boot_at})
                self.assertEqual(c.db.setting('windows_power')['phase'], 'owned')
                c.db.update('project', goal_status='active', windows_required=0, block_reason=None)
                c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                                  ('job', 'project', '{}', 'running', time.time(), time.time()))
                await power.tick(c)
                self.assertNotIn('idle_since', c.db.setting('windows_power'))
                c.db.conn.execute("UPDATE jobs SET status='finished'")
                c.native.rpc.return_value['thread']['status']['type'] = 'active'
                await power.tick(c)  # Wait for the requesting native turn, not just the first test result.
                self.assertNotIn('idle_since', c.db.setting('windows_power'))
                c.native.rpc.return_value['thread']['status']['type'] = 'idle'
                await power.tick(c)
                state = c.db.setting('windows_power')
                state['idle_since'] -= 601
                c.db.set_setting('windows_power', state)
                c.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                                  ('next', 'project', '{}', 'pending', time.time(), time.time()))
                await power.tick(c)
                send.assert_awaited_once()  # A second queued job cancels the shutdown grace.
                await power.observe(c, self.observation(boot_at=boot_at, user_active=True))
                self.assertEqual(c.db.setting('windows_power')['phase'], 'released')
                await power.tick(c)
                send.assert_awaited_once()

    async def test_timeout_holds_shutdown_once_and_invalid_targets(self):
        with tempfile.TemporaryDirectory() as directory, closing((c := self.controller(directory)).db.conn):
            c.db.set_setting('auto_boot_windows', True)
            with patch('app.power.wake') as wake, patch('app.worker_server.send', AsyncMock()) as send:
                c.db.set_setting('manual_pause/project', True)
                await power.tick(c)
                wake.assert_not_called()
                c.db.set_setting('manual_pause/project', False)
                await power.tick(c)
                state = c.db.setting('windows_power')
                with patch('app.power.time.time', return_value=state['requested_at'] + 601):
                    await power.tick(c)
                    await power.tick(c)
                self.assertEqual(c.db.setting('windows_power')['phase'], 'failed')
                wake.assert_called_once()
                c.worker, c.worker_seen = SimpleNamespace(closed=False), time.monotonic()
                c.db.update('project', goal_status='complete', queue_position=None)
                state.update(phase='owned', boot_at=time.time(), idle_since=time.time() - 601)
                c.db.set_setting('windows_power', state)
                await power.tick(c)
                await power.tick(c)
                send.assert_awaited_once()
                self.assertEqual(send.await_args.args[1]['type'], 'power_shutdown')
                self.assertNotIn('argv', send.await_args.args[1])
                c.worker_seen = 0
                await power.tick(c)
                self.assertEqual(c.db.setting('windows_power')['phase'], 'shutdown_sent')
            for value in ({}, {'mac': None}, self.observation(address='8.8.8.8'), self.observation(mac='ff')):
                with self.assertRaises(ValueError):
                    power.target(value, c.config['lan_subnet'])
            with self.assertRaises(ValueError):
                await power.observe(c, self.observation(boot_at=float('nan')))

    async def test_worker_never_shuts_down_existing_boot_user_session_or_unfinished_jobs(self):
        with tempfile.TemporaryDirectory() as directory, closing((worker := Worker(directory, 'secret', 'unused',
                boot_worker=True, boot_at=time.time() - 1)).db):
            observation = self.observation(boot_at=worker.boot_at)
            from app.windows_power import network_wake_since
            (worker.root / 'windows-worker/power.json').write_text(json.dumps({'mac': observation['mac']}))
            event = {'source': 'Ethernet adapter', 'adapter': 'Ethernet adapter',
                     'time': datetime.now(timezone.utc).isoformat()}
            with patch('app.windows_power.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(event))) as query:
                self.assertTrue(network_wake_since(worker.root, time.time() - 2))
                event['source'] = 'USB controller'
                query.return_value.stdout = json.dumps(event)
                self.assertFalse(network_wake_since(worker.root, time.time() - 2))
                event['source'], event['time'] = 'Ethernet adapter', '2020-01-01T00:00:00Z'
                query.return_value.stdout = json.dumps(event)
                self.assertFalse(network_wake_since(worker.root, time.time() - 2))
            with patch('app.windows_power.observation', return_value=observation), \
                    patch('app.windows_power.network_wake_since', return_value=True) as network_wake, \
                    patch('app.windows_worker.execute', AsyncMock(return_value={'exit_code': 0})) as execute:
                claim = {'type': 'power_claim', 'id': str(uuid.uuid4()), 'requested_at': time.time() - 2,
                         'previous_boot': worker.boot_at}
                network_wake.return_value = False
                self.assertFalse((await worker.power_command(claim))['accepted'])
                claim.update(id=str(uuid.uuid4()), previous_boot=1)
                observation['user_active'] = True
                self.assertFalse((await worker.power_command(claim))['accepted'])
                claim['id'], observation['user_active'] = str(uuid.uuid4()), False
                network_wake.return_value = False
                self.assertFalse((await worker.power_command(claim))['accepted'])
                claim['id'], network_wake.return_value = str(uuid.uuid4()), True
                self.assertTrue((await worker.power_command(claim))['accepted'])
                shutdown = {'type': 'power_shutdown', 'id': claim['id'], 'boot_at': worker.boot_at,
                            'expires_at': time.time() + 25}
                worker.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)', ('job', '{}', 'finished', '{}', time.time()))
                self.assertFalse((await worker.power_command(shutdown))['accepted'])
                worker.db.execute("UPDATE jobs SET status='delivered'")
                observation['user_active'] = True
                self.assertFalse((await worker.power_command(shutdown))['accepted'])
                observation['user_active'] = False
                self.assertTrue((await worker.power_command(shutdown))['accepted'])
                self.assertFalse((await worker.power_command(shutdown))['accepted'])
                execute.assert_awaited_once_with(['shutdown.exe', '/s', '/t', '0'], worker.root, 10)
            from app.windows_worker import main
            with patch.dict(sys.modules, {'msvcrt': SimpleNamespace(LK_NBLCK=1,
                    locking=lambda *_: (_ for _ in ()).throw(PermissionError(errno.EACCES, 'locked')))}), \
                    patch.object(sys, 'argv', ['worker', '--boot']), \
                    patch('app.windows_worker.ROOT', worker.root), \
                    patch('app.windows_worker.RotatingFileHandler', return_value=logging.NullHandler()), \
                    patch('app.windows_power.desktop_in_use', return_value=True), \
                    patch('app.windows_worker.protect_secret') as decrypt:
                main()
                decrypt.assert_not_called()  # A racing boot task cannot start a second executor.


if __name__ == '__main__':
    unittest.main()
