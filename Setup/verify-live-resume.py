"""Resume only the existing queue E2E goal; never create or replace an objective."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true', help='Resume the existing queue E2E goal once')
    args = parser.parse_args()
    base = 'http://192.168.2.105:8787'
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client.open(base + '/', timeout=15).read()
    password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
    client.open(base + '/login', urllib.parse.urlencode({'password': password}).encode(), timeout=15).read()
    password = None

    def state():
        return json.load(client.open(base + '/api/state', timeout=15))

    current = state()
    ident = 'bd081627-9ed2-44a5-82df-e10487d84dff'
    target = next(p for p in current['projects'] if p['project_id'] == ident)
    assert target['display_name'] == 'CodexPi Queue E2E 20260920'
    assert target['codex_session_id'] == '01a0bbef-d4d2-7a63-9ebb-40495fa41952'
    assert target['lifecycle'] == 'ready'
    if args.resume:
        assert target['goal_status'] in ('paused', 'stalled'), target['goal_status']
        assert not target['operation'], target['operation']
        request = urllib.request.Request(base + '/api/action', method='POST',
            data=json.dumps({'action': 'run-now', 'project_id': ident}).encode(),
            headers={'Content-Type': 'application/json', 'X-CSRF-Token': current['csrf']})
        assert json.load(client.open(request, timeout=45))['ok']
        for _ in range(60):
            current = state()
            assert sum(p['goal_status'] == 'active' for p in current['projects']) <= 1
            target = next(p for p in current['projects'] if p['project_id'] == ident)
            if target['goal_status'] in ('active', 'complete') and not target['operation']:
                print('LIVE_NATIVE_RESUME_ACKNOWLEDGED')
                break
            time.sleep(.5)
        else:
            raise RuntimeError('No native resume acknowledgement; inspect existing handle, do not blindly restart')
    fields = ('project_id', 'display_name', 'codex_session_id', 'goal_status', 'queue_position',
              'last_commit', 'last_ci_status', 'operation', 'block_reason')
    print(json.dumps([{k: p[k] for k in fields} for p in current['projects']], indent=2))


if __name__ == '__main__':
    main()
