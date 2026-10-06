"""Durable user prompts. Native queue/add auto-runs on resume, so do not use it."""
import json
import time
import uuid

from .common import NATIVE_STATUS
from .native import project_thread_config, turn_params


def key(project):
    return 'prompts/' + project['project_id']


def active(controller, project):
    return controller.db.setting('prompt_active/' + project['project_id'])


async def submit(controller, project, params, upstream):
    if not isinstance(params.get('input'), list) or not params['input']:
        raise ValueError('A user prompt is required')
    queue = controller.db.setting(key(project), [])
    ident = params.get('clientUserMessageId') or str(uuid.uuid4())
    receipt = next((r for r in controller.db.setting('prompt_receipts/' + project['project_id'], []) if r['id'] == ident), None)
    if receipt:
        if receipt.get('result'):
            return receipt['result']
        raise ValueError('This prompt was cancelled after an uncertain delivery; inspect its session before sending a new prompt')
    current = active(controller, project)
    if current and current['id'] == ident:
        if current.get('result'):
            return current['result']
        raise ValueError('Prompt delivery is being reconciled; do not submit it again')
    if not any(item['id'] == ident for item in queue):
        if len(queue) >= 100 or len(json.dumps(queue + [params]).encode()) > 8 * 1024 * 1024:
            raise ValueError('Project prompt queue is full')
        queue.append({'id': ident, 'params': turn_params(project, params), 'created_at': time.time()})
        with controller.db.transaction():
            controller.db.set_setting(key(project), queue)
            controller.db.set_setting('manual_pause/' + project['project_id'], False)
    selected = controller.db.setting('selected')
    if not controller.db.setting('pause_all', False) and (not selected or selected == project['project_id']):
        if not current and not project['operation']:
            result = await dispatch(controller, project, upstream, allow_limited=True)
            if result is not None:
                return result
    raise ValueError('Prompt saved in the CodexPi queue; the running project keeps working. Do not resend this prompt.')


async def dispatch(controller, project, native, *, allow_limited=False):
    queue = controller.db.setting(key(project), [])
    if (not queue or active(controller, project) or project['operation'] or project['lifecycle'] != 'ready'
            or controller.db.setting('pause_all', False)
            or controller.db.setting('manual_pause/' + project['project_id'], False)
            or project['goal_status'] == 'usage limited' and not allow_limited):
        return None
    selected = controller.db.setting('selected')
    if selected and selected != project['project_id']:
        return None
    thread = (await native.rpc('thread/read', {'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
    if thread['status']['type'] not in ('idle', 'notLoaded', 'systemError'):
        return None
    if thread['status']['type'] == 'systemError':
        turns = (await native.rpc('thread/turns/list', {'threadId': project['codex_session_id'], 'limit': 1,
                                                       'sortDirection': 'desc'}))['data']
        if not turns or turns[0]['status'] not in ('completed', 'failed', 'interrupted'):
            return None
    # No paused/blocked goal is resumed implicitly by sending an ordinary prompt.
    await native.rpc('thread/resume', {'threadId': project['codex_session_id'], 'cwd': project['project_path'],
        'runtimeWorkspaceRoots': [project['project_path']], 'approvalPolicy': 'never', 'sandbox': 'workspace-write',
        'config': project_thread_config(project['project_path'])})
    item = {**queue[0], 'previous_status': project['goal_status'], 'phase': 'submitting'}
    controller.select(project['project_id'])
    with controller.db.transaction():
        controller.db.set_setting('prompt_active/' + project['project_id'], item)
        controller.db.set_setting(key(project), queue[1:])
    # A crash/timeout after this boundary is ambiguous: never replay automatically.
    try:
        result = await native.rpc('turn/start', item['params'])
        item.update(phase='active', result=result, turn_id=result['turn']['id'])
        with controller.db.transaction():
            controller.db.set_setting('prompt_active/' + project['project_id'], item)
            controller.db.update(project['project_id'], goal_status='active', last_activity=time.time())
        return result
    except Exception as exc:
        item['error'] = controller.redactor.clean(str(exc))
        controller.db.set_setting('prompt_active/' + project['project_id'], item)
        controller.health_errors['prompt'] = 'Prompt delivery requires inspection in ' + project['display_name'] + ': ' + item['error']
        raise


async def reconcile(controller, project):
    item = active(controller, project)
    if not item:
        return False
    turns = (await controller.native.rpc('thread/turns/list', {'threadId': project['codex_session_id'],
                        'limit': 100, 'sortDirection': 'desc'}))['data']
    turn = next((t for t in turns if t['id'] == item.get('turn_id') or any(
        i.get('clientUserMessageId') == item['id'] for i in t.get('items', []))), None)
    if turn is None:
        controller.health_errors['prompt'] = 'Cannot confirm prompt delivery in ' + project['display_name'] + '; inspect its TUI before retrying'
        return True  # Fail closed: retain the slot, never replay a possibly delivered prompt.
    if turn['status'] == 'inProgress':
        controller.db.update(project['project_id'], goal_status='active')
        return True
    if turn['status'] not in ('completed', 'failed', 'interrupted'):
        return True
    goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
    status = NATIVE_STATUS[goal['status']] if goal else item['previous_status']
    error = turn.get('error') or {}
    if error.get('codexErrorInfo') == 'usageLimitExceeded':
        status = 'usage limited'  # Genuine native turn error, not account availability/inactivity.
    controller.record_status(controller.db.get(project['project_id']), status)
    with controller.db.transaction():
        receipts = controller.db.setting('prompt_receipts/' + project['project_id'], [])
        controller.db.set_setting('prompt_receipts/' + project['project_id'],
                                  (receipts + [{'id': item['id'], 'result': item.get('result')}])[-100:])
        controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_active/' + project['project_id'],))
        if status not in ('active', 'usage limited') and controller.db.setting('selected') == project['project_id']:
            controller.db.set_setting('selected', None)
    controller.health_errors.pop('prompt', None)
    return status == 'usage limited' and not goal


def cancel_active(controller, project):
    """Only after the shared wait_idle proof. Never automatically replay an uncertain send."""
    item = active(controller, project)
    if item:
        with controller.db.transaction():
            receipts = controller.db.setting('prompt_receipts/' + project['project_id'], [])
            controller.db.set_setting('prompt_receipts/' + project['project_id'],
                                      (receipts + [{'id': item['id'], 'result': item.get('result')}])[-100:])
            controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_active/' + project['project_id'],))
        controller.health_errors.pop('prompt', None)
