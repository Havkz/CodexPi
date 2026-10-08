"""Isolated Edge regression; --live only reads the Pi and opens/cancels dialogs."""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/web_assets'
BASE = 'http://192.168.2.105:8787'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--preview', action='store_true', help='Preview local assets against the real Pi, without installing them')
    args = parser.parse_args()
    live = args.live or args.preview
    now = time.time()
    data = {'account_id': 'first', 'windows': {
        'daily': {'remaining': 0, 'duration': 300, 'reset_at': now - 1},
        'weekly': {'remaining': 67, 'duration': 10080, 'reset_at': now + 86400}},
        'checked_at': now, 'server_time': now, 'error': None,
        'history': {'daily': [], 'weekly': []}}
    for series, values in [('daily', [100, 30, 0, 100, 0]), ('weekly', [80, 20, 100, 80, 67])]:
        data['history'][series] = [{'observed_at': now - 240 + n * 60, 'remaining': value,
            'duration': data['windows'][series]['duration'], 'reset_at': now + 86400,
            'segment': 0 if n < 3 else 1} for n, value in enumerate(values)]
    def project(pid, status, priority, pending=0):
        return {'project_id': pid, 'display_name': pid, 'github_repo': 'fixture/' + pid,
            'goal_status': status, 'queue_position': priority, 'pending_prompt_count': pending,
            'completion_notified': True, 'lifecycle': 'ready', 'operation': None,
            'manual_paused': status == 'paused', 'last_activity': now, 'last_ci_status': 'passed',
            'windows_required': False, 'codex_session_id': pid, 'project_path': '/fixture/' + pid}
    state = {'csrf': 'fixture-only', 'selected': 'running', 'pause_all': False,
        'auto_continue': True, 'auto_account_change': False, 'auto_boot_windows': True,
        'accounts': [{'account_id': 'first', 'name': 'First account', 'status': 'ready'}],
        'active_account': 'first', 'account_usage': {'checked_at': now},
        'projects': [project('running', 'active', 1), project('new-work', 'complete', 2, 1),
                     project('held', 'paused', 3), project('finished', 'complete', None)],
        'infrastructure': [{'name': 'Raspberry Pi', 'status': 'online', 'error': 'Fixture diagnostic',
                            'detail': 'Connected', 'checked_at': now},
                           {'name': 'Windows', 'status': 'online', 'error': None, 'detail': 'Signed worker',
                            'checked_at': now, 'heartbeat_age': 4}]}
    errors, violations, mutations = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: violations.append(message.text) if 'Content Security Policy' in message.text else None)
        def guard(route):
            if route.request.post_data_json.get('action') == 'logout' and live:
                if args.preview:
                    route.fulfill(response=route.fetch())
                else:
                    route.continue_()
            else:
                mutations.append(route.request.post_data_json)
                route.abort()
        page.route('**/api/action', guard)
        if live:
            page.goto(BASE)
            password = os.environ.get('CODEXPI_DASHBOARD_PASSWORD') or getpass('Dashboard password (not logged): ')
            page.locator('input[name=password]').fill(password)
            password = None
            page.locator('button[type=submit]').click()
            expect(page.locator('#usage-weekly')).to_be_visible()
            if args.preview:
                page.route(BASE + '/', lambda route: route.fulfill(path=str(ASSETS / 'index.html')))
                page.route(BASE + '/static/**', lambda route: route.fulfill(
                    path=str(ASSETS / route.request.url.rsplit('/', 1)[-1])))
                # Routed HTML has no LAN address-space metadata; proxy read-only API fetches.
                for path in ('/api/state', '/api/usage', '/api/projects/*'):
                    page.route(BASE + path, lambda route: route.fulfill(response=route.fetch()))
                page.reload()
            data = page.request.get(BASE + '/api/usage').json()
            expect(page.locator('#usage-freshness')).not_to_be_empty()
            assert page.request.get(BASE + '/favicon.ico').body() == (ASSETS / 'favicon.ico').read_bytes()
        else:
            def route(request):
                path = request.request.url.removeprefix('http://codexpi.test')
                headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'"}
                if path == '/api/state':
                    request.fulfill(json=state, headers=headers)
                elif path == '/api/usage':
                    request.fulfill(json=data, headers=headers)
                elif path.startswith('/api/projects/'):
                    p = next(p for p in state['projects'] if p['project_id'] == path.rsplit('/', 1)[-1])
                    request.fulfill(json={'project': p, 'commits': [], 'jobs': [], 'events': []}, headers=headers)
                else:
                    file = ASSETS / ('index.html' if path == '/' else path.removeprefix('/static/'))
                    request.fulfill(path=str(file), headers=headers)
            page.context.route('http://codexpi.test/**', route)
            page.goto('http://codexpi.test/')
        expect(page.locator('#usage-chart-value')).not_to_have_text('—')
        expect(page.locator('#usage-weekly')).to_have_attribute('aria-pressed', 'true')
        assert page.locator('main > section').first.get_attribute('id') == 'usage-section'
        assert page.locator('html').get_attribute('lang') == 'en'
        assert page.locator('#usage-history-note').count() == 0
        expect(page.locator('link[rel=icon]')).to_have_attribute('href', '/favicon.ico')
        expect(page.locator('#usage-chart-title')).to_have_text('Weekly')
        page.evaluate('window.savedUsageSvg = document.querySelector("#usage-chart svg"); window.savedUsageLine = document.querySelector(".usage-line")')
        page.evaluate('usageRetryAt = 0; refreshUsage(-1, usageAccount)')
        expect(page.locator('#usage-weekly-value')).to_contain_text(str(data['windows']['weekly']['remaining']))
        assert page.evaluate('savedUsageSvg === document.querySelector("#usage-chart svg") && savedUsageLine === document.querySelector(".usage-line")')
        assert page.locator('.usage-plot').evaluate('(el) => el.getAnimations().length') == 0
        page.locator('#usage-daily').click()
        expect(page.locator('#usage-daily')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#usage-chart-title')).to_contain_text('Daily')
        if not live:
            assert page.locator('.usage-line').count() == 2
            assert page.locator('.usage-gap[d^="M"]').count() == 1
            expect(page.locator('#usage-daily-reset')).to_contain_text('awaiting confirmation')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '0')
            # Reset time alone never refills usage. Only a new real measurement changes it.
            page.evaluate('renderUsage()')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '0')
            data['windows']['daily']['remaining'] = 100
            data['history']['daily'].append({**data['history']['daily'][-1], 'observed_at': now + 60, 'remaining': 100})
            data['checked_at'] += 60
            page.evaluate('refreshUsage(-2, usageAccount)')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '100')
            assert page.evaluate('savedUsageSvg === document.querySelector("#usage-chart svg")')
            assert page.locator('.usage-plot').evaluate('(el) => el.getAnimations().length') == 0
            assert page.locator('.usage-point').evaluate_all('(els) => els.some(el => el.getAnimations().length > 0)')
            page.emulate_media(reduced_motion='reduce')
            data['history']['daily'][-1]['remaining'] = 90
            page.evaluate('refreshUsage(-3, usageAccount)')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '100')
            page.wait_for_function('() => Math.abs(Number([...document.querySelectorAll(".usage-point")].at(-1).getAttribute("cy")) - 30.4) < 0.001')
            assert page.locator('.usage-point').evaluate_all('(els) => els.every(el => el.getAnimations().length === 0)')
            page.emulate_media(reduced_motion='no-preference')
            # An old account response must never repaint the next account's history.
            page.evaluate('refreshUsage(-4, "second")')
            expect(page.locator('#usage-weekly-value')).to_have_text('—')
            expect(page.locator('#usage-empty')).to_be_visible()
            assert page.locator('.usage-line').count() == 0
            data['account_id'] = 'second'
            data['windows']['weekly']['remaining'] = 23
            data['history']['weekly'] = [data['history']['weekly'][-1] | {'remaining': 23}]
            page.evaluate('refreshUsage(-5, "second")')
            expect(page.locator('#usage-weekly-value')).to_have_text('23%')
            expect(page.locator('#top-status')).to_contain_text('Raspberry Pi needs attention')
            expect(page.locator('#infra .badge').first).to_have_text('error')
            page.locator('.infra-diagnostics').first.evaluate('(el) => el.open = true')
            page.evaluate('render()')
            assert page.locator('.infra-diagnostics').first.get_attribute('open') is not None
            queued = page.locator('#queue tr[data-id="new-work"]')
            expect(queued.locator('.badge')).to_have_text('queued')
            expect(queued.get_by_role('button', name='Resume', exact=True)).to_be_enabled()
            expect(queued.get_by_role('button', name='Run now', exact=True)).to_be_enabled()
            assert queued.get_by_role('button', name='Details', exact=True).count() == 0
            assert page.locator('#queue tr[data-id="running"]').get_by_role('button', name='Resume', exact=True).count() == 0
            finished = page.locator('#projects article').filter(has=page.get_by_role('heading', name='finished', exact=True))
            assert finished.get_by_role('button', name='Resume', exact=True).count() == 0
            data['windows'] = {}
            data['history'] = {'daily': [], 'weekly': []}
            data['error'] = 'Fixture offline'
            page.evaluate('refreshUsage(-6, usageAccount)')
            expect(page.locator('#usage-weekly-value')).to_have_text('—')
            expect(page.locator('#usage-weekly-bar')).to_be_hidden()
            expect(page.locator('#usage-freshness')).to_have_text('Usage unavailable')
        # Details remain usable; deletion always defaults to preserving GitHub.
        page.locator('#projects article').first.get_by_role('button', name='Details', exact=True).click()
        expect(page.locator('#detail-overview')).to_be_visible()
        assert page.locator('#project-dialog').get_by_role('button', name='Details', exact=True).count() == 0
        page.locator('#project-dialog').get_by_role('button', name='Delete', exact=True).click()
        checkbox = page.get_by_role('checkbox', name='Also delete the GitHub repository')
        expect(checkbox).not_to_be_checked()
        checkbox.check()
        page.locator('#lifecycle-cancel').click()
        page.locator('#projects article').first.get_by_role('button', name='Details', exact=True).click()
        page.locator('#project-dialog').get_by_role('button', name='Delete', exact=True).click()
        expect(checkbox).not_to_be_checked()
        page.locator('#lifecycle-cancel').click()
        page.locator('#usage-weekly').click()
        prefix = 'dashboard-preview' if args.preview else 'dashboard-live' if live else 'dashboard-fixture'
        page.screenshot(path=str(ROOT / 'state' / (prefix + '-desktop.png')), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            expect(page.locator('#usage-weekly')).to_be_visible()
            page.screenshot(path=str(ROOT / 'state' / (prefix + '-mobile-' + str(width) + '.png')), full_page=True)
        page.reload()
        expect(page.locator('#usage-weekly')).to_have_attribute('aria-pressed', 'true')
        assert not errors, errors
        assert not violations, violations
        assert not mutations, mutations
        if live:
            expect(page.locator('#freshness')).to_contain_text('Live')
            expect(page.locator('#logout')).to_be_enabled()
            if args.preview:
                page.unroute(BASE + '/')
            page.locator('#logout').click()
            expect(page.locator('input[name=password]')).to_be_visible()
        browser.close()
    print(json.dumps({'live': live, 'preview': args.preview, 'desktop_mobile': True,
        'stable_chart': True, 'account_isolation': not live, 'contextual_controls': not live,
        'delete_default_kept': True, 'page_errors': errors, 'csp_violations': violations, 'mutations': mutations}))


if __name__ == '__main__':
    main()
