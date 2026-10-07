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

from .common import atomic_write
from .usage import number, windows


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

    def remove(self, account_id):
        self.path(account_id).unlink(missing_ok=True)


async def observe_account(native, vault, expected_id=None):
    """Controller lock required. Confirm the loaded login plus fresh provider quota.

    The legacy token-bearing RPC is private to the controller; its response must
    never enter dashboard state, notification payloads, journals or logs.
    """
    account = (await native.rpc('account/read', {'refreshToken': False}, timeout=20)).get('account')
    limits = await native.rpc('account/rateLimits/read', {}, timeout=20)
    proof = await native.rpc('getAuthStatus', {'includeToken': True, 'refreshToken': False}, timeout=20)
    try:
        metadata = vault.checkpoint(account, {**proof, 'accountId': limits.get('accountId')}, expected_id)
    finally:
        proof.clear()
    usage = {key: limits.get(key) for key in ('ordinaryUsageAllowed', 'rateLimits', 'rateLimitsByLimitId')}
    return metadata, {**usage, 'account_id': metadata['account_id'], 'checked_at': time.time()}


def switching(controller):
    return controller.db.setting('account_switch', {}).get('phase') not in (None, 'complete', 'failed')


def holds_goal(controller, project):
    state = controller.db.setting('account_switch', {})
    return bool(switching(controller) and state.get('project_id') == project['project_id']
                and state.get('goal_hold'))


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
    metadata, usage = await observe_account(controller.native, vault(controller), expected)
    if not expected:
        controller.db.bind_legacy_usage(metadata['account_id'])
    remember(controller, metadata, usage)
    if not expected:
        controller.db.activate_account(metadata['account_id'])
    controller.health_errors.pop('account_usage', None)
    return usage


async def request_switch(controller, account_id, *, automatic=False):
    """Called under the controller lock; persist intent before stopping continuation."""
    if switching(controller):
        raise ValueError('An account change is already pending')
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
    if any(p['lifecycle'] != 'ready' or p['operation'] for p in controller.db.all()):
        raise ValueError('Wait for project lifecycle/resume operations before changing account')
    state = {'id': str(uuid.uuid4()), 'phase': 'complete' if current == account_id else 'waiting_turn',
             'old_account': current, 'target_account': account_id, 'requested_at': time.time(),
             'automatic': automatic}
    selected = controller.db.setting('selected')
    if selected:
        project = controller.db.get(selected)
        goal = (await controller.native.rpc('thread/goal/get', {'threadId': project['codex_session_id']})).get('goal')
        if goal and goal['status'] in ('active', 'usageLimited') and controller.can_auto_resume(project):
            state.update(project_id=selected, session_id=project['codex_session_id'],
                project_path=project['project_path'], goal_created_at=goal.get('createdAt'),
                objective_hash=hashlib.sha256(goal['objective'].encode()).hexdigest(),
                before_status=goal['status'], goal_hold=goal['status'] == 'active')
    if automatic and (not controller.db.setting('auto_account_change', False)
                      or state.get('before_status') != 'usageLimited'):
        raise ValueError('Automatic account changes require Auto Account Change and a genuine native usage-limited goal')
    controller.db.set_setting('account_switch', state)
    return {'ok': True, 'operation_id': state['id']}


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
                    Native(controller.root / 'state/native.sock').connect(),
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
    state = controller.db.setting('account_switch', {})
    if not switching(controller) or state.get('phase') == 'recovery_required':
        return
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
            await refresh(controller)  # Save any native-managed token rotation to the OLD slot.
            state['phase'] = 'installing'
        elif state['phase'] == 'installing':
            # The previous tick persisted this phase before touching auth.json.
            vault(controller).install(state['target_account'])
            state['phase'] = 'reloading'
        elif state['phase'] == 'reloading':
            await reload_native(controller, state)
            state['phase'] = 'verifying'
        elif state['phase'] == 'verifying':
            metadata, usage = await observe_account(controller.native, vault(controller), state['target_account'])
            remember(controller, metadata, usage)
            controller.db.activate_account(metadata['account_id'])
            state['phase'] = 'resuming'
        elif state['phase'] == 'resuming':
            await finish_switch(controller, state)
            state['phase'] = 'complete'
            state['completed_at'] = time.time()
        controller.db.set_setting('account_switch', state)
        controller.health_errors.pop('accounts', None)
    except Exception:
        # Native errors may contain provider/auth details. A recovery journal
        # needs the phase, not credential-bearing response text.
        state.update(failed_phase=state['phase'], phase='recovery_required',
                     error='Account change could not be confirmed; controller recovery is required. No work was resumed.')
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
            or project['operation']):
        return
    goal = (await controller.native.rpc('thread/goal/get', {'threadId': state['session_id']})).get('goal')
    if (not goal or goal.get('createdAt') != state['goal_created_at']
            or hashlib.sha256(goal['objective'].encode()).hexdigest() != state['objective_hash']
            or goal['status'] not in ('paused', 'usageLimited')):
        return
    account = controller.db.setting('account_usage', {})
    quota = windows(account)
    if (account.get('account_id') != state['target_account'] or account.get('ordinaryUsageAllowed') is not True
            or not quota or any(w['remaining'] == 0 for w in quota.values())):
        return  # No quota is invented; retain the real native limit for Unsnooze.
    await controller.cancel_wakes(project, refresh=True)
    controller.db.update(project['project_id'], usage_limit=None, resume_result=None,
        operation=json.dumps({'kind': 'resume', 'source': 'account-switch', 'id': state['id'],
                              'requested_at': time.time(), 'account_id': state['target_account']}))
