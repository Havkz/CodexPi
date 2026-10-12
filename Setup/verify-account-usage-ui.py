"""Isolated Chromium check of real assets: chart selection must never change native auth."""
import importlib.util
import json
from urllib.parse import parse_qs, urlsplit
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usage_fixture', ROOT / 'Setup/verify-usage-ui.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
state, first = fixture.fixture()
second = json.loads(json.dumps(first))
second['account_id'] = 'second'
second['windows']['weekly']['remaining'] = 23
second['history']['weekly'] = [second['history']['weekly'][-1] | {'remaining': 23}]
samples = {'first': first, 'second': second}
errors, mutations = [], []
stale_response = False

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080})
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request):
        url = urlsplit(request.request.url)
        headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'"}
        if request.request.method != 'GET':
            mutations.append(url.path); request.abort(); return
        if url.path == '/api/state':
            request.fulfill(json=state, headers=headers)
        elif url.path == '/api/usage':
            ident = parse_qs(url.query).get('account_id', [state['active_account']])[0]
            request.fulfill(json=first if stale_response else samples[ident], headers=headers)
        else:
            request.fulfill(path=str(ROOT / 'app/web_assets' / ('index.html' if url.path == '/' else url.path.removeprefix('/static/'))), headers=headers)
    page.route('http://codexpi.test/**', route)
    page.goto('http://codexpi.test/')
    expect(page.locator('#usage-chart-value')).to_have_text('67%')
    page.locator('#usage-account-menu summary').click()
    stale_response = True
    page.locator('#usage-account-options button').nth(1).click()
    expect(page.locator('#usage-chart-value')).to_have_text('—')
    expect(page.locator('#usage-empty')).to_be_visible()
    page.wait_for_function('!usageLoading')
    stale_response = False
    page.evaluate('refreshUsage(undefined, usageAccount)')
    expect(page.locator('#usage-chart-value')).to_have_text('23%')
    expect(page.locator('#account-current')).to_have_text('First account')
    page.evaluate('refresh()')
    expect(page.locator('#usage-chart-value')).to_have_text('23%')
    expect(page.locator('#usage-freshness')).to_have_text('Live')
    for width in (1440, 430, 390, 375, 320):
        page.set_viewport_size({'width': width, 'height': 1080})
        page.locator('#usage-account-menu summary').click()
        menu = page.locator('#usage-account-options')
        bounds = menu.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert menu.evaluate('(el) => el.scrollWidth <= el.clientWidth')
        page.locator('#usage-section').screenshot(path=str(ROOT / 'state' / ('account-usage-' + str(width) + '.png')))
        page.locator('#usage-account-menu').press('Escape')
    second['checked_at'] -= 86400
    page.evaluate('refreshUsage(-1, usageAccount)')
    expect(page.locator('#usage-freshness')).to_contain_text('Last updated')
    second['error'] = 'Live usage could not be confirmed'
    page.evaluate('refreshUsage(-2, usageAccount)')
    expect(page.locator('#usage-freshness')).to_have_text('Usage unavailable')
    assert state['active_account'] == 'first' and not mutations and not errors
    browser.close()
print(json.dumps({'chromium': True, 'widths': [320, 375, 390, 430, 1440], 'account_isolation': True,
                  'stale_response_rejected': True, 'overflow': False, 'mutations': mutations, 'errors': errors}))
