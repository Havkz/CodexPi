"""Daily official CLI update, only at a proven idle single-runtime boundary."""
import asyncio
from pathlib import Path
import sqlite3
import time

from .controller import command
from .native import Native, idle_thread


async def idle(controller):
    from .prompts import active
    if any(p['lifecycle'] != 'ready' or p['operation'] or p['goal_status'] == 'active'
           or active(controller, p) for p in controller.db.all()):
        return False
    if controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone():
        return False
    if time.time() - controller.db.setting('last_tui_activity', 0) < 600:
        return False
    panes = await command('tmux', 'list-sessions', '-F', '#{session_attached} #{session_activity}', check=False)
    if panes['exit_code'] and 'no server running' not in panes['stderr'] and 'No such file' not in panes['stderr']:
        return False
    for line in panes['stdout'].splitlines():
        attached, stamp = line.split()
        if attached != '0' or time.time() - float(stamp) < 600:
            return False
    loaded = await controller.native.rpc('thread/loaded/list', {})
    for session in loaded['data']:
        if not await idle_thread(controller.native, session):
            return False
    return True


async def daily_update(controller):
    now = time.time()
    if now - getattr(controller, 'last_update_poll', 0) < 60:
        return
    controller.last_update_poll = now
    state = controller.db.setting('cli_update', {})
    pending = state.get('phase') in ('installing', 'installed', 'activating')
    if not pending and now - state.get('attempted_at', 0) < 86400:
        return
    if not await idle(controller):
        return
    binary = Path('/home/raspberry/.local/bin/codex')
    if '/packages/standalone/releases/' not in str(binary.resolve()):
        controller.health_errors['cli_update'] = 'Cannot safely update: expected the official standalone Codex installation'
        return
    before = (await command(binary, '--version', timeout=15))['stdout'].strip()
    if state.get('phase') == 'installing' and before == state.get('before'):
        state.update(phase='failed', error='CLI update was interrupted before a new version could be confirmed; retry at the next daily idle window')
        controller.db.set_setting('cli_update', state)
        controller.health_errors['cli_update'] = state['error']
        return
    controller.maintenance = True
    try:
        if not pending:
            controller.db.backup(controller.root / 'backups/sqlite')
            backup = controller.root / 'backups/native-updates' / str(int(now))
            backup.mkdir(parents=True, mode=0o700)
            # SQLite's online backup API includes WAL, never copy a live database file.
            for database in (Path.home() / '.codex').glob('*.sqlite'):
                if database.name.startswith(('goals_', 'state_')):
                    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as source:
                        with sqlite3.connect(backup / database.name) as target:
                            source.backup(target)
            state = {'phase': 'installing', 'attempted_at': now, 'before': before, 'backup': str(backup)}
            controller.db.set_setting('cli_update', state)
            await command(binary, 'update', timeout=300)
        after = (await command(binary, '--version', timeout=15))['stdout'].strip()
        state.update(phase='installed', after=after)
        controller.db.set_setting('cli_update', state)
        if after != state['before']:
            if not await idle(controller):
                return  # Install succeeded; defer runtime activation until idle again.
            state['phase'] = 'activating'
            controller.db.set_setting('cli_update', state)
            await controller.native.close()
            await command('systemctl', '--user', 'restart', 'codexpi-native.service', timeout=45)
            for attempt in range(30):
                try:
                    controller.native = await Native(controller.root / 'state/native.sock').connect()
                    break
                except Exception:
                    if attempt == 29:
                        raise
                    await asyncio.sleep(1)
            await controller.native.rpc('account/rateLimits/read', {}, timeout=15)
            for project in controller.db.all():
                thread = (await controller.native.rpc('thread/read', {'threadId': project['codex_session_id'],
                                                                     'includeTurns': False}))['thread']
                if thread['id'] != project['codex_session_id'] or thread['cwd'] != project['project_path']:
                    raise RuntimeError('Updated native runtime has a mismatched session/workspace mapping')
            await controller.recover()
        state.update(phase='complete', completed_at=time.time())
        state.pop('error', None)
        controller.db.set_setting('cli_update', state)
        controller.health_errors.pop('cli_update', None)
    except Exception as exc:
        state.update(phase='failed', error=controller.redactor.clean(str(exc)))
        controller.db.set_setting('cli_update', state)
        controller.health_errors['cli_update'] = state['error']
    finally:
        controller.maintenance = False
