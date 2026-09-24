"""Start/observe one real deployment goal; never replace an existing objective.

Default is observation only. --start authorizes initial fixture creation and a
single mapped-TUI /goal submission. Re-runs never send a duplicate objective.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
RECORD = ROOT / 'state/deployment-e2e-20260924.json'
NAME = 'CodexPi Deployment E2E 20260924'
OBJECTIVE = ('This dedicated integration-test project explicitly requires a 24/7 Pi user service. '
    'Create a tiny Python standard-library HTTP service in service.py, listening only on 127.0.0.1:18973, '
    'returning exactly codexpi-deployment-20260924 for GET /. Create healthcheck.py which requests that URL '
    'with a timeout and exits nonzero unless that exact response is received. Test both locally by starting '
    'and then stopping only your own test-server process. No dependencies or GitHub Actions workflow are '
    'needed for this dedicated lifecycle smoke fixture. Register the deployment while this goal is active '
    'using /home/raspberry/CodexPi/bin/codexpi-tool deploy-pi --goal-requires-24x7 '
    '--reason "Explicit 24/7 integration-test goal" --health-command "python3 healthcheck.py" -- python3 service.py . '
    'That command schedules deployment after completion; do not move directories or create systemd units yourself. '
    'Commit and push the verified code, then mark the goal complete. The controller will move the directory '
    'and verify the production health check before publishing completion. Do not spawn agents, install anything, '
    'touch other projects, or leave your temporary test server running.')
# The 0.155.1 TUI treated the long paste as a prompt. The worker then created this
# genuine native goal through create_goal; preserve its exact observed objective.
NATIVE_OBJECTIVE = ('Create and locally verify the standard-library HTTP service on 127.0.0.1:18973 returning exactly '
    'codexpi-deployment-20260924 for GET / and its timeout healthcheck; stop own test process; register explicit 24/7 '
    'Pi deployment with codexpi-tool; commit and push; mark complete for controller delivery. No dependencies, Actions '
    'workflows, agents or manual deployment.')


def observe(project):
    return helper.remote('''import asyncio,json,subprocess
from pathlib import Path
from app.db import Database
from app.native import Native
async def main():
 db=Database('state/codexpi.db')
 p=db.get(''' + repr(project['project_id']) + ''')
 plan=db.setting('deployment/'+p['project_id'])
 n=await Native('state/native.sock').connect()
 try:
  thread=(await n.rpc('thread/read',{'threadId':p['codex_session_id']}))['thread']
  goal=(await n.rpc('thread/goal/get',{'threadId':p['codex_session_id']})).get('goal')
  if goal: assert goal['objective'] in ''' + repr((OBJECTIVE, NATIVE_OBJECTIVE)) + '''
  result={'project':p,'deployment':plan,'native_status':goal['status'] if goal else None,'native_cwd':thread['cwd']}
  if p['goal_status']=='complete':
   expected=Path('/home/raspberry')/p['slug']
   assert Path(p['project_path'])==expected and thread['cwd']==str(expected)
   assert not (Path('/home/raspberry/CodexPi/projects')/p['slug']).exists()
   assert plan['status']=='active' and plan['verified_commit']==p['last_commit']
   unit='codexpi-project-'+p['project_id']+'.service'
   subprocess.run(['systemctl','--user','is-active','--quiet',unit],check=True)
   subprocess.run(plan['check'],cwd=expected,check=True,capture_output=True,timeout=30)
   remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/main'],cwd=expected,text=True).split()[0]
   assert remote==p['last_commit']
   assert not subprocess.check_output(['git','status','--porcelain'],cwd=expected,text=True).strip()
   result['live_deployment']='passed'
  print(json.dumps(result))
 finally:
  await n.close()
  db.conn.close()
asyncio.run(main())
''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--lifecycle', action='store_true', help='Verify restart, then rename/delete ONLY this completed fixture')
    args = parser.parse_args()
    if RECORD.exists():
        project = json.loads(RECORD.read_text())
    else:
        assert args.start, 'No fixture exists; use --start only for initial live verification'
        helper.remote('''import json,socket
from pathlib import Path
from app.native import GoalSource
assert all(r['status']!='active' for r in GoalSource(Path.cwd()).rows().values())
with socket.socket() as sock: sock.bind(('127.0.0.1',18973))
print(json.dumps({'idle_and_port_free':True}))
''')
        project = helper.open_project(NAME)
        RECORD.write_text(json.dumps(project, indent=2))
    if project.get('verified') and project.get('renamed'):
        helper.RECORD = RECORD
        helper.verify_deleted(project, project['renamed'])
        return
    current = observe(project)
    if args.lifecycle:
        assert current.get('live_deployment') == 'passed', 'Deployment must pass before lifecycle verification'
        restart = helper.remote('''import json,subprocess,time,urllib.request
from pathlib import Path
from app.native import GoalSource
assert all(r['status']!='active' for r in GoalSource(Path.cwd()).rows().values())
unit='codexpi-project-''' + project['project_id'] + '''.service'
before=subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID','--value'],text=True).strip()
assert int(before)>0
subprocess.run(['systemctl','--user','restart','codexpi'],check=True,timeout=30)
for _ in range(30):
 try:
  urllib.request.urlopen('http://192.168.2.105:8787',timeout=2).close()
  break
 except OSError: time.sleep(.5)
else: raise RuntimeError('Dashboard did not return after restart')
after=subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID','--value'],text=True).strip()
assert before==after
print(json.dumps({'controller_restart_preserved_service_pid':int(after)}))
''')
        assert observe(project).get('live_deployment') == 'passed'
        project.update(current['project'], deployment_verification=current['deployment'], restart_verification=restart)
        RECORD.write_text(json.dumps(project, indent=2))
        helper.RECORD, helper.NAME, helper.RENAMED = RECORD, NAME, 'CodexPi Deployment Renamed E2E 20260924'
        helper.main()
        removed = helper.remote('''import json,subprocess
from pathlib import Path
from app.db import Database
ident=''' + repr(project['project_id']) + '''
db=Database('state/codexpi.db')
assert db.setting('deployment/'+ident) is None
unit='codexpi-project-'+ident+'.service'
assert not (Path('/home/raspberry/.config/systemd/user')/unit).exists()
assert subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode!=0
print(json.dumps({'deployment_mapping_and_service_removed':True}))
db.conn.close()
''')
        print(json.dumps({**restart, **removed}))
        return
    if current['native_status'] is None and not project.get('goal_submitted'):
        assert args.start, 'Initial goal submission requires --start'
        project['goal_submitted'] = time.time()
        RECORD.write_text(json.dumps(project, indent=2))
        helper.remote('''import json,subprocess,time
target=''' + repr(project['tmux_session_name'] + ':0.0') + '''
subprocess.run(['tmux','send-keys','-t',target,'-l', ''' + repr('/goal ' + OBJECTIVE) + '''],check=True)
time.sleep(.3)
subprocess.run(['tmux','send-keys','-t',target,'Enter'],check=True)
print(json.dumps({'submitted_once':True}))
''')
    if args.start and current['project']['goal_status'] == 'paused' and not project.get('resume_requested'):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            page.goto(helper.BASE)
            password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
            page.get_by_label('Passwort').fill(password)
            password = None
            page.get_by_role('button', name='Anmelden').click()
            card = page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=NAME, exact=True))
            card.get_by_role('button', name='Run now', exact=True).click()
            project['resume_requested'] = time.time()
            RECORD.write_text(json.dumps(project, indent=2))
            browser.close()
    print(json.dumps(observe(project), indent=2))


if __name__ == '__main__':
    main()
