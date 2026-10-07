"""Read-only live block presentation check; never sends project actions."""
import argparse
import getpass
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://192.168.2.105:8787')
    parser.add_argument('--project', default='Sybu-Debug')
    args = parser.parse_args()
    password = os.environ.get('CODEXPI_TEST_PASSWORD') or getpass.getpass('Dashboard password: ')
    output = Path(__file__).resolve().parents[1] / 'state/design-checks'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.base)
            page.get_by_label('Passwort').fill(password)
            password = None
            page.get_by_role('button', name='Anmelden').click()
            card = page.locator('#projects .project-card').filter(has_text=args.project)
            card.get_by_role('button', name='Details', exact=True).click()
            blocker = page.locator('#detail-overview .block-reason')
            blocker.wait_for()
            for width, height in [(1440, 1000), (375, 812)]:
                page.set_viewport_size({'width': width, 'height': height})
                labels = blocker.locator('section > strong').all_text_contents()
                assert labels in (['Reason', 'Erklärung', 'Lösung'], ['Reasons', 'Erklärung', 'Lösung']), labels
                assert blocker.locator('section').nth(2).inner_text().strip() != 'Lösung'
                assert blocker.get_by_text('Kein automatisches Resume ohne Nutzerfreigabe.', exact=True).is_visible()
                details = blocker.locator('details')
                assert not details.locator('pre').is_visible()
                details.locator('summary').click()
                assert details.locator('pre').is_visible()
                # Reloaded API state must not collapse the user's technical details.
                page.wait_for_function("document.getElementById('freshness').textContent.includes('Live')")
                page.wait_for_timeout(2300)
                assert blocker.locator('details').get_attribute('open') is not None
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert page.locator('#project-dialog').evaluate('(el) => el.scrollWidth <= el.clientWidth')
                page.screenshot(path=str(output / f'blocking-{width}.png'))
                blocker.locator('summary').click()
            assert not errors, errors
            print('LIVE_BLOCK_PRESENTATION_OK: ordered sections, actionable solution, technical details, desktop/mobile')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
