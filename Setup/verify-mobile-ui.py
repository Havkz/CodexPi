"""Serve the real dashboard locally with isolated fixtures; inspect Chromium layouts."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import threading
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/web_assets'
OUTPUT = ROOT / 'state/mobile-ui'
WIDTHS = (320, 375, 390, 430)


def main():
    state, usage = runpy.run_path(str(ROOT / 'Setup/verify-usage-ui.py'))['fixture']()
    names = ('Raspberry Pi', 'Native Codex Bridge', 'Windows Worker', 'GitHub',
             'Discord', 'Unsnooze', 'GitHub Actions')
    state['infrastructure'] = [{'name': name, 'status': 'online', 'error': None,
        'detail': 'Isolated visual fixture', 'checked_at': usage['checked_at'],
        **({'heartbeat_age': 4} if name == 'Windows Worker' else {})} for name in names]
    state['accounts'][0]['name'] = 'active-account-with-a-long-email@example.com'
    state['projects'][0]['display_name'] = 'Project-with-a-long-mobile-dashboard-name'
    state['projects'][0]['github_repo'] = 'fixture/repository-with-a-long-mobile-name'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    errors, failures, results = [], [], []

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                if path == '/api/state':
                    value = state
                elif path == '/api/usage':
                    value = usage
                elif path.startswith('/api/projects/'):
                    project = next(p for p in state['projects'] if p['project_id'] == path.rsplit('/', 1)[-1])
                    value = {'project': project, 'commits': [], 'jobs': [], 'events': []}
                else:
                    self.send_error(404)
                    return
                payload = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.path = '/index.html' if path == '/' else path.removeprefix('/static')
                super().do_GET()

        def do_POST(self):
            self.send_error(405, 'Visual fixtures cannot mutate projects')

        def end_headers(self):
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'")
            super().end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ASSETS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    print('LOCAL_DASHBOARD', base, flush=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 320, 'height': 900}, is_mobile=True, has_touch=True)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            changes = []
            def confirm_status(route):
                body = route.request.post_data_json
                assert body['action'] == 'queue-status'
                project = next(p for p in state['projects'] if p['project_id'] == body['project_id'])
                assert body['expected_status'] == project['queue_status']
                project['queue_status'] = body['status']
                project['manual_paused'] = body['status'] == 'paused'
                changes.append(body)
                route.fulfill(json={'ok': True, 'queue_status': body['status']})
            page.route('**/api/action', confirm_status)
            for width in (*WIDTHS, 1440):
                queued = next(p for p in state['projects'] if p['project_id'] == 'new-work')
                queued.update(queue_status='queued', manual_paused=False)
                page.set_viewport_size({'width': width, 'height': 900})
                page.goto(base)
                expect(page.locator('body')).to_have_class('dashboard-ready')
                expect(page.locator('#usage-chart-value')).to_have_text('67%')
                page.wait_for_function("() => [...document.getAnimations()].every(a => a.playState === 'finished')")
                expect(page.locator('#infra img')).to_have_count(7)
                page.wait_for_function("() => [...document.querySelectorAll('#infra img')].every(i => i.complete && i.naturalWidth > 0)")

                def snapshot(name, full=True):
                    overflow = page.evaluate("""() => {
                        const w = document.documentElement.clientWidth;
                        return [...document.querySelectorAll('main *, header *, dialog[open], dialog[open] *')].filter(el => {
                            const box = el.getBoundingClientRect();
                            if (!box.width || el.closest('dialog:not([open])') || el.closest('.table-scroll') && !el.classList.contains('table-scroll')) return false;
                            return box.right > w + 1 || box.left < -1;
                        }).map(el => ({element: el.tagName, id: el.id, cls: el.className,
                            left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right}));
                    }""")
                    document_overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    queue_overflow = page.locator('.table-scroll').evaluate('(el) => el.scrollWidth > el.clientWidth')
                    result = {'width': width, 'view': name, 'document_overflow': document_overflow,
                              'queue_overflow': queue_overflow, 'overflow_elements': overflow}
                    results.append(result)
                    if overflow or document_overflow or queue_overflow:
                        failures.append(result)
                    page.screenshot(path=str(OUTPUT / f'{name}-{width}.png'), full_page=full)

                snapshot('dashboard')
                page.locator('#infra').screenshot(path=str(OUTPUT / f'infrastructure-{width}.png'))
                page.locator('.table-panel').screenshot(path=str(OUTPUT / f'queue-{width}.png'))
                toggle = page.locator('#queue tr[data-id="new-work"] .queue-status-button')
                before = len(changes)
                toggle.click()
                expect(toggle).to_contain_text('Sure?')
                assert len(changes) == before
                snapshot('queue-confirm')
                toggle.press('Escape')
                expect(toggle).to_have_text('queued')
                toggle.click()
                toggle.click()
                expect(toggle).to_have_text('paused')
                assert len(changes) == before + 1
                toggle.click()
                toggle.click()
                expect(toggle).to_have_text('queued')
                assert len(changes) == before + 2
                assert page.locator('#queue tr[data-id="running"] .queue-status-button').count() == 0
                if width == 320:
                    toggle.click()
                    queued.update(goal_status='active', queue_status=None)
                    page.evaluate('refresh()')
                    expect(toggle).to_have_count(0)
                    assert len(changes) == before + 2
                    queued.update(goal_status='complete', queue_status='queued')
                    page.evaluate('refresh()')
                    expect(toggle).to_have_text('queued')
                page.locator('#account-menu > summary').click()
                expect(page.locator('#account-options')).to_be_visible()
                page.wait_for_function("() => document.querySelector('#account-options').getAnimations().every(a => a.playState === 'finished')")
                snapshot('accounts', False)
                page.locator('#account-menu > summary').click()
                page.locator('#projects article').first.get_by_role('button', name='Details', exact=True).click()
                expect(page.locator('#detail-overview')).to_be_visible()
                assert page.locator('#project-dialog').get_by_role('button', name='Details', exact=True).count() == 0
                snapshot('details', False)
                page.locator('#close-detail').click()
                page.locator('#usage-daily').click()
                expect(page.locator('#usage-chart-title')).to_contain_text('Daily')
                snapshot('daily')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    report = {'browser': 'Chromium', 'widths': WIDTHS, 'results': results, 'errors': errors}
    (OUTPUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'failures': failures, 'errors': errors, 'screenshots': str(OUTPUT)}))
    assert not errors and not failures, 'Inspect screenshots and overflow report'


if __name__ == '__main__':
    main()
