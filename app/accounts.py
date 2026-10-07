"""Private managed-Codex auth slots. Never store tokens in DB, browser state or logs."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re

from .common import atomic_write


def auth_identity(raw):
    """Decode identity, not authenticity; the native account/limits RPC confirms the login."""
    try:
        auth = json.loads(raw)
        tokens = auth['tokens']
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

    def checkpoint(self, native_account, expected_id=None):
        raw = self.read(self.auth_path)
        ident, claims = auth_identity(raw)
        if expected_id is not None and ident != expected_id:
            raise ValueError('Active login identity changed; refusing to overwrite another account')
        if not isinstance(native_account, dict) or native_account.get('type') != 'chatgpt':
            raise ValueError('A native-confirmed ChatGPT login is required')
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
