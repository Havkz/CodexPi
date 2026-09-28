"""Live idle recovery; explicit --crash or --worker-restart injects a fault.

Never kills the native bridge, Unsnooze or unrelated services.
Refuses active goals, pending lifecycle work and unfinished Windows jobs.
"""
import argparse
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
BASE = 'http://192.168.2.105:8787'
SNAPSHOT = '''import asyncio,json,subprocess
from pathlib import Path
from app.db import Database
from app.native import GoalSource,Native
def service(name):
 text=subprocess.check_output(['systemctl','--user','show',name,'--property=MainPID,NRestarts,ActiveState,InvocationID'],text=True)
 return dict(line.split('=',1) for line in text.splitlines())
async def snapshot():
 db=Database('state/codexpi.db')
 assert db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 projects=db.all()
 assert not any(p['operation'] or p['goal_status']=='active' for p in projects), 'Project operation or active goal; abort'
 assert not db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('pending','sent','running')").fetchone(), 'Unfinished Windows job; abort'
 native_rows=GoalSource(Path.cwd()).rows()
 assert not any(r['status']=='active' for r in native_rows.values()), 'Native active goal; abort'
 native=await Native('state/native.sock').connect()
 try:
  for p in projects:
   thread=(await native.rpc('thread/read',{'threadId':p['codex_session_id']}))['thread']
   assert thread['status']['type'] in ('idle','notLoaded'), 'Native turn is executing; abort'
 finally: await native.close()
 fields=('project_id','display_name','project_path','codex_session_id','tmux_session_name','github_repo','discord_channel_id','queue_position','goal_status','block_reason','lifecycle')
 result={'projects':[{k:p[k] for k in fields} for p in projects], 'selected':db.setting('selected'),
   'manual_holds':{p['project_id']:db.setting('manual_pause/'+p['project_id'],False) for p in projects},
   'native_statuses':{k:r['status'] for k,r in native_rows.items()},
   'usage_samples':[list(r) for r in db.conn.execute('SELECT * FROM usage_samples ORDER BY observed_at DESC LIMIT 4')],
   'services':{n:service(n) for n in ('codexpi','codexpi-native','codexpi-unsnooze')}}
 assert all(s['ActiveState']=='active' and int(s['MainPID'])>0 for s in result['services'].values())
 db.conn.close()
 return result
'''


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--crash', action='store_true')
    action.add_argument('--worker-restart', action='store_true')
    args = parser.parse_args()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client.open(BASE, timeout=10).close()
    password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
    client.open(BASE + '/login', urllib.parse.urlencode({'password': password}).encode(), timeout=10).close()
    password = None
    def state():
        with client.open(BASE + '/api/state', timeout=5) as response:
            return json.load(response)
    before_web = state()
    assert before_web['windows_online'] and before_web['discord_online'], 'Need connected baseline to verify reconnect'
    before = helper.remote(SNAPSHOT + '\nprint(json.dumps(asyncio.run(snapshot())))\n')
    if args.worker_restart:
        # Reuse the same idle/native/queue preflight; never interrupt a Windows job.
        ledger = sqlite3.connect((ROOT / 'windows-worker/state/jobs.db').as_uri() + '?mode=ro', uri=True)
        try:
            assert not ledger.execute("SELECT 1 FROM jobs WHERE status!='delivered'").fetchone(), 'Unacknowledged Windows job; abort'
        finally:
            ledger.close()
        def task(command):
            subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                "$ErrorActionPreference='Stop'; " + command], check=True, capture_output=True, text=True, timeout=25)
        task("if ((Get-ScheduledTask -TaskName 'CodexPi Windows Worker').State -ne 'Running') { throw 'Worker not running' }")
        started = time.monotonic()
        try:
            task("Stop-ScheduledTask -TaskName 'CodexPi Windows Worker'; "
                 "$deadline=(Get-Date).AddSeconds(15); "
                 "while ((Get-ScheduledTask -TaskName 'CodexPi Windows Worker').State -eq 'Running') { "
                 "if ((Get-Date) -gt $deadline) { throw 'Worker did not stop' }; Start-Sleep -Milliseconds 250 }")
            while state()['windows_online']:
                if time.monotonic() - started > 55:
                    raise RuntimeError('Worker disconnect not observed within deadline')
                time.sleep(1)
            offline_seconds = time.monotonic() - started
            assert offline_seconds <= 60
            print('Worker offline confirmed; restarting its existing scheduled task', flush=True)
        finally:
            task("Start-ScheduledTask -TaskName 'CodexPi Windows Worker'")
        restarted = time.monotonic()
        while not state()['windows_online']:
            if time.monotonic() - restarted > 60:
                raise RuntimeError('Worker signed heartbeat did not reconnect')
            time.sleep(1)
        after = helper.remote(SNAPSHOT + '\nprint(json.dumps(asyncio.run(snapshot())))\n')
        for field in ('projects', 'selected', 'manual_holds', 'native_statuses', 'services'):
            assert after[field] == before[field], field
        result = {'passed': True, 'offline_seconds': offline_seconds,
            'reconnect_seconds': time.monotonic() - restarted, 'pi_and_projects_unchanged': True,
            'logon_autostart_tested': False, 'silent_open_socket_expiry_tested': False}
        record = ROOT / 'state' / ('worker-recovery-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
        record.write_text(json.dumps(result, indent=2))
        print(json.dumps({'record': str(record), **result}))
        return
    if not args.crash:
        print(json.dumps({'preflight': 'passed', 'projects': len(before['projects']), 'crash_injected': False}))
        return
    record = ROOT / 'state' / ('controller-recovery-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    record.write_text(json.dumps({'before': before, 'completed': False}, indent=2))
    # Recheck immediately on the Pi before targeting the exact systemd main process.
    killed = helper.remote(SNAPSHOT + '''
before=asyncio.run(snapshot())
subprocess.run(['systemctl','--user','kill','--kill-whom=main','--signal=SIGKILL','codexpi.service'],check=True)
print(json.dumps(before['services']['codexpi']))
''')
    assert killed['MainPID'] == before['services']['codexpi']['MainPID'], 'Controller changed before injection; inspect record'
    print('Injected SIGKILL into idle controller; waiting for systemd and signed worker reconnect', flush=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            web = state()
            if web['windows_online'] and web['discord_online'] and web['unsnooze'].get('daemonRunning'):
                break
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError('Controller/integrations not confirmed within 90s; no repeated crash')
    after = helper.remote(SNAPSHOT + '\nprint(json.dumps(asyncio.run(snapshot())))\n')
    for field in ('projects', 'selected', 'manual_holds', 'native_statuses'):
        assert after[field] == before[field], field
    old, new = before['services']['codexpi'], after['services']['codexpi']
    assert new['MainPID'] != old['MainPID'] and new['InvocationID'] != old['InvocationID']
    assert int(new['NRestarts']) > int(old['NRestarts'])
    for service in ('codexpi-native', 'codexpi-unsnooze'):
        assert before['services'][service] == after['services'][service], service
    rows = helper.remote("from app.db import Database\nimport json\nd=Database('state/codexpi.db')\nprint(json.dumps([list(r) for r in d.conn.execute('SELECT * FROM usage_samples')]))\nd.conn.close()")
    assert all(row in rows for row in before['usage_samples'])
    assert web['csrf'] == before_web['csrf'], 'Existing authenticated dashboard session was not preserved'
    result = {'before': before, 'after': after, 'completed': True, 'crash_injected': True,
        'windows_reconnected': True, 'discord_reconnected': True, 'dashboard_session_preserved': True,
        'usage_history_preserved': True, 'automatic_active_goal_resume_tested': False}
    record.write_text(json.dumps(result, indent=2))
    print(json.dumps({'record': str(record), 'passed': True, 'old_pid': old['MainPID'], 'new_pid': new['MainPID']}))


if __name__ == '__main__':
    main()
