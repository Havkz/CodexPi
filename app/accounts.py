"""Private managed-Codex auth slots. Never store tokens in DB, browser state or logs."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time

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
