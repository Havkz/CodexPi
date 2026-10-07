"""Isolated browser regression; never connects to the Pi or changes real accounts."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    assets = Path(__file__).resolve().parents[1] / 'app/web_assets'
    first, second = 'a' * 64, 'b' * 64
    state = {'projects': [], 'selected': None, 'csrf': 'test-csrf', 'active_account': first,
        'accounts': [{'account_id': first, 'name': 'First Account', 'status': 'ready'},
                     {'account_id': second, 'name': 'Second Account', 'status': 'ready'}],
        'account_operation': {}, 'auto_account_change': False, 'auto_continue': False,
        'account_usage': {'checked_at': 1}, 'infrastructure': [], 'windows_online': True,
        'unsnooze': {}, 'discord_online': False}
    requests, errors = [], []
    def route(request):
        path = urlsplit(request.request.url).path
        if path == '/api/state':
            request.fulfill(json=state)
        elif path == '/api/usage':
            remaining = 70 if state['active_account'] == first else 20
            request.fulfill(json={'account_id': state['active_account'], 'checked_at': 1,
                'windows': {key: {'remaining': remaining, 'duration': 10080 if key == 'weekly' else 300}
                            for key in ('weekly', 'daily')}, 'history': {}, 'server_time': 1})
        elif path == '/api/action':
            body = request.request.post_data_json
            requests.append(body)
            if body['action'] == 'account-switch':
                state['account_operation'] = {'id': 'switch', 'phase': 'waiting_turn', 'target_account': second}
                request.fulfill(json={'ok': True, 'operation_id': 'switch'})
            elif body['action'] == 'account-remove':
                assert body['account_id'] == first and body['confirmation'] == 'First Account'
                state['accounts'] = state['accounts'][1:]
                request.fulfill(json={'ok': True})
            else:
                request.fulfill(json={'ok': True})
        else:
            file = assets / (path.removeprefix('/static/') if path.startswith('/static/') else 'index.html')
            request.fulfill(path=str(file))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('http://codexpi-test.local/**', route)
        page.goto('http://codexpi-test.local/')
        expect(page.locator('#account-current')).to_have_text('First Account')
        expect(page.locator('#usage-weekly-value')).to_have_text('70 %')
        page.locator('#account-menu summary').click()
        expect(page.locator('#account-options > button').last).to_have_text('＋ Account hinzufügen')
        page.get_by_role('button', name='Second Account', exact=True).click()
        expect(page.locator('#account-menu summary')).to_have_class('loading')
        expect(page.locator('#account-current')).to_have_text('First Account')
        expect(page.locator('#account-status')).to_contain_text('Abschluss des aktuellen Turns')
        assert len(requests) == 1  # HTTP success alone never claims a completed account change.
        state.update(active_account=second, account_operation={'id': 'switch', 'phase': 'complete', 'target_account': second})
        expect(page.locator('#account-current')).to_have_text('Second Account', timeout=5000)
        expect(page.locator('#account-menu summary')).not_to_have_class('loading')
        expect(page.locator('#usage-weekly-value')).to_have_text('20 %')  # Same timestamp, different account.
        page.locator('#account-menu summary').click()
        page.get_by_role('button', name='First Account entfernen', exact=True).click()
        expect(page.locator('#account-remove-dialog')).to_be_visible()
        assert len(requests) == 1  # Opening confirmation is not removal.
        page.locator('#account-remove-submit').click()
        expect(page.locator('#account-remove-dialog')).not_to_be_visible()
        assert requests[-1]['action'] == 'account-remove'
        controls = page.locator('.account-control').bounding_box()
        usage = page.locator('#usage-section').bounding_box()
        assert controls['y'] < usage['y']
        assert page.locator('#auto-account-change').evaluate(
            "el => Boolean(document.querySelector('#auto-continue').compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)")
        assert not errors, errors
        browser.close()
    print(json.dumps({'account_menu': 'passed', 'controller_confirmation': 'passed',
        'account_usage_refresh': 'passed', 'remove_confirmation': 'passed', 'placement': 'passed'}))


if __name__ == '__main__':
    main()
