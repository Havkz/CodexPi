"""One real, small native E2E goal via the mapped TUI and dashboard Run now.

Never overwrites a goal, never fabricates usageLimited, never resumes unrelated
goals. Re-runs observe the original recorded project instead of creating more.
"""
import importlib.util
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
    if native['goal_status'] is None:
        helper.remote('''import json,subprocess,time
target=''' + repr(project['tmux_session_name'] + ':0.0') + '''
subprocess.run(['tmux','send-keys','-t',target,'-l', ''' + repr('/goal ' + OBJECTIVE) + '''],check=True)
time.sleep(.3)
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
