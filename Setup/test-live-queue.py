"""Exercise the two explicitly named E2E projects through the authenticated dashboard."""
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

base = 'http://192.168.2.105:8787'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
client.open(base + '/', timeout=15).read()
password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
client.open(base + '/login', urllib.parse.urlencode({'password': password}).encode(), timeout=15).read()
password = None


def state():
    return json.load(client.open(base + '/api/state', timeout=15))


before = state()
first = next(p for p in before['projects'] if p['display_name'] == 'CodexPi E2E 20260920')
second = next(p for p in before['projects'] if p['display_name'] == 'CodexPi Queue E2E 20260920')
assert first['goal_status'] == 'active', first['goal_status']
assert second['goal_status'] == 'paused', second['goal_status']
request = urllib.request.Request(base + '/api/action', method='POST',
    data=json.dumps({'action': 'run-now', 'project_id': second['project_id']}).encode(),
    headers={'Content-Type': 'application/json', 'X-CSRF-Token': before['csrf']})
assert json.load(client.open(request, timeout=45))['ok']
for _ in range(80):
    current = state()
    assert sum(p['goal_status'] == 'active' for p in current['projects']) <= 1
    rows = {p['project_id']: p for p in current['projects']}
    if rows[second['project_id']]['goal_status'] == 'active':
        assert rows[first['project_id']]['goal_status'] == 'paused'
        assert rows[second['project_id']]['queue_position'] == 1
        print(json.dumps({'live_run_now': 'passed', 'previous': 'paused', 'selected': 'active',
                          'selected_queue_position': 1}))
        break
    time.sleep(.5)
else:
    raise RuntimeError('Run now did not receive a native active acknowledgement')
