"""Optimizer-driven native /compact, after the current turn has finished."""
import hashlib
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import time
import uuid


def operation(project):
    value = json.loads(project.get('operation') or '{}')
    return value if value.get('kind') == 'compact' else None


def holds_goal(project):
    return bool(operation(project))


def warning(home, session):
    try:
        uuid.UUID(session)  # Never interpolate an unvalidated session into a glob.
    except (ValueError, TypeError, AttributeError):
        return None
    for path in (home / 'token-optimizer').glob('quality-cache-*' + session + '.json'):
        try:
            if path.is_symlink() or path.stat().st_size > 128 * 1024:
                continue
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or not isinstance(data.get('fill_warning'), dict):
                continue
            observed = datetime.fromisoformat(data['timestamp'])
            if observed.tzinfo is None:
                continue
        except (OSError, ValueError):
            continue
        except (KeyError, TypeError):
            continue
        fill = data.get('fill_warning') or {}
        if (fill.get('level') in ('WARNING', 'CRITICAL')
                and 'compact' in str(fill.get('message', '')).lower()
                and type(data.get('compactions')) is int and data['compactions'] >= 0
                and data.get('session_file') == path.name.removeprefix('quality-cache-').removesuffix('.json') + '.jsonl'):
            return {'cycle': [data['session_file'], data['compactions']], 'observed_at': observed.timestamp()}
    return None


def finish(controller, project, state, outcome):
    with controller.db.transaction():
        controller.db.set_setting('compact_result/' + project['project_id'], {
            'cycle': state['cycle'], 'outcome': outcome, 'finished_at': time.time()})
        controller.db.update(project['project_id'], operation=None)
        if state.get('previous_selected') is None and controller.db.setting('selected') == project['project_id']:
            controller.db.set_setting('selected', None)
    logging.getLogger('compaction').log(logging.WARNING if outcome == 'failed' else logging.INFO,
        'Native context compaction %s for %s', outcome, project['display_name'])


async def tick(controller):
    from .native import idle_thread
    home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    for project in controller.db.all():
        state = operation(project)
        selected = controller.db.setting('selected')
        allowed = (selected == project['project_id'] or selected is None and project['goal_status'] == 'stalled')
        allowed = (allowed and project['queue_position'] == 1 and project['lifecycle'] == 'ready'
            and not controller.db.setting('pause_all', False)
            and not controller.db.setting('manual_pause/' + project['project_id'], False)
            and not controller.db.setting('prompt_resume_required/' + project['project_id'], False)
            and not controller.account_switch_pending and not getattr(controller, 'maintenance', False))
        if not state:
            if (not allowed or project['operation'] or project['goal_status'] not in ('active', 'stalled')
                    or controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('pending','sent','running')").fetchone()):
                continue
            signal = warning(home, project['codex_session_id'])
            if not signal or controller.db.setting('compact_result/' + project['project_id'], {}).get('cycle') == signal['cycle']:
                continue
            thread = (await controller.native.rpc('thread/read', {
                'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
            if (thread['id'] != project['codex_session_id'] or thread['cwd'] != project['project_path']
                    or Path(thread.get('path') or '').name != signal['cycle'][0]):
                continue
            goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
            if goal and goal['status'] not in ('active', 'blocked'):
                continue
            if selected is None:
                if not goal or goal['status'] != 'blocked':
                    continue
                loaded = (await controller.native.rpc('thread/loaded/list', {}))['data']
                busy = False
                for session in loaded:
                    if session != project['codex_session_id'] and not await idle_thread(controller.native, session):
                        busy = True
                        break
                if busy:
                    continue
            state = {'kind': 'compact', **signal, 'phase': 'waiting', 'requested_at': time.time(),
                'previous_selected': selected,
                'goal_created_at': goal['createdAt'] if goal else None,
                'objective_hash': hashlib.sha256(goal['objective'].encode()).hexdigest() if goal else None,
                'restore_active': bool(goal and goal['status'] == 'active')}
            with controller.db.transaction():
                controller.db.update(project['project_id'], operation=json.dumps(state))
                controller.db.set_setting('selected', project['project_id'])
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if (not allowed or (goal['createdAt'] if goal else None) != state['goal_created_at']
                or (hashlib.sha256(goal['objective'].encode()).hexdigest() if goal else None) != state['objective_hash']
                or goal and goal['status'] not in ('active', 'paused', 'blocked')):
            finish(controller, project, state, 'cancelled')
            continue
        if state['phase'] == 'waiting':
            if state['restore_active'] and goal and goal['status'] == 'active':
                # Pause future goal continuation only; never interrupt the current turn.
                await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'paused'})
                goal['status'] = 'paused'
            if (controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('pending','sent','running')").fetchone()
                    or not await idle_thread(controller.native, project['codex_session_id'])):
                continue
            turns = (await controller.native.rpc('thread/turns/list', {
                'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc', 'itemsView': 'full'}))['data']
            if turns and turns[0]['status'] == 'completed' and any(i.get('type') == 'contextCompaction' for i in turns[0].get('items', [])):
                stamp = turns[0].get('completedAt') or 0
                if stamp / (1000 if stamp > 1e12 else 1) >= state['observed_at']:
                    if state['restore_active'] and goal['status'] == 'paused':
                        await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'active'})
                    finish(controller, project, state, 'completed')
                    continue
            state.update(phase='sent', previous_turn=turns[0]['id'] if turns else None, sent_at=time.time())
            controller.db.update(project['project_id'], operation=json.dumps(state))
            try:
                await controller.native.rpc('thread/compact/start', {'threadId': project['codex_session_id']}, timeout=20)
            except Exception as exc:
                # Delivery may have happened. Reconcile native evidence, never blindly resend.
                if getattr(exc, 'rejected', False):
                    state['phase'] = 'rejected'
                else:
                    state['uncertain'] = True
                controller.db.update(project['project_id'], operation=json.dumps(state))
            continue
        if not await idle_thread(controller.native, project['codex_session_id']):
            continue
        turns = (await controller.native.rpc('thread/turns/list', {
            'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc', 'itemsView': 'full'}))['data']
        completed = bool(turns and turns[0]['id'] != state['previous_turn'] and turns[0]['status'] == 'completed'
            and any(item.get('type') == 'contextCompaction' for item in turns[0].get('items', [])))
        failed = state['phase'] == 'rejected' or bool(turns and turns[0]['id'] != state['previous_turn']
            and turns[0]['status'] in ('failed', 'interrupted'))
        if not completed and not failed:
            continue  # Timeout or idle alone is not proof of a terminal compact operation.
        if state['restore_active'] and goal and goal['status'] == 'paused':
            await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'active'})
        finish(controller, project, state, 'completed' if completed else 'failed')
