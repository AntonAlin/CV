"""Print/PDF assertions. The PDF is the version most readers\nactually receive, so it gets its own suite rather than riding on the screen tests.

Standalone script — `python tests/test_print.py`. CI runs it from
.github/workflows/tests.yml on every push. Set CHROMIUM_PATH to reuse a browser
already on the machine instead of the one Playwright installs.
"""
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / "index.html").as_uri()
WORK = pathlib.Path(tempfile.mkdtemp(prefix="cv-tests-"))
CHROMIUM = os.environ.get("CHROMIUM_PATH")


def launch(pw):
    """Playwright's own Chromium unless the machine already has a matching one."""
    return pw.chromium.launch(executable_path=CHROMIUM) if CHROMIUM else pw.chromium.launch()

import sys
import pymupdf
from playwright.sync_api import sync_playwright

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "  -> " + str(extra)))
    if not cond: fails.append(name)

def build(lang, path):
    with sync_playwright() as p:
        b = launch(p)
        pg = b.new_page(viewport={"width": 900, "height": 1200})
        pg.goto(URL); pg.wait_for_timeout(1100)
        pg.evaluate(f"setLang('{lang}')"); pg.evaluate("revealContact()")
        pg.wait_for_timeout(400)
        pg.pdf(path=path, format="A4", print_background=True)
        b.close()
    return pymupdf.open(path)

for lang, other_words, own_words in [
    ("sv", ["Experience", "Native", "Head of Data & BI", "Sales Executive"],
           ["Erfarenhet", "Modersmål", "Data- och BI-ansvarig", "Säljare"]),
    ("en", ["Erfarenhet", "Modersmål", "Data- och BI-ansvarig", "Säljare"],
           ["Experience", "Native", "Head of Data & BI", "Sales Executive"]),
]:
    d = build(lang, str(WORK / f"t_{lang}.pdf"))
    text = " ".join(p.get_text() for p in d)
    H = d[0].rect.height
    print(f"\n=== {lang.upper()} ===")

    check(f"[{lang}] fits on exactly 2 pages", d.page_count == 2, d.page_count)

    # Both pages must be well filled: a half-empty last page reads as sloppy.
    fills = []
    for i, pg in enumerate(d):
        body = [b for b in pg.get_text("blocks") if b[4].strip()
                and "Anton Ålin · CV" not in b[4]]
        fills.append(max(b[3] for b in body) / H)
    check(f"[{lang}] every page is at least 85% filled",
          all(f > .85 for f in fills), [f"{f:.0%}" for f in fills])

    check(f"[{lang}] prints only its own language",
          all(w not in text for w in other_words) and all(w in text for w in own_words),
          [w for w in other_words if w in text] or
          [w for w in own_words if w not in text])

    # Running identity + page number belong on continuation pages only.
    p1, p2 = d[0].get_text(), d[1].get_text()
    check(f"[{lang}] page 1 carries no running footer", "Anton Ålin · CV" not in p1)
    check(f"[{lang}] page 2 identifies itself", "Anton Ålin · CV" in p2)
    check(f"[{lang}] page 2 is numbered 2 / 2", "2 / 2" in p2, repr(p2[-60:]))

    # Screen-only chrome must never reach paper.
    for word in ["Sök", "Search", "ESC", "Skriv ut", "Visa e-post", "Show email"]:
        check(f"[{lang}] screen chrome absent: {word!r}", word not in text)

    # Contact belongs in the header, once — not repeated in the closing line.
    check(f"[{lang}] contact appears exactly once", text.count("+46 73 724 96 87") == 1,
          text.count("+46 73 724 96 87"))
    check(f"[{lang}] closing line has no dangling separator",
          "begäran. ·" not in text and "request. ·" not in text)

    # Swedish practice includes a CV photo; US/UK guidance discourages one.
    imgs = len(d[0].get_images())
    if lang == "sv":
        check("[sv] portrait printed", imgs == 1, imgs)
    else:
        check("[en] portrait suppressed", imgs == 0, imgs)

    d.close()


# --- Short (one-page) variant, rendered from the same DOM ---
import cv2, re
print("\n=== SHORT VARIANT ===")
for lang in ("sv", "en"):
    with sync_playwright() as p:
        b = launch(p)
        pg = b.new_page(viewport={"width": 900, "height": 1200})
        pg.goto(URL); pg.wait_for_timeout(1100)
        pg.evaluate(f"setLang('{lang}')"); pg.evaluate("revealContact()")
        pg.evaluate("document.body.classList.add('print-short')"); pg.wait_for_timeout(400)
        pg.pdf(path=str(WORK / f"t_{lang}_1p.pdf"), format="A4", print_background=True)
        b.close()
    d = pymupdf.open(str(WORK / f"t_{lang}_1p.pdf"))
    text = d[0].get_text()
    check(f"[{lang}-1p] fits on a single page", d.page_count == 1, d.page_count)
    # Withholding sections would otherwise leave the numbers reading 01, 03, 04.
    heads = [l for l in text.splitlines() if re.match(r"^0\d\s+\S", l)]
    want = (["01 Erfarenhet", "02 Kompetens", "03 Utbildning"] if lang == "sv"
            else ["01 Experience", "02 Skills", "03 Education"])
    check(f"[{lang}-1p] sections renumbered without gaps", heads == want, heads)
    for gone in (["Utvalda projekt","Meriter"] if lang=="sv"
                 else ["Selected Projects","Achievements"]):
        check(f"[{lang}-1p] withheld: {gone!r}", gone not in text)
    for kept in (["Erfarenhet","Kompetens","Utbildning"] if lang=="sv"
                 else ["Experience","Skills","Education"]):
        check(f"[{lang}-1p] kept: {kept!r}", kept in text)
    d.close()

# --- QR bridges paper back to the live page ---
print("\n=== QR ===")
det = cv2.QRCodeDetector()
TARGET = "https://antonalin.github.io/CV/"
for name in ("t_sv.pdf", "t_en.pdf", "t_sv_1p.pdf", "t_en_1p.pdf"):
    d = pymupdf.open(str(WORK / name)); pg_ = d[-1]
    box = next((dr["rect"] for dr in pg_.get_drawings()
                if 20 < dr["rect"].width < 40
                and abs(dr["rect"].width - dr["rect"].height) < 3), None)
    check(f"[{name}] QR is on the last page", box is not None)
    if box:
        mm = box.width / 72 * 25.4
        check(f"[{name}] QR is at least 9mm across", mm >= 9, f"{mm:.1f}mm")
        # Model a phone pointed at the code. 300dpi over an 11mm code is ~125px,
        # still far below what a 12MP camera at 10cm actually resolves (~440px),
        # so this stays a conservative bar. 150dpi (62px) was below OpenCV's own
        # detection floor and failed on the densest page while the code itself
        # was fine — that measured the detector, not the artwork.
        clip = pymupdf.Rect(box.x0-8, box.y0-8, box.x1+8, box.y1+8)
        pg_.get_pixmap(dpi=300, clip=clip).save(str(WORK / "_qr.png"))
        val, _, _ = det.detectAndDecode(cv2.imread(str(WORK / "_qr.png")))
        check(f"[{name}] QR decodes to the live URL", val == TARGET, repr(val))
    d.close()

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
