"""Private managed-Codex auth slots. Never store tokens in DB, browser state or logs."""
import base64
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import uuid

from .common import atomic_write, codex_login_url
from .usage import number, windows


class LoginRequired(ValueError):
    """Explicit native auth rejection, never a timeout or identity mismatch."""


def mark_login_required(controller, account_id):
    controller.db.set_setting('accounts', [dict(a, status='needs_login') if a['account_id'] == account_id else a
                                         for a in controller.db.setting('accounts', [])])
    if controller.db.setting('active_account') == account_id:
        controller.db.set_setting('account_usage', {'account_id': account_id, 'checked_at': None})


def choose_account(accounts, snapshots, now, attempted=()):
    """Choose a quota check or reset wait, never authorize a goal from cached usage.

    The controller must supply a bounded, durable per-limit-event `attempted`
    list and confirm fresh native limits after installing any chosen login.
    """
    available, unknown, waiting = [], [], []
    for account in accounts:
        ident = account.get('account_id')
        if not ident or account.get('status') != 'ready':
            continue
        snapshot = snapshots.get(ident, {})
        stamp = snapshot.get('checked_at')
        quota = windows(snapshot) if (snapshot.get('account_id') == ident
            and number(stamp) and 0 < stamp <= now) else {}
        weekly, daily = quota.get('weekly'), quota.get('daily')
        exhausted = [w for w in quota.values() if w['remaining'] == 0]
        # An observed empty weekly window cannot become eligible at its 5h reset.
        # Reset passage only permits another check; it never manufactures a refill.
        if weekly and weekly['remaining'] == 0 and weekly['reset_at'] and weekly['reset_at'] > now:
            reset = max([weekly['reset_at']] + [w['reset_at'] for w in exhausted if w['reset_at']])
            waiting.append({'account_id': ident, 'mode': 'wait', 'reset_at': reset,
                            'reason': 'weekly exhausted'})
            continue
        if (weekly and weekly['remaining'] > 0 and daily and daily['remaining'] == 0
                and daily['reset_at'] and daily['reset_at'] > now):
            waiting.append({'account_id': ident, 'mode': 'wait', 'reset_at': daily['reset_at'],
                            'reason': '5h exhausted'})
            continue
        if ident in attempted:
            continue  # No ping-pong or repeated probes within the same limit event.
        fresh = bool(quota and now - stamp <= 90 and not any(
            w['reset_at'] and stamp < w['reset_at'] <= now for w in quota.values()))
        candidate = {'account_id': ident, 'mode': 'verify', 'reset_at': None,
                     'reason': 'fresh native limits required'}
        if (fresh and weekly and daily and weekly['remaining'] > 0 and daily['remaining'] > 0
                and snapshot.get('ordinaryUsageAllowed') is not False):
            resets = [w['reset_at'] for w in quota.values() if w['reset_at'] and w['reset_at'] > now]
            available.append((min(resets, default=float('inf')), weekly['remaining'], candidate))
        else:
            unknown.append(candidate)
    if available:
        earliest = min(item[0] for item in available)
        # One telemetry polling interval counts as practically the same reset time.
        near = [item for item in available if item[0] <= earliest + 60]
        return min(near, key=lambda item: (-item[1], item[0], item[2]['account_id']))[2]
    if unknown:
        return min(unknown, key=lambda item: item['account_id'])
    return min(waiting, key=lambda item: (item['reset_at'], item['account_id'])) if waiting else None


def auth_identity(raw):
    """Decode identity, not authenticity; the native account/limits RPC confirms the login."""
    try:
        auth = json.loads(raw)
        if not isinstance(auth, dict):
            raise ValueError()
        tokens = auth['tokens']
        if not isinstance(tokens, dict):
            raise ValueError()
        if auth.get('auth_mode', 'chatgpt') != 'chatgpt' or auth.get('OPENAI_API_KEY'):
            raise ValueError()
        if any(not isinstance(tokens.get(key), str) or not tokens[key]
               for key in ('id_token', 'access_token', 'refresh_token', 'account_id')):
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(tokens['id_token'].split('.')[1] + '==='))
        if not isinstance(claims, dict):
            raise ValueError()
        principal = claims.get('sub')
        if not isinstance(principal, str) or not principal:
            raise ValueError()
        data = {'account_id': tokens['account_id'], 'sub': principal}
        ident = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        return ident, claims
    except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
        raise ValueError('Saved ChatGPT login is invalid; sign in again') from None


class AccountVault:
    def __init__(self, root, codex_home):
        self.directory = Path(root) / 'state/accounts'
        self.auth_path = Path(codex_home) / 'auth.json'
        if self.directory.is_symlink():
            raise ValueError('Account storage must not be a symlink')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'posix':
            self.directory.chmod(0o700)

    def path(self, account_id):
        if not isinstance(account_id, str) or not re.fullmatch('[a-f0-9]{64}', account_id):
            raise ValueError('Invalid saved account ID')
        path = self.directory / (account_id + '.json')
        if path.is_symlink():
            raise ValueError('Account credentials must not be a symlink')
        return path

    def read(self, path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
            raise ValueError('Saved ChatGPT login is unavailable; sign in again')
        return path.read_bytes()

    def checkpoint(self, native_account, proof, expected_id=None):
        raw = self.read(self.auth_path)
        ident, claims = auth_identity(raw)
        if expected_id is not None and ident != expected_id:
            raise ValueError('Active login identity changed; refusing to overwrite another account')
        if not isinstance(native_account, dict) or native_account.get('type') != 'chatgpt':
            raise ValueError('A native-confirmed ChatGPT login is required')
        tokens = json.loads(raw)['tokens']
        # Metadata/email alone can describe the server's previous cached account.
        # Compare its loaded bearer only in server memory, never return/store it.
        if (not isinstance(proof, dict) or proof.get('authMethod') != 'chatgpt'
                or not isinstance(proof.get('authToken'), str)
                or not hmac.compare_digest(proof['authToken'].encode(), tokens['access_token'].encode())
                or proof.get('accountId') != tokens['account_id']):
            raise ValueError('Native login and fresh usage identity do not match the active credentials')
        email = native_account.get('email')
        if email and claims.get('email') and email != claims['email']:
            raise ValueError('Native account does not match the saved login')
        atomic_write(self.path(ident), raw)
        return {'account_id': ident, 'name': str(email or claims.get('email') or ('Account ' + ident[:8])),
                'plan': native_account.get('planType'), 'status': 'ready'}

    def install(self, account_id):
        """Controller only, after its durable idle barrier. Changes auth.json, never CODEX_HOME."""
        raw = self.read(self.path(account_id))
        if auth_identity(raw)[0] != account_id or self.auth_path.is_symlink():
            raise ValueError('Saved login identity does not match the selected account')
        atomic_write(self.auth_path, raw)

    def clear_active(self, account_id):
        # Local sign-out only, after checkpointing and the idle barrier. Upstream
        # logout can revoke the saved OAuth login and must never be used here.
        if auth_identity(self.read(self.path(account_id)))[0] != account_id:
            raise ValueError('The previous login is not safely saved')
        if self.auth_path.is_symlink():
            raise ValueError('Active credentials must not be a symlink')
        if self.auth_path.exists() and auth_identity(self.read(self.auth_path))[0] != account_id:
            raise ValueError('The active login changed during local sign-out')
        self.auth_path.unlink(missing_ok=True)

    def remove(self, account_id):
        self.path(account_id).unlink(missing_ok=True)


async def observe_account(native, vault, expected_id=None):
    """Controller lock required. Confirm the loaded login plus fresh provider quota.

    The legacy token-bearing RPC is private to the controller; its response must
    never enter dashboard state, notification payloads, journals or logs.
    """
    from .native import NativeError
    try:
        state = await native.rpc('account/read', {'refreshToken': False}, timeout=20)
        account = state.get('account')
        if account is None and state.get('requiresOpenaiAuth') is True:
            raise LoginRequired('Native Codex requires a regular login; sign in again')
        limits = await native.rpc('account/rateLimits/read', {}, timeout=20)
        proof = await native.rpc('getAuthStatus', {'includeToken': True, 'refreshToken': False}, timeout=20)
    except NativeError as exc:
        if any(word in str(exc).lower() for word in ('unauthorized', 'not authenticated', 'login required',
                'refresh_token_reused', 'refresh_token_expired', 'refresh_token_invalidated',
                'refresh token has expired', 'refresh token has already been used', 'refresh token was invalidated')):
            raise LoginRequired('Native Codex rejected the saved login; sign in again') from None
        raise  # Network/provider failures never invalidate a stored account.
    try:
        metadata = vault.checkpoint(account, {**proof, 'accountId': limits.get('accountId')}, expected_id)
    finally:
        proof.clear()
    usage = {key: limits.get(key) for key in ('ordinaryUsageAllowed', 'rateLimits', 'rateLimitsByLimitId')}
    return metadata, {**usage, 'account_id': metadata['account_id'], 'checked_at': time.time()}


def switching(controller):
    return controller.db.setting('account_switch', {}).get('phase') not in (None, 'complete', 'failed')


def wake_key(controller, project):
    account_id = controller.db.setting('active_account')
    return 'usage_wake/' + (account_id + '/' if account_id else '') + project['project_id']


def fresh_usage(account, account_id):
    stamp = account.get('checked_at')
    quota = windows(account)
    now = time.time()
    return bool(account.get('account_id') == account_id and account.get('ordinaryUsageAllowed') is True
                and number(stamp) and 0 <= now - stamp <= 90 and quota
                and not any(w['remaining'] == 0 or w['reset_at'] and stamp < w['reset_at'] <= now
                            for w in quota.values()))


def bind_legacy_limits(controller, account_id):
    """One-time original-account attribution, only after native identity confirmation."""
    with controller.db.transaction():
        for project in controller.db.all():
            ident = project['project_id']
            old_wake = controller.db.setting('usage_wake/' + ident)
            if old_wake:
                controller.db.set_setting('usage_wake/' + account_id + '/' + ident, old_wake)
            if project['goal_status'] != 'usage limited' or controller.db.setting('usage_account/' + ident):
                continue
            controller.db.set_setting('usage_account/' + ident, account_id)
            metadata = json.loads(project['usage_limit'] or '{}')
            if metadata:
                metadata['account_id'] = account_id
                controller.db.update(ident, usage_limit=json.dumps(metadata))
                controller.db.set_setting('usage_limits/' + account_id + '/' + ident, metadata)
            event = controller.db.conn.execute("SELECT event_id,payload FROM events WHERE project_id=? "
                "AND kind='usage limited' ORDER BY event_id DESC LIMIT 1", (ident,)).fetchone()
            if event:
                payload = json.loads(event['payload'])
                payload['account_id'] = account_id
                payload['failed_prompt'] = bool(controller.db.setting('prompt_limit/' + ident))
                if metadata:
                    payload['usage_limit'] = metadata
                controller.db.conn.execute('UPDATE events SET payload=? WHERE event_id=?', (json.dumps(payload), event['event_id']))


def holds_goal(controller, project):
    state = controller.db.setting('account_switch', {})
    wait = controller.db.setting('account_wait') or {}
    return bool((switching(controller) and state.get('project_id') == project['project_id'] and state.get('goal_hold'))
                or (wait.get('account_id') == controller.db.setting('active_account')
                    and wait.get('project_id') == project['project_id'] and wait.get('goal_hold')))


def vault(controller):
    if not hasattr(controller, 'account_vault'):
        controller.account_vault = AccountVault(controller.root, Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    return controller.account_vault


def remember(controller, metadata, usage):
    accounts = controller.db.setting('accounts', [])
    accounts = [metadata if item['account_id'] == metadata['account_id'] else item for item in accounts]
    if not any(item['account_id'] == metadata['account_id'] for item in accounts):
        accounts.append(metadata)
    controller.db.set_setting('accounts', accounts)
    controller.db.record_usage(usage, metadata['account_id'])


async def refresh(controller):
    expected = controller.db.setting('active_account')
    try:
        metadata, usage = await observe_account(controller.native, vault(controller), expected)
    except LoginRequired:
        if expected:
            mark_login_required(controller, expected)
        raise
    if not expected:
        controller.db.bind_legacy_usage(metadata['account_id'])
        bind_legacy_limits(controller, metadata['account_id'])
    remember(controller, metadata, usage)
    if not expected:
        controller.db.activate_account(metadata['account_id'])
    controller.health_errors.pop('account_usage', None)
    return usage


def failed_resume(project):
    operation = json.loads(project['operation'] or '{}')
    result = json.loads(project['resume_result'] or '{}')
    return bool(operation.get('kind') == 'resume' and operation.get('error') and operation.get('id')
                and result.get('id') == operation['id'] and result.get('status') == 'failed')


async def native_limit(controller, project, goal):
    if goal and goal.get('status') == 'usageLimited':
        return True
    receipt = controller.db.setting('prompt_limit/' + project['project_id']) or {}
    if receipt.get('turn_id'):
        turns = (await controller.native.rpc('thread/turns/list', {
            'threadId': project['codex_session_id'], 'limit': 100, 'sortDirection': 'desc'}))['data']
        return any(t['id'] == receipt['turn_id'] and t['status'] == 'failed'
                   and (t.get('error') or {}).get('codexErrorInfo') == 'usageLimitExceeded' for t in turns)
    return False


async def automatic_change(controller):
    """Existing scheduler only: one durable probe per account and real reset epoch."""
    if not controller.db.setting('auto_account_change', False) or controller.db.setting('pause_all', False):
        return
    selected, current = controller.db.setting('selected'), controller.db.setting('active_account')
    if not selected or not current:
        return
    project = controller.db.get(selected)
    if (project['queue_position'] != 1 or not controller.can_auto_resume(project)
            or project['goal_status'] != 'usage limited' or project['operation'] and not failed_resume(project)):
        return
    event = controller.db.conn.execute("SELECT event_id FROM events WHERE project_id=? AND kind='usage limited' "
                                      "ORDER BY event_id DESC LIMIT 1", (selected,)).fetchone()
    if not event:
        return  # No invented limit events from idle time or account availability.
    state = controller.db.setting('account_selection', {})
    if state.get('event_id') != event['event_id']:
        state = {'event_id': event['event_id'], 'project_id': selected, 'attempted': [], 'reset_probes': {}}
    if time.time() < state.get('next_check', 0):
        return
    state['next_check'] = time.time() + 20
    controller.db.set_setting('account_selection', state)
    goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
    if not await native_limit(controller, project, goal):
        return
    # Fresh current usage can keep the current account. Cached positive usage
    # is never sufficient to start work or avoid a needed account check.
    usage = await refresh(controller)
    if fresh_usage(usage, current):
        return  # Unsnooze/confirmation handles the current session, not another switch.
    accounts = controller.db.setting('accounts', [])
    snapshots = {a['account_id']: controller.db.setting('account_usage/' + a['account_id'], {}) for a in accounts}
    if current not in state['attempted']:
        state['attempted'].append(current)
    now = time.time()
    for account_id, snapshot in snapshots.items():
        resets = [w['reset_at'] for w in windows(snapshot).values()
                  if w['remaining'] == 0 and w['reset_at'] and w['reset_at'] <= now]
        reset = max(resets, default=0)
        if reset > state['reset_probes'].get(account_id, 0):
            state['reset_probes'][account_id] = reset
            state['attempted'] = [a for a in state['attempted'] if a != account_id]
    candidate = choose_account(accounts, snapshots, now, state['attempted'])
    state['next_check'] = now + 20
    state['waiting_for'] = candidate
    if candidate and candidate['mode'] == 'wait':
        state['next_check'] = min(candidate['reset_at'], now + 60)
    controller.db.set_setting('account_selection', state)
    if not candidate or candidate['account_id'] == current:
        return
    if candidate['mode'] == 'wait' and candidate['reason'] == 'weekly exhausted':
        return  # Weekly-empty logins are never installed before their real reset.
    target = candidate['account_id']
    state['attempted'] = list(dict.fromkeys(state['attempted'] + [target]))
    controller.db.set_setting('account_selection', state)  # Persist before touching auth or sending anything.
    await request_switch(controller, target, automatic=True)


async def request_switch(controller, account_id, *, automatic=False, adding=False):
    """Called under the controller lock; persist intent before stopping continuation."""
    if switching(controller):
        raise ValueError('An account change is already pending')
    if adding:
        if automatic or not controller.windows_online:
            raise ValueError('Connect the Windows worker before adding an account')
    else:
        saved = next((a for a in controller.db.setting('accounts', []) if a['account_id'] == account_id), None)
        if not saved or saved.get('status') != 'ready':
            raise ValueError('Selected account needs a regular Codex login')
        try:
            if auth_identity(vault(controller).read(vault(controller).path(account_id)))[0] != account_id:
                raise ValueError('Saved login identity does not match the selected account')
        except ValueError:
            controller.db.set_setting('accounts', [dict(a, status='needs_login') if a['account_id'] == account_id else a
                                                 for a in controller.db.setting('accounts', [])])
            raise
    current = controller.db.setting('active_account')
    if not current:
        raise ValueError('The current native account has not been confirmed yet')
    if any(p['lifecycle'] != 'ready' or p['operation'] and not failed_resume(p) for p in controller.db.all()):
        raise ValueError('Wait for project lifecycle/resume operations before changing account')
    state = {'id': str(uuid.uuid4()), 'phase': 'complete' if current == account_id else 'waiting_turn',
             'old_account': current, 'target_account': account_id, 'requested_at': time.time(),
             'automatic': automatic, 'kind': 'add' if adding else 'switch'}
    selected = controller.db.setting('selected')
    if selected:
        project = controller.db.get(selected)
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if goal and goal['status'] in ('active', 'usageLimited') and controller.can_auto_resume(project):
            state.update(project_id=selected, session_id=project['codex_session_id'],
                project_path=project['project_path'], goal_created_at=goal.get('createdAt'),
                objective_hash=hashlib.sha256(goal['objective'].encode()).hexdigest(),
                before_status=goal['status'], goal_hold=goal['status'] == 'active')
    if automatic:
        if (not controller.db.setting('auto_account_change', False) or not selected
                or not await native_limit(controller, project, goal)):
            raise ValueError('Automatic account changes require Auto Account Change and a genuine native usage-limited goal or turn')
        if not goal or goal['status'] != 'usageLimited':
            state.pop('project_id', None)  # Failed user prompts are never replayed.
    controller.db.set_setting('account_switch', state)
    return {'ok': True, 'operation_id': state['id']}


def public_state(controller):
    """Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error."""
    state = controller.db.setting('account_switch', {})
    operation = {key: state[key] for key in ('id', 'phase', 'kind', 'old_account', 'target_account',
        'requested_at', 'completed_at', 'error', 'failed_phase', 'project_id') if key in state}
    if state.get('phase') == 'complete' and state.get('project_id'):
        try:
            project = controller.db.get(state['project_id'])
        except KeyError:
            pass
        else:
            pending = json.loads(project['operation'] or '{}')
            result = json.loads(project['resume_result'] or '{}')
            if pending.get('id') == state['id'] and not pending.get('error'):
                operation['phase'] = 'confirming_resume'
            elif result.get('id') == state['id']:
                operation['resume_status'] = result.get('status')
                operation['message'] = controller.redactor.clean(str(result.get('message', '')))
                if result.get('status') in ('failed', 'cancelled'):
                    operation.update(phase='failed', error=operation['message'])
    return {'active_account': controller.db.setting('active_account'),
            'accounts': [{key: item.get(key) for key in ('account_id', 'name', 'plan', 'status')}
                         for item in controller.db.setting('accounts', [])],
            'auto_account_change': controller.db.setting('auto_account_change', False),
            'account_operation': operation, 'account_wait': controller.db.setting('account_wait'),
            'account_selection': controller.db.setting('account_selection', {}).get('waiting_for')}


async def notification(controller, value):
    if value.get('method') == 'account/login/completed':
        params = value.get('params', {})
        # No RPC/lock wait here: the native reader must keep delivering replies.
        controller.db.set_setting('account_login_result', {
            'login_id': params.get('loginId'), 'success': params.get('success') is True})


async def recover_switch(controller, *, restore=False):
    state = controller.db.setting('account_switch', {})
    if state.get('phase') != 'recovery_required' and not (restore and state.get('kind') == 'add' and state.get('phase') == 'logging_in'):
        raise ValueError('No failed or pending login is waiting for account recovery')
    if restore:
        if state.get('login_id'):
            await controller.native.rpc('account/login/cancel', {'loginId': state['login_id']}, timeout=15)
        vault(controller).read(vault(controller).path(state['old_account']))
        state.update(kind='switch', target_account=state['old_account'], phase='waiting_turn',
                     automatic=False, restoring=True, requested_at=time.time())
        for key in ('restart_requested_at', 'login_id', 'login_url', 'login_requested_at', 'login_sent_at'):
            state.pop(key, None)
    else:
        if state.get('failed_phase') == 'starting_login':
            raise ValueError('Login startup was interrupted; restore the previous account before starting a new login')
        state['phase'] = state['failed_phase']
    state.pop('error', None)
    controller.db.set_setting('account_switch', state)
    return {'ok': True, 'operation_id': state['id']}


def remove_account(controller, account_id, confirmation, *, recovering=False):
    if switching(controller):
        raise ValueError('Wait for the pending account change before removing an account')
    account = next((a for a in controller.db.setting('accounts', []) if a['account_id'] == account_id), None)
    if not account and not recovering:
        raise ValueError('Saved account was not found')
    if controller.db.setting('active_account') == account_id:
        raise ValueError('Switch to another account before removing the active account')
    if not recovering and (not isinstance(confirmation, str) or confirmation != account['name']):
        raise ValueError('Confirm removal with the exact account name')
    controller.db.set_setting('account_remove', {'account_id': account_id})
    vault(controller).remove(account_id)
    with controller.db.transaction():
        controller.db.delete_account_usage(account_id)
        controller.db.conn.execute("DELETE FROM settings WHERE substr(key,1,length(?))=? OR substr(key,1,length(?))=?",
            ('usage_wake/' + account_id + '/', 'usage_wake/' + account_id + '/',
             'usage_limits/' + account_id + '/', 'usage_limits/' + account_id + '/'))
        controller.db.set_setting('accounts', [a for a in controller.db.setting('accounts', []) if a['account_id'] != account_id])
        controller.db.set_setting('account_remove', None)


async def reload_native(controller, state):
    """One journaled restart, then bounded observations; never replay a model request."""
    from .controller import command
    from .native import Native
    controller.account_reloading = True
    try:
        if not state.get('restart_requested_at'):
            state['restart_requested_at'] = time.time()
            controller.db.set_setting('account_switch', state)
            await controller.native.close()
            await command('systemctl', '--user', 'restart', 'codexpi-native.service', timeout=45)
        elif controller.native:
            await controller.native.close()
        deadline = time.monotonic() + 90
        while True:
            try:
                controller.native = await asyncio.wait_for(
                    Native(controller.root / 'state/native.sock', lambda value: notification(controller, value)).connect(),
                    min(15, max(0.1, deadline - time.monotonic())))
                return
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Native Codex did not reconnect after account change; no goal was resumed') from None
                await asyncio.sleep(1)
    finally:
        controller.account_reloading = False


async def tick(controller):
    """Advance the durable account operation under the same single-project lock."""
    from .native import idle_thread
    removing = controller.db.setting('account_remove')
    if removing:
        remove_account(controller, removing['account_id'], None, recovering=True)
    state = controller.db.setting('account_switch', {})
    if not switching(controller):
        await automatic_change(controller)
        return
    if state.get('phase') == 'recovery_required':
        return
    if state.get('automatic') and not controller.db.setting('auto_account_change', False):
        # Disabling the policy cancels an uninstalled target or safely rolls
        # back an already installed login, through the same idle barrier.
        state.update(automatic=False, restoring=True, target_account=state['old_account'],
                     phase='waiting_turn', requested_at=time.time())
        state.pop('restart_requested_at', None)
        controller.db.set_setting('account_switch', state)
    try:
        if state['phase'] == 'waiting_turn':
            if state.get('goal_hold'):
                try:
                    project = controller.db.get(state['project_id'])
                except KeyError:
                    state.pop('project_id', None)  # Deleted projects must never resume.
                else:
                    goal = (await controller.native.rpc('thread/goal/get', {'threadId': state['session_id']})).get('goal')
                    if not goal:
                        state.pop('project_id', None)
                        state['goal_hold'] = False  # Explicit native clear revokes continuation.
                    elif (goal.get('createdAt') != state['goal_created_at']
                            or hashlib.sha256(goal['objective'].encode()).hexdigest() != state['objective_hash']):
                        raise ValueError('Native goal changed while the account switch was waiting')
                    if goal and goal['status'] == 'active':
                        # Native pause only disables future continuation. Never interrupt
                        # the current turn: its Windows work must still be allowed to finish.
                        await controller.native.rpc('thread/goal/set', {'threadId': state['session_id'], 'status': 'paused'})
            loaded = await controller.native.rpc('thread/loaded/list', {})
            for session in loaded['data']:
                if not await idle_thread(controller.native, session):
                    if time.time() - state['requested_at'] > 3600:
                        raise RuntimeError('Account change timed out waiting for the current native turn; it was not interrupted')
                    return
            if controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone():
                return
            from .prompts import active
            if any(active(controller, p) for p in controller.db.all()):
                return  # Reconciliation, not a second send, must settle user prompts.
            state['phase'] = 'checkpointing'
        elif state['phase'] == 'checkpointing':
            if not state.get('restoring'):
                try:
                    await refresh(controller)  # Save native-managed token rotation to the OLD slot.
                except LoginRequired:
                    # Keep the previously confirmed recovery slot untouched. An
                    # expired login must not prevent a normal login/new valid account.
                    saved = vault(controller)
                    if (auth_identity(saved.read(saved.path(state['old_account'])))[0] != state['old_account']
                            or saved.auth_path.exists() and auth_identity(saved.read(saved.auth_path))[0] != state['old_account']):
                        raise ValueError('The previous account identity changed; recovery is required')
            state['phase'] = 'installing'
        elif state['phase'] == 'installing':
            # The previous tick persisted this phase before touching auth.json.
            if state.get('kind') == 'add':
                vault(controller).clear_active(state['old_account'])
            else:
                vault(controller).install(state['target_account'])
            state['phase'] = 'reloading'
        elif state['phase'] == 'reloading':
            await reload_native(controller, state)
            state['phase'] = 'starting_login' if state.get('kind') == 'add' else 'verifying'
        elif state['phase'] == 'starting_login':
            if state.get('login_requested_at'):
                raise RuntimeError('Ambiguous native login startup; restore the saved account')
            state['login_requested_at'] = time.time()
            controller.db.set_setting('account_login_result', None)
            controller.db.set_setting('account_login_browser', None)
            controller.db.set_setting('account_switch', state)
            result = await controller.native.rpc('account/login/start', {'type': 'chatgpt'}, timeout=30)
            if result.get('type') != 'chatgpt' or str(uuid.UUID(result['loginId'])) != result['loginId']:
                raise ValueError('Unexpected native login result')
            state.update(login_id=result['loginId'], login_url=codex_login_url(result['authUrl']), phase='logging_in')
        elif state['phase'] == 'logging_in':
            if time.time() - state['login_requested_at'] > 600:
                raise RuntimeError('Native browser login timed out')
            result = controller.db.setting('account_login_result') or {}
            browser = controller.db.setting('account_login_browser') or {}
            if browser.get('operation_id') == state['id'] and browser.get('opened') is False:
                raise RuntimeError('The Windows worker could not open the browser callback tunnel')
            if result.get('login_id') == state['login_id'] and not result['success']:
                raise RuntimeError('Native browser login was not completed')
            if vault(controller).auth_path.exists():
                # Also recover a successful callback whose notification was lost
                # during a controller restart. Fresh native proof still follows.
                state['phase'] = 'verifying'
            elif controller.windows_online and time.time() - state.get('login_sent_at', 0) >= 20:
                from .worker_server import send
                await send(controller, {'type': 'account_login', 'operation_id': state['id'],
                    'url': state['login_url'], 'expires_at': state['login_requested_at'] + 600})
                state['login_sent_at'] = time.time()
        elif state['phase'] == 'verifying':
            metadata, usage = await observe_account(controller.native, vault(controller), state['target_account'])
            if state.get('kind') == 'add' and controller.windows_online:
                from .worker_server import send
                await send(controller, {'type': 'account_login_close', 'operation_id': state['id']})
            remember(controller, metadata, usage)
            for index, project in enumerate(controller.db.all()):
                # Upstream Snooze entries are keyed by session, not account. Retain
                # their DB reset history, but disarm timers from the previous login.
                await controller.cancel_wakes(project, refresh=index == 0)
            controller.db.activate_account(metadata['account_id'])
            state['target_account'] = metadata['account_id']
            state.pop('login_url', None)
            state['phase'] = 'resuming'
        elif state['phase'] == 'resuming':
            await finish_switch(controller, state)
            state['phase'] = 'complete'
            state['completed_at'] = time.time()
        controller.db.set_setting('account_switch', state)
        controller.health_errors.pop('accounts', None)
    except Exception as exc:
        # Native errors may contain provider/auth details. A recovery journal
        # needs the phase, not credential-bearing response text.
        errors = {'waiting_turn': 'The current native turn did not settle; it was not interrupted.',
            'checkpointing': 'The previous account could not be confirmed and safely saved.',
            'installing': 'The selected login could not be installed safely.',
            'reloading': 'Native Codex did not reconnect after changing the login.',
            'starting_login': 'Native browser login could not be started; restore the saved account.',
            'logging_in': 'Browser login failed or timed out; restore the saved account or retry verification.',
            'verifying': 'The loaded account and its fresh quota could not be confirmed.',
            'resuming': 'Account changed, but the original project continuation could not be confirmed.'}
        state.update(failed_phase=state['phase'], phase='recovery_required',
                     error=errors.get(state['phase'], 'Account change could not be confirmed.'))
        if state['failed_phase'] == 'verifying' and state.get('kind') != 'add' and isinstance(exc, LoginRequired):
            target = state['target_account']
            mark_login_required(controller, target)
            if state.get('automatic') and target != state['old_account']:
                state.update(target_account=state['old_account'], phase='waiting_turn', restoring=True, requested_at=time.time())
                state.pop('restart_requested_at', None)  # One new reload for this bounded rollback.
        controller.db.set_setting('account_switch', state)
        controller.health_errors['accounts'] = state['error']


async def finish_switch(controller, state):
    """Hand continuation back to the existing genuine mapped-TUI resume journal."""
    if not state.get('project_id'):
        return
    try:
        project = controller.db.get(state['project_id'])
    except KeyError:
        return
    if (controller.db.setting('selected') != project['project_id'] or not controller.can_auto_resume(project)
            or project['codex_session_id'] != state['session_id'] or project['project_path'] != state['project_path']
            or project['operation'] and not failed_resume(project)):
        return
    goal = (await controller.native.rpc('thread/goal/get', {'threadId': state['session_id']})).get('goal')
    if (not goal or goal.get('createdAt') != state['goal_created_at']
            or hashlib.sha256(goal['objective'].encode()).hexdigest() != state['objective_hash']
            or goal['status'] not in ('paused', 'usageLimited')):
        return
    account = controller.db.setting('account_usage', {})
    quota = windows(account)
    if failed_resume(project):
        # The shared barrier already proved all native turns/jobs idle and the
        # same goal. A terminal failed receipt is not another executing operation.
        controller.db.update(project['project_id'], operation=None)
    queue_wait = project['queue_position'] != 1
    if queue_wait or not fresh_usage(account, state['target_account']):
        controller.db.set_setting('account_wait', {key: state[key] for key in (
            'project_id', 'session_id', 'project_path', 'goal_created_at', 'objective_hash', 'goal_hold')}
            | {'account_id': state['target_account'], 'checked_at': account.get('checked_at'),
               'reason': 'queue' if queue_wait else 'usage',
               'reset_at': max((w['reset_at'] for w in quota.values() if w['remaining'] == 0 and w['reset_at']), default=None)})
        return  # No quota is invented; retain the real native limit for Unsnooze.
    controller.db.set_setting('account_wait', None)
    controller.db.update(project['project_id'], usage_limit=None, resume_result=None,
        operation=json.dumps({'kind': 'resume', 'source': 'account-switch', 'id': state['id'],
                              'requested_at': time.time(), 'account_id': state['target_account']}))


async def resume_account_wait(controller):
    """Use the existing reset poll and mapped resume, not another scheduler/daemon."""
    from .native import idle_thread
    wait = controller.db.setting('account_wait') or {}
    if not wait or wait.get('account_id') != controller.db.setting('active_account'):
        return False
    try:
        project = controller.db.get(wait['project_id'])
    except KeyError:
        controller.db.set_setting('account_wait', None)
        return False
    if (not controller.can_auto_resume(project)
            or project['codex_session_id'] != wait['session_id'] or project['project_path'] != wait['project_path']):
        controller.db.set_setting('account_wait', None)
        return False
    if project['queue_position'] != 1:
        return False  # Reordering defers this waiter; it never revokes reset eligibility.
    selected = controller.db.setting('selected')
    if selected and selected != project['project_id']:
        return False  # Never preempt another selected project for an account wake.
    if project['operation']:
        return True  # An existing resume owns its own confirmation/deduplication.
    goal = (await controller.native.rpc('thread/goal/get', {'threadId': wait['session_id']})).get('goal')
    if (not goal or goal.get('createdAt') != wait['goal_created_at']
            or hashlib.sha256(goal['objective'].encode()).hexdigest() != wait['objective_hash']
            or goal['status'] not in ('paused', 'usageLimited')):
        controller.db.set_setting('account_wait', None)
        return False
    account = controller.db.setting('account_usage', {})
    if (not fresh_usage(account, wait['account_id']) or not number(wait.get('checked_at'))
            or account['checked_at'] <= wait['checked_at']
            or controller.db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone()
            or not await idle_thread(controller.native, wait['session_id'])):
        return True
    if not selected:
        from .prompts import active
        if any(p['operation'] or active(controller, p) for p in controller.db.all()):
            return True
        loaded = await controller.native.rpc('thread/loaded/list', {})
        for session in loaded['data']:
            if not await idle_thread(controller.native, session):
                return True  # Missing selection is not proof of an idle native runtime.
    with controller.db.transaction():
        if not selected:
            controller.select(project['project_id'])  # Already the head; no queue reordering.
        controller.db.update(project['project_id'], usage_limit=None, resume_result=None,
            operation=json.dumps({'kind': 'resume', 'source': 'account-reset', 'id': str(uuid.uuid4()),
                'requested_at': time.time(), 'account_id': wait['account_id']}))
        controller.db.set_setting('account_wait', None)
    return True
