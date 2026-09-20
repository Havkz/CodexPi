import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
import unicodedata

STATUSES = ('active', 'paused', 'stalled', 'usage limited', 'limited by budget', 'complete')
NATIVE_STATUS = {'active': 'active', 'paused': 'paused', 'blocked': 'stalled',
                 'usageLimited': 'usage limited', 'budgetLimited': 'limited by budget',
                 'complete': 'complete'}


def slugify(name):
    name = name.strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Project name must contain 1-80 printable characters')
    plain = unicodedata.normalize('NFKD', name.replace('ß', 'ss')).encode('ascii', 'ignore').decode()
    slug = re.sub('[^a-z0-9]+', '-', plain.lower()).strip('-')
    if not slug or len(slug) > 80:
        raise ValueError('Project name needs at least one Latin letter or number')
    return slug


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.chmod(temp, mode)
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name == 'posix':
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_env(path):
    if not Path(path).exists():
        return {}
    return dict(line.split('=', 1) for line in Path(path).read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8,
                            p=1, maxmem=64 * 1024 * 1024).hex()
    return 'scrypt$32768$8$1$' + salt + '$' + digest


def password_valid(password, encoded):
    try:
        algorithm, n, r, p, salt, digest = encoded.split('$')
        if (algorithm, n, r, p) != ('scrypt', '32768', '8', '1'):
            return False
        return hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


class SignedChannel:
    """Per-connection random challenge + directional MAC + monotonic sequence."""
    def __init__(self, key, challenge, sender):
        if len(key) < 32 or len(challenge) < 32 or sender not in ('worker', 'controller'):
            raise ValueError('Invalid channel credentials')
        self.key = key.encode()
        self.challenge = challenge
        self.sender = sender
        self.sent = 0
        self.received = 0

    def sign(self, body):
        self.sent += 1
        msg = {'challenge': self.challenge, 'sender': self.sender,
               'seq': self.sent, 'ts': int(time.time()), 'body': body}
        msg['mac'] = hmac.new(self.key, canonical(msg), hashlib.sha256).hexdigest()
        return msg

    def verify(self, msg):
        if not isinstance(msg, dict) or set(msg) != {'challenge', 'sender', 'seq', 'ts', 'body', 'mac'}:
            raise ValueError('Malformed signed message')
        value = {k: v for k, v in msg.items() if k != 'mac'}
        expected = hmac.new(self.key, canonical(value), hashlib.sha256).hexdigest()
        if not isinstance(msg['mac'], str) or not hmac.compare_digest(expected, msg['mac']):
            raise ValueError('Invalid message authentication')
        other = 'worker' if self.sender == 'controller' else 'controller'
        if (msg['challenge'] != self.challenge or msg['sender'] != other or
                type(msg['seq']) is not int or msg['seq'] != self.received + 1 or
                type(msg['ts']) is not int or abs(time.time() - msg['ts']) > 60):
            raise ValueError('Stale, replayed or misdirected message')
        if not isinstance(msg['body'], dict):
            raise ValueError('Invalid message body')
        self.received = msg['seq']
        return msg['body']


class Redactor:
    def __init__(self, root):
        self.root = Path(root)

    def clean(self, value):
        text = str(value)
        paths = [self.root / '.env', *self.root.glob('projects/*/.env')]
        for path in paths:
            for secret in read_env(path).values():
                if secret:
                    text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'(?i)(?:gh[pousr]_[a-z0-9_]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9_-]{20,})',
                      '[REDACTED]', text)
        return text
