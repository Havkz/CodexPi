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


def fixture():
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
        'accounts': [{'account_id': 'first', 'name': 'First account', 'status': 'ready'},
                     {'account_id': 'second', 'name': 'another-account-with-a-long-email@example.com', 'status': 'ready'}],
        'active_account': 'first', 'account_usage': {'checked_at': now},
        'projects': [project('running', 'active', 1), project('new-work', 'complete', 2, 1),
                     project('held', 'paused', 3), project('finished', 'complete', None)],
        'infrastructure': [{'name': 'Raspberry Pi', 'status': 'online', 'error': 'Fixture diagnostic',
                            'detail': 'Connected', 'checked_at': now},
                           {'name': 'Windows', 'status': 'online', 'error': None, 'detail': 'Signed worker',
                            'checked_at': now, 'heartbeat_age': 4}]}
    return state, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--preview', action='store_true', help='Preview local assets against the real Pi, without installing them')
    args = parser.parse_args()
    live = args.live or args.preview
    state, data = fixture()
    now = data['checked_at']
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
        page.locator('#usage-chart').hover(position={'x': 18, 'y': 40})
        expect(page.locator('#usage-tooltip')).to_be_visible()
        assert page.evaluate('usageData.history[usageView].some(sample => new Date(sample.observed_at * 1000).toISOString() === document.querySelector("#usage-tooltip-time").dateTime)')
        page.locator('#usage-section').screenshot(path=str(ROOT / 'state/usage-tooltip.png'))
        page.locator('#usage-chart').press('Escape')
        if not live:
            assert page.locator('.usage-line').count() == 2
            assert page.locator('.usage-gap[d^="M"]').count() == 1
            assert 'C' in page.locator('.usage-line').first.get_attribute('d')
            chart = page.locator('#usage-chart')
            chart.hover(position={'x': 18, 'y': 40})
            expect(page.locator('#usage-tooltip-value')).to_have_text('100% remaining')
            expect(page.locator('#usage-tooltip-time')).to_have_attribute('datetime',
                page.evaluate('new Date(usageData.history.daily[0].observed_at * 1000).toISOString()'))
            chart.press('ArrowRight')
            expect(page.locator('#usage-tooltip-value')).to_have_text('30% remaining')
            chart.press('Escape')
            expect(page.locator('#usage-tooltip')).to_be_hidden()
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
            state['active_account'] = 'second'
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
            assert page.locator('.queue-grip').count() == 3
            assert page.locator('.queue-grip').first.locator('.grip-dots i').count() == 6
            # Reorder goes through the same API; no run-now, resume or second AI session.
            reorders = []
            def reorder(route):
                body = route.request.post_data_json
                assert body['action'] == 'reorder', body
                reorders.append(body['ids'])
                for position, pid in enumerate(body['ids'], 1):
                    next(p for p in state['projects'] if p['project_id'] == pid)['queue_position'] = position
                state['projects'].sort(key=lambda p: p['queue_position'] or 999)
                route.fulfill(json={'ok': True})
            page.route('**/api/action', reorder)
            page.locator('#queue tr[data-id="new-work"] .queue-grip').press('ArrowUp')
            expect(page.locator('#queue tr').first).to_have_attribute('data-id', 'new-work')
            expect(page.locator('#queue tr[data-id="new-work"] .queue-grip')).to_be_enabled()
            page.locator('#queue tr[data-id="new-work"] .queue-grip').drag_to(page.locator('#queue tr[data-id="running"]'))
            expect(page.locator('#queue tr').first).to_have_attribute('data-id', 'running')
            # Start on the status cell, not the handle. Real mouse drag must reach the same queue API.
            page.locator('#queue tr[data-id="new-work"] td').nth(2).drag_to(page.locator('#queue tr[data-id="running"] td').nth(2))
            expect(page.locator('#queue tr').first).to_have_attribute('data-id', 'new-work')
            page.locator('#queue tr[data-id="new-work"] .queue-grip').press('ArrowDown')
            expect(page.locator('#queue tr').first).to_have_attribute('data-id', 'running')
            assert reorders == [['new-work', 'running', 'held'], ['running', 'new-work', 'held']] * 2
            state['projects'][1].update(goal_status='paused', manual_paused=False, pending_prompt_count=0)
            page.evaluate('refresh()')
            expect(page.locator('#queue tr[data-id="new-work"] .badge')).to_have_text('queued')
            expect(page.locator('#queue tr[data-id="held"] .badge')).to_have_text('paused')
            page.locator('#queue tr[data-id="new-work"] .queue-name').click()
            expect(page.locator('#project-dialog')).to_be_visible()
            page.locator('#close-detail').click()
            assert len(reorders) == 4  # Clicking a name opens details; it never reorders.
            page.unroute('**/api/action', reorder)
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
        page.wait_for_function('() => document.querySelector("#usage-section").getAnimations().every(animation => animation.playState === "finished")')
        page.evaluate('window.savedEntryAnimation = document.querySelector("#usage-section").getAnimations()[0]; render()')
        assert page.evaluate('savedEntryAnimation === document.querySelector("#usage-section").getAnimations()[0]')
        menu = page.locator('#account-menu')
        menu.locator('summary').click()
        expect(page.locator('#account-options')).to_be_visible()
        page.evaluate('window.savedAccountOption = document.querySelector(".account-option button"); render()')
        assert page.evaluate('savedAccountOption === document.querySelector(".account-option button")')
        assert page.locator('#account-options').evaluate('(el) => { const box = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height - 15)); }')
        page.wait_for_function('() => document.querySelector("#account-options").getAnimations().every(animation => animation.playState === "finished")')
        page.screenshot(path=str(ROOT / 'state/account-menu-desktop.png'))
        menu.press('Escape')
        assert menu.get_attribute('open') is None
        prefix = 'dashboard-preview' if args.preview else 'dashboard-live' if live else 'dashboard-fixture'
        page.screenshot(path=str(ROOT / 'state' / (prefix + '-desktop.png')), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            expect(page.locator('#usage-weekly')).to_be_visible()
            menu.locator('summary').click()
            bounds = page.locator('#account-options').bounding_box()
            assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
            assert page.locator('#account-options').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            assert page.locator('#account-options').evaluate('(el) => { const box = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height - 15)); }')
            page.screenshot(path=str(ROOT / 'state' / ('account-menu-' + prefix + '-' + str(width) + '.png')))
            menu.press('Escape')
            page.screenshot(path=str(ROOT / 'state' / (prefix + '-mobile-' + str(width) + '.png')), full_page=True)
        page.reload()
        expect(page.locator('body')).to_have_class('dashboard-ready')
        expect(page.locator('#usage-weekly')).to_have_attribute('aria-pressed', 'true')
        if not live:
            page.route('http://codexpi.test/api/state', lambda route: route.fulfill(status=503, json={'error': 'Fixture offline'}))
            page.reload()
            expect(page.locator('#notice')).to_have_text('Dashboard unavailable')
            expect(page.locator('body')).to_have_class('dashboard-ready')
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
