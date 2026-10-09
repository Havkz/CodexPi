"""Durable user prompts. Native queue/add auto-runs on resume, so do not use it."""
import json
import time
import uuid

from .common import NATIVE_STATUS
from .native import idle_thread, project_thread_config, turn_params
from .usage import number


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
            controller.db.enqueue(project['project_id'])
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
            or controller.account_switch_pending
            or controller.db.setting('pause_all', False)
            or controller.db.setting('manual_pause/' + project['project_id'], False)
            or project['goal_status'] == 'usage limited' and not allow_limited):
        return None
    selected = controller.db.setting('selected')
    if selected and selected != project['project_id']:
        return None
    thread = (await native.rpc('thread/read', {'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
    if thread.get('id') != project['codex_session_id'] or thread.get('cwd') != project['project_path']:
        raise ValueError('Native prompt session identity does not match the project mapping')
    if thread['status']['type'] not in ('idle', 'notLoaded', 'systemError'):
        return None
    if thread['status']['type'] == 'systemError':
        turns = (await native.rpc('thread/turns/list', {'threadId': project['codex_session_id'], 'limit': 1,
                                                       'sortDirection': 'desc'}))['data']
        if not turns or turns[0]['status'] not in ('completed', 'failed', 'interrupted'):
            return None
    # No paused/blocked goal is resumed implicitly by sending an ordinary prompt.
    await native.rpc('thread/resume', {'threadId': project['codex_session_id'], 'cwd': project['project_path'],
        'excludeTurns': True,
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
            controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_limit/' + project['project_id'],))
            controller.db.update(project['project_id'], goal_status='active', usage_limit=None, last_activity=time.time())
            receipt = json.loads(project['resume_result'] or '{}')
            if receipt.get('id') == item['id']:
                controller.db.update(project['project_id'], resume_result=json.dumps({
                    'id': item['id'], 'status': 'active', 'message': 'Saved prompt is running in the mapped native session'}))
        return result
    except Exception as exc:
        item['error'] = controller.redactor.clean(str(exc))
        controller.db.set_setting('prompt_active/' + project['project_id'], item)
        controller.health_errors['prompt'] = 'Prompt delivery requires inspection in ' + project['display_name'] + ': ' + item['error']
        raise


async def reconcile(controller, project):
    item = active(controller, project)
    if not item:
        limit = controller.db.setting('prompt_limit/' + project['project_id'])
        if not limit:
            # Repair pre-fix receipts only with a newer, successful native terminal turn.
            receipts = controller.db.setting('prompt_receipts/' + project['project_id'], [])
            receipt = receipts[-1] if receipts else {}
            turn_id = ((receipt.get('result') or {}).get('turn') or {}).get('id')
            if project['goal_status'] == 'complete' and turn_id and not receipt.get('completion_checked'):
                turns = (await controller.native.rpc('thread/turns/list', {
                    'threadId': project['codex_session_id'], 'limit': 1, 'sortDirection': 'desc'}))['data']
                turn = turns[0] if turns else {}
                if (turn.get('id') != turn_id or turn.get('status') not in ('completed', 'failed', 'interrupted')
                        or not await idle_thread(controller.native, project['codex_session_id'])):
                    return False
                goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
                last_event = controller.db.conn.execute(
                    "SELECT max(created_at) FROM events WHERE project_id=? AND kind='complete'", (project['project_id'],)).fetchone()[0]
                completed = turn.get('completedAt')
                completed = completed / 1000 if number(completed) and completed > 1e12 else completed
                with controller.db.transaction():
                    receipt.update(completion_checked=True, status=turn['status'], completed_at=completed)
                    controller.db.set_setting('prompt_receipts/' + project['project_id'], receipts)
                    if (turn['status'] == 'completed' and goal and goal['status'] == 'complete'
                            and number(completed) and completed > (last_event or 0)):
                        controller.db.update(project['project_id'], completion_notified=0)
            return False
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        # A genuine failed user turn does not change an inactive native goal.
        # Keep its evidence until an explicit goal change or a confirmed reset.
        if ((goal['status'] if goal else None) != limit.get('goal_status')
                or (goal.get('updatedAt') if goal else None) != limit.get('goal_updated_at')):
            controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_limit/' + project['project_id'],))
            return False
        metadata = json.loads(project['usage_limit'] or '{}')
        account = controller.db.setting('account_usage', {})
        owner = controller.db.setting('usage_account/' + project['project_id'])
        if owner and account.get('account_id') != owner:
            return True  # Another login's quota never clears a failed prompt receipt.
        reset = metadata.get('resetAt')
        if (not reset or reset > time.time() * 1000 or account.get('checked_at', 0) * 1000 <= reset
                or account.get('ordinaryUsageAllowed') is not True
                or not await idle_thread(controller.native, project['codex_session_id'])
                or controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone()):
            return True
        # Do not replay a failed prompt: it may already have performed actions.
        # Nor does a quota reset authorize resuming a previously paused goal.
        with controller.db.transaction():
            controller.record_status(project, NATIVE_STATUS[goal['status']] if goal else limit['previous_status'])
            controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_limit/' + project['project_id'],))
            if (goal and goal['status'] == 'paused' and not controller.db.setting(key(project), [])
                    and not project['operation'] and not controller.account_holds_goal(project)):
                controller.db.set_setting('manual_pause/' + project['project_id'], True)
            if (controller.db.setting('selected') == project['project_id'] and not project['operation']
                    and not controller.account_holds_goal(project)):
                controller.db.set_setting('selected', None)
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
    limited = error.get('codexErrorInfo') == 'usageLimitExceeded'
    if limited:
        status = 'usage limited'  # Genuine native turn error, not account availability/inactivity.
    limit = None
    if limited and (not goal or goal['status'] != 'usageLimited'):
        limit = {
                'turn_id': turn['id'], 'goal_status': goal['status'] if goal else None,
                'goal_updated_at': goal.get('updatedAt') if goal else None,
                'previous_status': item['previous_status'] if item['previous_status'] not in ('active', 'usage limited') else 'paused'}
    controller.record_status(controller.db.get(project['project_id']), status, prompt_limit=limit)
    with controller.db.transaction():
        receipts = controller.db.setting('prompt_receipts/' + project['project_id'], [])
        controller.db.set_setting('prompt_receipts/' + project['project_id'],
                                  (receipts + [{'id': item['id'], 'result': item.get('result'),
                                    'status': turn['status'], 'completed_at': turn.get('completedAt'),
                                    'completion_checked': True}])[-100:])
        if turn['status'] == 'completed' and status == 'complete':
            controller.db.update(project['project_id'], completion_notified=0)
        controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_active/' + project['project_id'],))
        if (status == 'paused' and goal and not controller.db.setting(key(project), [])
                and not project['operation'] and not controller.account_holds_goal(project)):
            controller.db.set_setting('manual_pause/' + project['project_id'], True)
        if (status not in ('active', 'usage limited') and controller.db.setting('selected') == project['project_id']
                and not controller.account_holds_goal(project)):
            controller.db.set_setting('selected', None)
    controller.health_errors.pop('prompt', None)
    return limited


def cancel_active(controller, project):
    """Only after the shared wait_idle proof. Never automatically replay an uncertain send."""
    item = active(controller, project)
    controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_limit/' + project['project_id'],))
    if item:
        with controller.db.transaction():
            receipts = controller.db.setting('prompt_receipts/' + project['project_id'], [])
            controller.db.set_setting('prompt_receipts/' + project['project_id'],
                                      (receipts + [{'id': item['id'], 'result': item.get('result')}])[-100:])
            controller.db.conn.execute('DELETE FROM settings WHERE key=?', ('prompt_active/' + project['project_id'],))
        controller.health_errors.pop('prompt', None)
