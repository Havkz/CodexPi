"""Delete only a dedicated empty E2E project with a real queued resume intent."""
import importlib.util
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)
lifecycle.RECORD = ROOT / 'state/paused-delete-e2e-20260923.json'
NAME = 'CodexPi Paused Delete E2E 20260923'


def main():
    if lifecycle.RECORD.exists():
        project = json.loads(lifecycle.RECORD.read_text())
        if project.get('verified'):
            lifecycle.verify_deleted(project, project['renamed'])
            return
        absent = lifecycle.remote('''import json
from app.db import Database
db=Database('state/codexpi.db')
print(json.dumps({'absent': db.conn.execute('SELECT 1 FROM projects WHERE project_id=?',(''' + repr(project['project_id']) + ''',)).fetchone() is None}))
db.conn.close()
''')['absent']
        if absent:
            lifecycle.verify_deleted(project, dict(project))
            return
    else:
        project = lifecycle.open_project(NAME)
        lifecycle.RECORD.write_text(json.dumps(project, indent=2))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.goto(lifecycle.BASE)
        password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
        page.get_by_label('Passwort').fill(password)
        password = None
        page.get_by_role('button', name='Anmelden').click()
        page.locator('.infra-card').first.wait_for()
        state = page.request.get(lifecycle.BASE + '/api/state').json()
        assert state['selected'] and state['selected'] != project['project_id']
        assert not any(p['goal_status'] == 'active' for p in state['projects'])
        card = page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=NAME, exact=True))
        card.get_by_role('button', name='Resume', exact=True).click()
        expect(page.locator('#notice')).to_have_text('Queued; the current project keeps its execution slot', timeout=15000)
        state = page.request.get(lifecycle.BASE + '/api/state').json()
        current = next(p for p in state['projects'] if p['project_id'] == project['project_id'])
        assert current['goal_status'] == 'paused'
        assert json.loads(current['operation'])['kind'] == 'resume'
        card.get_by_role('button', name='Details').click()
        delete = page.locator('#project-dialog').get_by_role('button', name='Delete', exact=True)
        expect(delete).to_be_enabled()
        delete.click()
        page.locator('#lifecycle-input').fill(NAME)
        page.locator('#lifecycle-submit').click()
        expect(page.locator('#lifecycle-dialog')).not_to_be_visible(timeout=90000)
        final = page.request.get(lifecycle.BASE + '/api/state').json()
        assert all(p['project_id'] != project['project_id'] for p in final['projects'])
        assert final['selected'] == state['selected']
        browser.close()
    lifecycle.verify_deleted(project, dict(project))


if __name__ == '__main__':
    main()
