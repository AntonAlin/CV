#!/usr/bin/env python3
"""Render the CV to PDF, in both languages and both lengths.

Run locally with `python tools/build-pdf.py`, or let the workflow in
.github/workflows/build-pdf.yml run it on every push to main. Regenerating on
every push is the point: the downloadable file can never drift from the page.

The page-count assertions at the end are the real safety net. The print sheet is
tuned to fill two pages (or one, short) almost exactly, so any edit that pushes
it over shows up here rather than in somebody's inbox.
"""
import os
import pathlib
import sys

import pymupdf
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "pdf"
SITE = (ROOT / "index.html").as_uri()

# (lang, short?, filename, PDF title, expected page count)
VARIANTS = [
    ("sv", False, "anton-alin-cv-sv.pdf",    "Anton Ålin — CV",             2),
    ("en", False, "anton-alin-cv-en.pdf",    "Anton Ålin — CV",             2),
    ("sv", True,  "anton-alin-cv-sv-1p.pdf", "Anton Ålin — CV (en sida)",   1),
    ("en", True,  "anton-alin-cv-en-1p.pdf", "Anton Ålin — CV (one page)",  1),
]

KEYWORDS = ("Data, Business Intelligence, Microsoft Fabric, Power BI, "
            "Data Governance, Predictive Analytics, Financial Data")


def render(page, lang, short, path):
    page.goto(SITE)
    # Webfonts change line breaking, which changes pagination. Wait for them
    # rather than racing them, or CI produces a different document than a desk.
    # `fonts.ready` settles either way, so a blocked font host stalls nothing.
    page.evaluate("document.fonts.ready")
    page.evaluate(f"setLang('{lang}')")
    # A printed CV without contact details is useless; the page reveals them on
    # beforeprint anyway, but page.pdf() does not fire that event.
    page.evaluate("revealContact()")
    page.evaluate(
        "s => document.body.classList.toggle('print-short', s)", short)
    page.wait_for_timeout(300)
    page.pdf(path=str(path), format="A4", print_background=True)


def stamp(path, title):
    doc = pymupdf.open(path)
    doc.set_metadata({
        "title": title,
        "author": "Anton Ålin",
        "subject": "Curriculum vitae — Head of Data & BI",
        "keywords": KEYWORDS,
        "creator": "antonalin.github.io/CV",
    })
    doc.saveIncr()
    pages = doc.page_count
    doc.close()
    return pages


def main():
    OUT.mkdir(exist_ok=True)
    problems = []
    with sync_playwright() as p:
        # CI installs its own matching Chromium; set CHROMIUM_PATH to reuse a
        # browser that is already on the machine instead.
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        for lang, short, name, title, expected in VARIANTS:
            path = OUT / name
            render(page, lang, short, path)
            pages = stamp(path, title)
            ok = pages == expected
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {pages} page(s), "
                  f"expected {expected}, {path.stat().st_size // 1024} KB")
            if not ok:
                problems.append(f"{name} rendered {pages} pages, expected {expected}")
        browser.close()

    if problems:
        print("\nprint layout regressed:", *problems, sep="\n  ")
        return 1
    print(f"\n{len(VARIANTS)} PDFs written to {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
