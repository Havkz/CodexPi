"""One real, small native E2E goal via the mapped TUI and dashboard Run now.

Never overwrites a goal, never fabricates usageLimited, never resumes unrelated
goals. Re-runs observe the original recorded project instead of creating more.
"""
import importlib.util
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
RECORD = ROOT / 'state/native-resume-e2e-20260923.json'
NAME = 'CodexPi Resume E2E 20260923'
OBJECTIVE = 'Create RESUME_TEST.txt containing native-resume-20260923. Verify its content, commit and push. Then mark this goal complete. Work only in this dedicated E2E project; do not spawn agents or install anything.'


def main():
    global RECORD, NAME, OBJECTIVE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery-fixture', action='store_true')
    args = parser.parse_args()
    if args.recovery_fixture:
        RECORD = ROOT / 'state/active-recovery-e2e-20260928.json'
        NAME = 'CodexPi Active Recovery E2E 20260928'
        OBJECTIVE = ('First run python3 -c "import time; time.sleep(45)" once, for a controller-recovery test. '
            'Then create RECOVERY_TEST.txt containing native-recovery-20260928, verify, commit and push, and complete. '
            'Only this test project; no agents or installs.')
    if RECORD.exists():
        project = json.loads(RECORD.read_text())
    else:
        project = helper.open_project(NAME)
        RECORD.write_text(json.dumps(project, indent=2))
    native = helper.remote('''import asyncio,json
from app.native import Native
async def main():
 n=await Native('state/native.sock').connect()
 try:
  goal=(await n.rpc('thread/goal/get',{'threadId': ''' + repr(project['codex_session_id']) + '''})).get('goal')
  if goal: assert goal['objective']==''' + repr(OBJECTIVE) + '''
  print(json.dumps({'goal_status':goal['status'] if goal else None}))
 finally:await n.close()
asyncio.run(main())
''')
    if native['goal_status'] == 'complete':
        if args.recovery_fixture:
            result = helper.remote('''import asyncio,json,subprocess
from pathlib import Path
from aiohttp import ClientSession
from app.common import read_env
from app.db import Database
async def verify():
 d=Database('state/codexpi.db')
 p=d.get(''' + repr(project['project_id']) + ''')
 assert p['goal_status']=='complete' and p['completion_notified'] and not p['operation']
 path=Path(p['project_path'])
 assert (path/'RECOVERY_TEST.txt').read_text().strip()=='native-recovery-20260928'
 def git(*args):return subprocess.check_output(['git',*args],cwd=path,text=True).strip()
 assert not git('status','--porcelain')
 assert git('rev-parse','HEAD')==p['last_commit']==git('ls-remote','origin','refs/heads/main').split()[0]
 repo=json.loads(subprocess.check_output(['gh','repo','view',p['github_repo'],'--json','visibility'],text=True))
 assert repo['visibility']=='PRIVATE'
 events=d.conn.execute("SELECT * FROM events WHERE project_id=? AND kind='complete'",(p['project_id'],)).fetchall()
 assert len(events)==1 and events[0]['sent_at']
 async with ClientSession(headers={'Authorization':'Bot '+read_env('.env')['DISCORD_BOT_TOKEN']}) as client:
  async with client.get('https://discord.com/api/v10/channels/'+p['discord_channel_id']+'/messages',params={'limit':'100'}) as response:
   assert response.status==200,response.status
   messages=await response.json()
 assert len(messages)<100, 'Pagination required before claiming message uniqueness'
 marker='CodexPi \\u2022 Event '+str(events[0]['event_id'])
 matched=[m for m in messages if any(e.get('footer',{}).get('text')==marker for e in m.get('embeds',[]))]
 assert len(matched)==1
 message=matched[0]
 assert p['last_commit'] in json.dumps(message['embeds'])
 assert any(b.get('custom_id')=='codexpi:close' and b.get('label')=='Close' for row in message['components'] for b in row['components'])
 print(json.dumps({'complete':True,'commit':p['last_commit'],'private_repo':p['github_repo'],
   'discord_message_id':message['id'],'complete_messages':len(matched),'close_button_present':True,
   'close_button_clicked':False,'clean_tree_and_file_verified':True}))
 d.conn.close()
asyncio.run(verify())
''')
            project['completion_evidence'] = result
            RECORD.write_text(json.dumps(project, indent=2))
            print(json.dumps(result))
        else:
            print(json.dumps(native))
        return
    if native['goal_status'] is None:
        assert not project.get('goal_submitted'), 'Goal submission already attempted; inspect the original TUI without resending'
        project['goal_submitted'] = time.time()
        RECORD.write_text(json.dumps(project, indent=2))
        helper.remote('''import json,subprocess,time
target=''' + repr(project['tmux_session_name'] + ':0.0') + '''
for _ in range(30):
 pane=subprocess.check_output(['tmux','capture-pane','-p','-t',target],text=True)
 if 'gpt-6-' in pane: break
 time.sleep(.5)
else: raise RuntimeError('Mapped TUI did not finish startup')
subprocess.run(['tmux','send-keys','-t',target,'-l','/goal '],check=True)
time.sleep(.4)
subprocess.run(['tmux','send-keys','-t',target,'-l', ''' + repr(OBJECTIVE) + '''],check=True)
time.sleep(1)
subprocess.run(['tmux','send-keys','-t',target,'Enter'],check=True)
print(json.dumps({'goal_submitted_through_tui':True}))
''')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.goto(helper.BASE)
        password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
        page.get_by_label('Passwort').fill(password)
        password = None
        page.get_by_role('button', name='Anmelden').click()
        page.locator('.infra-card').first.wait_for()
        state = page.request.get(helper.BASE + '/api/state').json()
        current = next(p for p in state['projects'] if p['project_id'] == project['project_id'])
        if current['goal_status'] == 'paused' and not current['operation']:
            assert not any(p['goal_status'] == 'active' for p in state['projects'])
            card = page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=NAME, exact=True))
            card.get_by_role('button', name='Run now', exact=True).click()
        deadline = time.monotonic() + 85
        while time.monotonic() < deadline:
            state = page.request.get(helper.BASE + '/api/state').json()
            assert sum(p['goal_status'] == 'active' for p in state['projects']) <= 1
            current = next(p for p in state['projects'] if p['project_id'] == project['project_id'])
            result = json.loads(current['resume_result'] or '{}')
            if result.get('status') in ('active', 'complete', 'usage limited', 'failed', 'verifying'):
                break
            time.sleep(1)
        else:
            raise AssertionError('No authoritative native resume outcome within deadline')
        print(json.dumps({'project_id': project['project_id'], 'session_id': project['codex_session_id'],
            'goal_status': current['goal_status'], 'resume_result': result, 'usage_limit': current['usage_limit']}))
        assert result['status'] != 'failed', result
        if result['status'] == 'active':
            expect(page.locator('#active').get_by_role('heading', name=NAME, exact=True)).to_be_visible()
            expect(page.locator('#active .status-active')).to_be_visible()
        browser.close()


if __name__ == '__main__':
    main()
