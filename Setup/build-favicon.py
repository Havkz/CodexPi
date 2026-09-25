"""Render the existing HTML/CSS brand mark into a multi-resolution ICO.

No reference image or new artwork; regenerate after changing the dashboard logo.
Uses the already installed isolated Edge/Playwright verification environment.
"""
from pathlib import Path
import struct

from playwright.sync_api import sync_playwright

ASSETS = Path(__file__).resolve().parents[1] / 'app/web_assets'


def main():
    frames = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        for size in (16, 32, 48):
            context = browser.new_context(viewport={'width': 500, 'height': 500}, device_scale_factor=size / 35)
            page = context.new_page()
            def route(request):
                asset = 'style.css' if request.request.url.endswith('/style.css') else 'login.html'
                request.fulfill(path=str(ASSETS / asset))
            page.route('http://codexpi.test/**', route)
            page.goto('http://codexpi.test/')
            # Place the unchanged 35px mark on an exact pixel origin for small ICO frames.
            page.add_style_tag(content='.brand-mark { position: fixed; top: 0; left: 0; margin: 0; }')
            png = page.locator('.brand-mark').screenshot(omit_background=True, animations='disabled')
            assert struct.unpack('>II', png[16:24]) == (size, size), (size, struct.unpack('>II', png[16:24]))
            frames.append((size, png))
            context.close()
        browser.close()
    header = struct.pack('<HHH', 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = []
    for size, png in frames:
        entries.append(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    target = ASSETS / 'favicon.ico'
    target.write_bytes(header + b''.join(entries) + b''.join(png for _, png in frames))
    preview = ASSETS.parents[1] / 'state/favicon-preview.png'
    preview.parent.mkdir(exist_ok=True)
    preview.write_bytes(frames[-1][1])
    print('Built favicon.ico from existing brand-mark: 16, 32, 48px')


if __name__ == '__main__':
    main()
