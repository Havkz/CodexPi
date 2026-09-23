"""Live verification of the user's empty mapped session; no invented goal.

Isolated Edge profile. Resume restores the existing TUI, not a model turn.
Also exercises delayed confirmation and duplicate-click prevention with explicit
browser fixtures, without sending fixture mutations to the real controller.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://192.168.2.105:8787'
IDENT = '26af23ec-e146-4713-b1a5-aba7bb93948b'


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE)
        password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
        page.get_by_label('Passwort').fill(password)
        password = None
        page.get_by_role('button', name='Anmelden').click()
        page.locator('.infra-card').first.wait_for()
        initial = page.request.get(BASE + '/api/state').json()
        project = next(p for p in initial['projects'] if p['project_id'] == IDENT)
        assert project['display_name'] == 'UserTestProject' and project['goal_status'] == 'paused'
        assert not any(p['goal_status'] == 'active' for p in initial['projects'])
        page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name='UserTestProject', exact=True)).get_by_role('button', name='Details').click()
        page.locator('#detail-overview').wait_for()
        dialog = page.locator('#project-dialog')
        assert dialog.get_by_role('button', name='Details', exact=True).count() == 0
        assert dialog.get_by_role('button', name='Run now', exact=True).count() == 0
        expect(dialog.get_by_role('button', name='Delete', exact=True)).to_be_enabled()
        dialog.get_by_role('button', name='Resume', exact=True).click()
        expect(dialog.get_by_role('button', name='Resume …', exact=True)).to_have_attribute('aria-busy', 'true')
        expect(dialog.get_by_role('button', name='Resume', exact=True)).to_be_enabled(timeout=85000)
        expect(dialog.get_by_text('Session restored. No native goal exists; enter /goal in this project TUI.', exact=True)).to_be_visible(timeout=85000)
        final = page.request.get(BASE + '/api/state').json()
        project = next(p for p in final['projects'] if p['project_id'] == IDENT)
        result = json.loads(project['resume_result'])
        assert result['id'] != json.loads(next(p for p in initial['projects'] if p['project_id'] == IDENT)['resume_result'] or '{}').get('id')
        assert result['status'] == 'restored' and not project['operation']
        assert project['goal_status'] == 'paused' and final['selected'] == IDENT
        assert not final['infrastructure'][0].get('error')
        for width in (1440, 375, 430):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth')
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.screenshot(path=str(ROOT / 'state/design-checks/resume-confirmed.png'))
        print(json.dumps({'live_empty_session_resume': result, 'nested_details': False,
                          'delete_enabled': True, 'run_now_on_head': False, 'errors': errors}))
        assert not errors
        # Delayed native acknowledgement fixture: HTTP 200 is not completion.
        fixture = final
        project['resume_result'] = None
        calls = []
        def action(route):
            calls.append(route.request.post_data_json)
            route.fulfill(json={'ok': True, 'operation_id': 'test-confirmation'})
        page.route('**/api/action', action)
        page.route('**/api/state', lambda route: route.fulfill(json=fixture))
        dialog.get_by_role('button', name='Resume', exact=True).click()
        expect(dialog.get_by_role('button', name='Resume …', exact=True)).to_be_disabled()
        page.wait_for_timeout(2500)
        expect(dialog.get_by_role('button', name='Resume …', exact=True)).to_have_attribute('aria-busy', 'true')
        assert len(calls) == 1
        project['resume_result'] = json.dumps({'id': 'test-confirmation', 'status': 'failed', 'message': 'Fixture: native acknowledgement timed out'})
        expect(dialog.get_by_text('Fixture: native acknowledgement timed out', exact=True)).to_be_visible(timeout=10000)
        expect(dialog.get_by_role('button', name='Resume', exact=True)).to_be_enabled()
        assert len(calls) == 1
        print('DELAYED_ACK_AND_ERROR_FIXTURE_OK')
        browser.close()


if __name__ == '__main__':
    main()
