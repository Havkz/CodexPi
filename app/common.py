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
from urllib.parse import parse_qs, urlsplit

STATUSES = ('active', 'paused', 'stalled', 'usage limited', 'limited by budget', 'complete')
NATIVE_STATUS = {'active': 'active', 'paused': 'paused', 'blocked': 'stalled',
                 'usageLimited': 'usage limited', 'budgetLimited': 'limited by budget',
                 'complete': 'complete'}


def codex_login_url(value):
    """Only the native managed OAuth ceremony, never an arbitrary worker/browser URL."""
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 33 for c in value):
        raise ValueError('Invalid native Codex login URL')
    url = urlsplit(value)
    query = parse_qs(url.query)
    if (url.scheme != 'https' or url.netloc not in ('auth.openai.com', 'chatgpt.com')
            or url.path not in ('/oauth/authorize', '/auth/authorize') or url.fragment
            # Current native Codex uses the IPv4 loopback spelling; no other
            # host, port or callback path is admitted by either Pi or worker.
            or query.get('redirect_uri') not in (['http://localhost:1455/auth/callback'],
                                                 ['http://127.0.0.1:1455/auth/callback'])
            or query.get('response_type') != ['code'] or len(query.get('state', [])) != 1
            or len(query.get('code_challenge', [])) != 1
            or query.get('code_challenge_method') != ['S256']
            or any(key in query for key in ('access_token', 'refresh_token', 'id_token', 'code'))):
        raise ValueError('Login requires the official Codex OAuth URL and its local callback')
    return value


def block_summary(project, reason=None, status=None):
    """Presentation only: never change native status or resume authorization."""
    status = status or project.get('goal_status')
    raw = project.get('block_reason') if reason is None else reason
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {'reason': raw}
    raw = raw if isinstance(raw, dict) else {}
    if not raw and status not in ('stalled', 'usage limited', 'limited by budget'):
        return None

    def short(value, limit):
        value = ' '.join(value.split()) if isinstance(value, str) else ''
        return value if len(value) <= limit else value[:limit].rsplit(' ', 1)[0] + '…'

    def items(value, limit):
        values = value if isinstance(value, list) else [value]
        result = list(dict.fromkeys(text for item in values if (text := short(item, limit))))
        return result[:5] + ['Weitere Einträge: technische Details öffnen.'] if len(result) > 6 else result

    details = raw.get('details') if isinstance(raw.get('details'), str) else ''
    reset = None
    if status == 'usage limited':
        limit = project.get('usage_limit') or {}
        if isinstance(limit, str):
            try:
                limit = json.loads(limit)
            except ValueError:
                limit = {}
        reset = limit.get('resetAt') if isinstance(limit, dict) else None
        reasons = ['OpenAI-Codex-Usage-Limit erreicht']
        explanation = 'Die native Codex-Session meldet ein ausgeschöpftes Usage-Limit.'
        solution = ['Auf den tatsächlichen Reset warten. Unsnooze setzt nur eine weiterhin berechtigte Session fort.']
    elif status == 'limited by budget':
        reasons = ['Goal-Tokenbudget erreicht']
        explanation = 'Das native Goal kann innerhalb seines gesetzten Tokenbudgets nicht weiterarbeiten.'
        solution = ['Das Goal-Budget prüfen und bei Bedarf ausdrücklich erhöhen; danach Resume verwenden.']
    else:
        reasons = items(raw.get('reasons') or raw.get('reason'), 140) or ['Native Goal blockiert']
        explanation = short(raw.get('explanation'), 320)
        solution = [short(raw['question'], 1000)] if isinstance(raw.get('question'), str) and raw['question'].strip() else items(raw.get('solution'), 240)
        if raw.get('reason') == 'Windows offline':
            explanation = explanation or 'Der benötigte Windows-Worker hat keine frische authentifizierte Verbindung.'
            solution = solution or ['Windows-PC und CodexPi-Worker starten. Nach gültigem Heartbeat wird das berechtigte Queue-Projekt fortgesetzt.']
        elif raw.get('requires_user'):
            explanation = explanation or 'Eine Nutzerentscheidung oder Information fehlt; automatisches Resume bleibt gesperrt.'
            # Preserve an explicitly recorded request; never invent a decision from logs.
            requests = [s for s in re.split(r'(?<=[.!?])\s+|\n+', details)
                        if re.match(r'(?i)^(please\b|bitte\b|user direction\b|user decision\b|entscheide\b)', s.strip())]
            solution = solution or items(requests, 240) or ['Die konkrete fehlende Entscheidung ist nicht separat angegeben. Technische Details öffnen und in der Projekt-Session klären.']
        elif raw.get('reason') == 'Completion verification failed':
            explanation = explanation or short(details, 320)
            solution = solution or ['Uncommittete Änderungen beziehungsweise den fehlgeschlagenen CI-Run prüfen, korrigieren, committen und pushen; danach Resume verwenden.']
        elif raw.get('reason') == 'Deployment verification failed':
            explanation = explanation or 'Die Auslieferungsprüfung ist fehlgeschlagen; das Projekt gilt nicht als erfolgreich ausgeliefert.'
            solution = solution or ['Den Auslieferungsfehler in den technischen Details prüfen und in derselben Projekt-Session beheben; danach erneut verifizieren.']
        else:
            explanation = explanation or 'Das native Goal wartet auf die gemeldete Voraussetzung; Details sind separat verfügbar.'
            solution = solution or ['Die gemeldete Voraussetzung anhand der technischen Details prüfen und beheben; danach Resume verwenden.']
    if raw.get('requires_user') and status in ('usage limited', 'limited by budget'):
        solution += items(raw.get('solution'), 240) or ['Die zusätzlich erforderliche Nutzerentscheidung klären; der Reset hebt diese Sperre nicht auf.']
    if any(isinstance(raw.get(key), list) and len(raw[key]) > 6 for key in ('reasons', 'solution')):
        details = details + '\n\nVollständige strukturierte Meldung:\n' + json.dumps(raw, ensure_ascii=False)
    return {'reasons': reasons, 'explanation': explanation, 'solution': solution,
            'details': details, 'reset_at': reset, 'requires_user': bool(raw.get('requires_user'))}


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
