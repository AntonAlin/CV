#!/usr/bin/env python3
"""Render the social-sharing image (og-image.png) from the live page.

LinkedIn, Slack and the rest show this card whenever the CV's URL is
shared. Rendering it from index.html itself, in the PDF workflow, means it
can never drift from the page: same name, same title, same sky.

    python tools/build-og.py           # writes og-image.png (1200x630)
"""
import os
import pathlib
import sys

import fontmirror
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "og-image.png"
SITE = (ROOT / "index.html").as_uri()
W, H = 1200, 630


def main():
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        # Nothing external: the sky and the cards fall back to their drawings.
        page.route("**/*", lambda r: r.abort() if r.request.url.startswith("http") else r.continue_())
        fontmirror.prepare(page, SITE)
        page.evaluate("""() => {
          document.body.classList.remove('tod-day', 'tod-dusk', 'tod-dawn');
          document.body.classList.add('tod-night', 'og-mode');
          document.dispatchEvent(new CustomEvent('cv:tod'));
          setLang('en');
          document.querySelectorAll('.reveal').forEach(e => e.classList.add('is-in'));
        }""")
        page.wait_for_timeout(2800)   # aurora colours ease over 2.6 s
        page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()
    size = OUT.stat().st_size
    if size < 20_000:
        sys.exit(f"og-image.png looks empty ({size} bytes)")
    print(f"wrote {OUT.name} ({W}x{H}, {size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
