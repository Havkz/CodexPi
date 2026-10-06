"""Isolated Edge UI regression; --live reads the real Pi dashboard, never resumes goals."""
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/web_assets'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--check-auto-continue', action='store_true', help='Toggle and restore policy only with a sole usage-limited project')
    args = parser.parse_args()
    now = time.time()
    data = {'windows': {'daily': {'remaining': 0, 'duration': 300, 'reset_at': now - 1},
                        'weekly': {'remaining': 67, 'duration': 10080, 'reset_at': now + 86400}},
            'checked_at': now, 'server_time': now, 'error': None,
            'history': {'daily': [], 'weekly': []}}
    for series, values in [('daily', [100, 30, 0, 100, 0]), ('weekly', [80, 20, 100, 80, 67])]:
        data['history'][series] = [{'observed_at': now - 240 + n * 60, 'remaining': value,
            'duration': data['windows'][series]['duration'], 'reset_at': now + 86400,
            'segment': 0 if n < 3 else 1} for n, value in enumerate(values)]
    errors, violations = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: violations.append(message.text) if 'Content Security Policy' in message.text else None)
        if args.live:
            page.goto('http://192.168.2.105:8787/')
            expect(page.locator('link[rel=icon]')).to_have_attribute('href', '/favicon.ico')
            icon = page.request.get('http://192.168.2.105:8787/favicon.ico')
            assert icon.status == 200 and icon.body() == (ASSETS / 'favicon.ico').read_bytes()
            password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
            page.locator('input[name=password]').fill(password)
            page.locator('button[type=submit]').click()
            expect(page.locator('#usage-weekly')).to_be_visible()
            expect(page.locator('#usage-freshness')).to_contain_text('Letzte Messung')
            data = page.request.get('http://192.168.2.105:8787/api/usage').json()
            assert data['history']['weekly'] and data['history']['daily']
            if args.check_auto_continue:
                current = page.request.get('http://192.168.2.105:8787/api/state').json()
                assert len(current['projects']) == 1
                project = current['projects'][0]
                assert project['goal_status'] == 'usage limited' and not project['operation']
                switch = page.get_by_role('switch', name='Auto Continue')
                expect(switch).to_be_enabled()
                original = current['auto_continue']
                try:
                    switch.set_checked(not original)
                    expect(switch).to_be_enabled()
                    page.reload()
                    expect(switch).to_be_checked(checked=not original)
                    fresh = page.request.get('http://192.168.2.105:8787/api/state').json()
                    assert fresh['auto_continue'] is not original
                    assert fresh['selected'] == current['selected']
                    assert fresh['projects'][0]['goal_status'] == 'usage limited'
                    assert not fresh['projects'][0]['operation']
                    assert switch.bounding_box()['y'] < page.locator('#queue-title').bounding_box()['y']
                    page.locator('.queue-policy').screenshot(path=str(ROOT / 'state/auto-continue-live.png'))
                finally:
                    switch.set_checked(original)
                    expect(switch).to_be_enabled()
                    page.reload()
                    expect(switch).to_be_checked(checked=original)
                print('AUTO_CONTINUE_LIVE: persisted across reload; usage-limit slot retained; original policy restored')
        else:
            def route(request):
                path = request.request.url.removeprefix('http://codexpi.test')
                headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'"}
                if path == '/api/usage':
                    request.fulfill(json=data, headers=headers)
                elif path == '/favicon.ico':
                    request.fulfill(body=(ASSETS / 'favicon.ico').read_bytes(), content_type='image/x-icon', headers=headers)
                elif path == '/static/dashboard.js':
                    request.fulfill(body='refreshUsage();', content_type='text/javascript', headers=headers)
                else:
                    file = ASSETS / ('index.html' if path == '/' else path.removeprefix('/static/'))
                    request.fulfill(path=str(file), headers=headers)
            page.context.route('http://codexpi.test/**', route)
            page.goto('http://codexpi.test/')
        expect(page.locator('#usage-weekly')).to_have_attribute('aria-pressed', 'true')
        assert page.locator('main > section').first.get_attribute('id') == 'usage-section'
        page.screenshot(path=str(ROOT / 'state/usage-dashboard-top.png'))
        expect(page.locator('link[rel=icon]')).to_have_attribute('href', '/favicon.ico')
        if args.live:
            # Chromium's special favicon fetch is not reliably intercepted by the fixture route.
            # Decode the real HTTP resource; test_web separately checks every ICO/PNG frame.
            assert page.evaluate('''async () => {
                const image = new Image(); image.src = '/favicon.ico'; await image.decode();
                return [16, 32, 48].includes(image.naturalWidth) && image.naturalWidth === image.naturalHeight;
            }''')
        expect(page.locator('#usage-chart-title')).to_have_text('Weekly')
        for series in ('weekly', 'daily'):
            expected = str(data['windows'][series]['remaining'])
            expect(page.locator('#usage-' + series + '-bar')).to_have_attribute('value', expected)
        page.locator('#usage-daily').click()
        expect(page.locator('#usage-daily')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#usage-chart-title')).to_have_text('Daily / 5h')
        expect(page.locator('#usage-chart-value')).to_contain_text(str(data['windows']['daily']['remaining']))
        if args.live:
            page.locator('#usage-section').screenshot(path=str(ROOT / 'state/usage-live-daily.png'))
        if not args.live:
            assert page.locator('.usage-line').count() == 2  # No line across the missing interval.
            expect(page.locator('#usage-daily-reset')).to_contain_text('neue Bestätigung abwarten')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '0')
            # Reset preview is never a synthetic refill; newly observed values animate.
            data['windows']['daily']['remaining'] = 100
            data['checked_at'] += 60
            page.evaluate('usageRetryAt = 0; refreshUsage(-1)')
            expect(page.locator('#usage-daily-bar')).to_have_attribute('value', '100')
            assert page.locator('.usage-plot').evaluate('(el) => el.getAnimations().length') == 1
            page.emulate_media(reduced_motion='reduce')
            page.locator('#usage-weekly').click()
            assert page.locator('.usage-plot').evaluate('(el) => el.getAnimations().length') == 0
        page.locator('#usage-weekly').click()
        prefix = 'usage-live' if args.live else 'usage-fixture'
        page.locator('#usage-section').screenshot(path=str(ROOT / 'state' / (prefix + '-desktop.png')))
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            expect(page.locator('#usage-weekly')).to_be_visible()
            page.locator('#usage-section').screenshot(path=str(ROOT / 'state' / (prefix + '-mobile-' + str(width) + '.png')))
        if not args.live:
            data['windows'] = {}; data['history'] = {'daily': [], 'weekly': []}
            data['checked_at'] = now - 600; data['error'] = 'test-only offline'
            page.evaluate('usageRetryAt = 0; refreshUsage(-2)')
            expect(page.locator('#usage-weekly-value')).to_have_text('—')
            expect(page.locator('#usage-weekly-bar')).to_be_hidden()
            expect(page.locator('#usage-freshness')).to_contain_text('Veraltete')
            expect(page.locator('#usage-history-note')).to_contain_text('Noch kein Verlauf')
        page.reload()
        expect(page.locator('#usage-weekly')).to_have_attribute('aria-pressed', 'true')
        assert not errors, errors
        assert not violations, violations
        browser.close()
    print(json.dumps({'live': args.live, 'desktop_and_mobile': True, 'weekly_default': True,
        'separate_series': True, 'favicon_decoded_live': args.live, 'page_errors': errors, 'csp_violations': violations,
        'samples': {key: len(value) for key, value in data['history'].items()}}))


if __name__ == '__main__':
    main()
