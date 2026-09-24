"""Live manual pause/restart/queued-resume test on one dedicated native goal.

Never runs the goal or changes the user's selected blocked project. Deletes only
the dedicated fixture through the normal lifecycle, retaining repo and backup.
"""
import importlib.util
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
RECORD = ROOT / 'state/pause-policy-e2e-20260924.json'
NAME = 'CodexPi Pause Policy E2E 20260924'
OBJECTIVE = 'Keep this verification goal paused. Do not execute any task until explicitly resumed.'


def native(project):
    return helper.remote('''import asyncio,json
from app.native import Native
from app.db import Database
async def main():
 n=await Native('state/native.sock').connect()
 db=Database('state/codexpi.db')
 try:
  p=db.get(''' + repr(project['project_id']) + ''')
  goal=(await n.rpc('thread/goal/get',{'threadId':p['codex_session_id']})).get('goal')
  if goal:
   assert goal['objective']==''' + repr(OBJECTIVE) + '''
   assert goal['status']=='paused' and goal['tokensUsed']==0
  print(json.dumps({'goal':goal,'manual_paused':db.setting('manual_pause/'+p['project_id'],False),
    'operation':p['operation'],'selected':db.setting('selected')}))
 finally:await n.close();db.conn.close()
asyncio.run(main())
''')


def main():
    if RECORD.exists():
        project = json.loads(RECORD.read_text())
        if project.get('verified'):
            helper.RECORD = RECORD
            helper.verify_deleted(project, project['renamed'])
            return
    else:
        project = helper.open_project(NAME)
        RECORD.write_text(json.dumps(project, indent=2))
    snapshot = native(project)
    assert snapshot['selected'] and snapshot['selected'] != project['project_id'], 'A different nonexecuting project must retain the slot'
    if not snapshot['goal']:
        assert not project.get('submitted'), 'Inspect the recorded native composer; never resend blindly'
        project['submitted'] = True
        RECORD.write_text(json.dumps(project, indent=2))
        helper.remote('''import asyncio,json,subprocess,time
from app.native import Native
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
async def check():
 n=await Native('state/native.sock').connect()
 try:
  for _ in range(20):
   g=(await n.rpc('thread/goal/get',{'threadId':''' + repr(project['codex_session_id']) + '''})).get('goal')
   if g:
    assert g['status']=='paused' and g['tokensUsed']==0
    print(json.dumps({'native_goal_created_without_execution':True}))
    return
   await asyncio.sleep(.5)
  raise RuntimeError('No native goal acknowledgement; inspect without repeating input')
 finally:await n.close()
asyncio.run(check())
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
        card = page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=NAME, exact=True))
        if not native(project)['manual_paused']:
            card.get_by_role('button', name='Pause', exact=True).click()
        expect(card.get_by_role('button', name='Pause', exact=True)).to_be_disabled()
        assert native(project)['manual_paused']
        helper.remote('''import json,subprocess,time,urllib.request
from pathlib import Path
from app.native import GoalSource
assert all(r['status']!='active' for r in GoalSource(Path.cwd()).rows().values())
subprocess.run(['systemctl','--user','restart','codexpi'],check=True,timeout=30)
for _ in range(30):
 try: urllib.request.urlopen('http://192.168.2.105:8787',timeout=2).close(); break
 except OSError: time.sleep(.5)
else: raise RuntimeError('Dashboard not ready')
print(json.dumps({'restarted':True}))
''')
        page.reload()
        expect(card.get_by_role('button', name='Pause', exact=True)).to_be_disabled()
        assert native(project)['manual_paused']
        card.get_by_role('button', name='Resume', exact=True).click()
        expect(card.get_by_role('button', name='Pause', exact=True)).to_be_enabled()
        state = native(project)
        assert state['selected'] == snapshot['selected'] and not state['manual_paused']
        assert json.loads(state['operation'])['kind'] == 'resume'
        card.get_by_role('button', name='Pause', exact=True).click()
        expect(card.get_by_role('button', name='Pause', exact=True)).to_be_disabled()
        state = native(project)
        assert state['manual_paused'] and state['operation'] is None
        card.get_by_role('button', name='Details', exact=True).click()
        page.locator('#project-dialog').get_by_role('button', name='Delete', exact=True).click()
        page.locator('#lifecycle-input').fill(NAME)
        page.get_by_role('button', name='Löschen bestätigen', exact=True).click()
        page.locator('#lifecycle-dialog').wait_for(state='hidden', timeout=90000)
        browser.close()
    helper.RECORD = RECORD
    helper.verify_deleted(project, dict(project))
    print('MANUAL_PAUSE_RESTART_QUEUED_RESUME_CANCEL_LIVE_PASSED')


if __name__ == '__main__':
    main()
