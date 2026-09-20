"""Read-only live LAN checks; obtains password in memory from the user specification."""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

base = 'http://192.168.2.105:8787'
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(path, data=None, headers=None):
    try:
        response = client.open(urllib.request.Request(base + path, data=data, headers=headers or {}), timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    return response.status, response.headers, response.read()


assert request('/api/state')[0] == 401
status, headers, _ = request('/')
assert status == 200 and 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
assert request('/login', b'password=definitely-wrong-test-value')[0] == 401
assert request('/')[0] == 200
password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
assert request('/login', urllib.parse.urlencode({'password': password}).encode())[0] == 200
password = None
status, headers, body = request('/api/state')
assert status == 200 and headers['Cache-Control'] == 'no-store'
state = json.loads(body)
assert 'password_hash' not in body.decode() and 'worker_secret' not in body.decode()
assert request('/api/action', b'{"action":"logout"}', {'Content-Type': 'application/json'})[0] == 403
assert request('/api/action', b'{"action":"logout"}', {'Content-Type': 'application/json',
    'X-CSRF-Token': state['csrf'], 'Origin': 'http://evil.example'})[0] == 403
assert request('/', headers={'Host': 'evil.example'})[0] == 403
assert request('/api/action', b'{"action":"logout"}', {'Content-Type': 'application/json',
    'X-CSRF-Token': state['csrf']})[0] == 200
assert request('/api/state')[0] == 401
print(json.dumps({'live_dashboard': 'passed', 'checks': ['authentication', 'wrong-password',
    'HttpOnly-SameSite', 'no-secret-state', 'csrf', 'origin', 'host', 'logout'],
    'projects': len(state['projects']), 'discord_online': state['discord_online'],
    'windows_online': state['windows_online']}))
