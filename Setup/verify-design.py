"""Live, non-destructive browser checks; isolated headless Edge, no saved credentials.

Uses the already-installed Windows Playwright package, not a production dependency.
Screenshots are local test artifacts under ignored state/design-checks.
"""
import json
from pathlib import Path
import copy

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://192.168.2.105:8787'
OUTPUT = ROOT / 'state/design-checks'


def no_overflow(page, label):
    sizes = page.evaluate('''() => ({width: innerWidth, content: document.documentElement.scrollWidth,
        dialog: (() => {const el = document.querySelector('dialog[open]');
            return el ? {width: el.clientWidth, content: el.scrollWidth} : null;})()})''')
    assert sizes['content'] <= sizes['width'], (label, sizes)
    assert not sizes['dialog'] or sizes['dialog']['content'] <= sizes['dialog']['width'], (label, sizes)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
    report = {'type': 'live-read-only-browser', 'screens': [], 'errors': []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.goto(BASE)
        assert page.locator('input').count() == 1
        assert page.get_by_label('Passwort').get_attribute('type') == 'password'
        for width, height in [(1920, 1080), (1440, 1000), (375, 812), (430, 932)]:
            page.set_viewport_size({'width': width, 'height': height})
            no_overflow(page, 'login-' + str(width))
            page.screenshot(path=str(OUTPUT / f'login-{width}.png'), full_page=True)
        page.get_by_label('Passwort').fill(password)
        password = None
        page.get_by_role('button', name='Anmelden').click()
        try:
            page.locator('.infra-card').first.wait_for()
        except Exception:
            page.screenshot(path=str(OUTPUT / 'failure.png'), full_page=True)
            print(json.dumps({'url': page.url, 'title': page.title(), 'errors': report['errors'],
                              'notice': page.locator('#notice').text_content() if page.locator('#notice').count() else None}))
            raise
        assert page.locator('.infra-card').count() == 6
        assert page.locator('.kpi').count() == 4
        for width, height in [(1920, 1080), (1440, 1000), (375, 812), (430, 932)]:
            page.set_viewport_size({'width': width, 'height': height})
            no_overflow(page, 'dashboard-' + str(width))
            assert page.locator('#logout').is_visible()
            assert page.locator('#pause-all').is_visible()
            if width < 520:
                scroll = page.locator('.table-scroll')
                scroll.evaluate('(el) => { el.scrollLeft = el.scrollWidth; }')
                if page.locator('#queue tr').count():
                    control = page.locator('#queue tr').first.get_by_role('button', name='Details')
                    bounds = control.bounding_box()
                    assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= width
                scroll.evaluate('(el) => { el.scrollLeft = 0; }')
            page.screenshot(path=str(OUTPUT / f'dashboard-{width}.png'), full_page=True)
            report['screens'].append({'width': width, 'height': height, 'overflow': False})
            if page.locator('#projects .project-card').count():
                page.locator('#projects .project-card').first.get_by_role('button', name='Details').click()
                page.locator('#detail-body .detail-grid').wait_for()
                no_overflow(page, 'detail-' + str(width))
                assert page.get_by_role('heading', name='Lifecycle Events', exact=True).is_visible()
                page.screenshot(path=str(OUTPUT / f'detail-{width}.png'))
                page.get_by_role('button', name='Projekt-Details schließen').click()
                assert not page.locator('#project-dialog').is_visible()
        # All supplied text is inserted as text nodes, never HTML markup.
        assert not page.locator('#main script').count()
        # Explicitly synthetic UI interaction checks: intercept every mutation, never change live projects.
        live = page.request.get(BASE + '/api/state').json()
        fixture = copy.deepcopy(live)
        statuses = ['active', 'paused', 'stalled', 'usage limited', 'limited by budget', 'complete']
        template = live['projects'][0]
        fixture['projects'] = [dict(template, project_id='fixture-' + str(i),
            display_name='Design fixture ' + str(i), queue_position=i + 1, goal_status=status,
            block_reason=None, last_activity=live['server_time']) for i, status in enumerate(statuses)]
        fixture['projects'][0]['display_name'] = '<img src=x onerror=alert(1)>'
        fixture['selected'] = 'fixture-0'
        fixture['pause_all'] = False
        for project in fixture['projects']:
            project.update(operation=None, resume_result=None)
        actions = []
        def fake_action(route):
            body = route.request.post_data_json
            assert route.request.headers['x-csrf-token'] == fixture['csrf']
            actions.append(body['action'])
            if body['action'] == 'reorder':
                assert set(body['ids']) == {p['project_id'] for p in fixture['projects']}
                fixture['projects'].sort(key=lambda p: body['ids'].index(p['project_id']))
                for index, project in enumerate(fixture['projects'], 1):
                    project['queue_position'] = index
            elif body['action'] in ('run-now', 'resume'):
                if body['action'] == 'run-now':
                    fixture['projects'].sort(key=lambda p: p['project_id'] != body['project_id'])
                    for index, project in enumerate(fixture['projects'], 1):
                        project['queue_position'] = index
                fixture['selected'] = body['project_id']
                for project in fixture['projects']:
                    if project['goal_status'] == 'active':
                        project['goal_status'] = 'paused'
                    if project['project_id'] == body['project_id']:
                        project['goal_status'] = 'active'
            elif body['action'] == 'pause-all':
                fixture['pause_all'] = True
                fixture['selected'] = None
                for project in fixture['projects']:
                    if project['goal_status'] == 'active':
                        project['goal_status'] = 'paused'
            elif body['action'] == 'pause':
                fixture['selected'] = None
                next(p for p in fixture['projects'] if p['project_id'] == body['project_id'])['goal_status'] = 'paused'
            else:
                raise AssertionError('Unexpected mutation: ' + body['action'])
            route.fulfill(json={'ok': True})
        page.route('**/api/action', fake_action)
        page.route('**/api/state', lambda route: route.fulfill(json=fixture))
        page.reload()
        page.get_by_role('heading', name='<img src=x onerror=alert(1)>', exact=True).first.wait_for()
        assert page.locator('#active img').count() == 0
        for status in statuses:
            assert page.locator('#queue .status-' + status.replace(' ', '-')).count() == 1
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('#queue tr').nth(1).drag_to(page.locator('#queue tr').first)
        page.wait_for_function("() => document.querySelector('#queue tr').dataset.id === 'fixture-1'")
        page.get_by_role('button', name='Design fixture 1 nach unten', exact=True).click()
        page.wait_for_function("() => document.querySelector('#queue tr').dataset.id === 'fixture-0'")
        # Polling must not steal focus or collapse the dialog.
        page.get_by_role('button', name='Design fixture 1 nach oben', exact=True).focus()
        with page.expect_response('**/api/state', timeout=8000):
            pass  # Wait for the live five-second poll; do not manually invoke refresh.
        page.wait_for_function("() => document.activeElement.dataset.key === 'fixture-1:move-1'")
        page.locator('#queue tr[data-id="fixture-1"]').get_by_role('button', name='Run now').click()
        page.locator('#active').get_by_role('heading', name='Design fixture 1', exact=True).wait_for()
        page.locator('#active').get_by_role('button', name='Pause', exact=True).click()
        page.get_by_text('Kein Projekt ausgewählt.', exact=False).wait_for()
        page.locator('#queue tr[data-id="fixture-0"]').get_by_role('button', name='Run now').click()
        page.locator('#active').get_by_role('button', name='Pause', exact=True).click()
        page.locator('#queue tr[data-id="fixture-0"]').get_by_role('button', name='Resume', exact=True).click()
        page.get_by_role('button', name='Pause all', exact=True).click()
        page.get_by_text('Alle Arbeit pausiert. Mit', exact=False).wait_for()
        assert actions == ['reorder', 'reorder', 'run-now', 'pause', 'run-now', 'pause', 'resume', 'pause-all'], actions
        report['synthetic_interactions'] = actions
        page.unroute('**/api/action')
        page.unroute('**/api/state')
        page.reload()
        page.locator('.infra-card').first.wait_for()
        assert not report['errors'], report['errors']
        page.get_by_role('button', name='Abmelden').click()
        page.get_by_label('Passwort').wait_for()
        browser.close()
    (OUTPUT / 'live-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
