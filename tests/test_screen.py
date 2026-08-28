"""Screen-side assertions for the CV page.

Standalone script — `python tests/test_screen.py`. CI runs it from
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
from PIL import Image
from playwright.sync_api import sync_playwright

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "  -> " + str(extra)))
    if not cond: fails.append(name)

with sync_playwright() as p:
    b = launch(p)
    pg = b.new_page(viewport={"width":1280,"height":900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console."+m.type+": "+m.text)
       if m.type=="error" and "fonts.googleapis" not in m.text and "ERR_CONNECTION" not in m.text else None)
    pg.goto(URL)
    pg.wait_for_timeout(900)
    pg.evaluate("setLang('sv')")   # headless locale is en-US; pin it so labels are deterministic
    pg.wait_for_timeout(300)

    check("no JS errors on load", not errors, errors)

    # --- carousel: 4 images + 4 dots, aria-current on active ---
    check("4 portrait images", pg.locator(".portrait-img").count()==4)
    check("4 portrait dots", pg.locator(".portrait-dot").count()==4)
    check("dots are role=group not tablist",
          pg.locator(".portrait-dots").get_attribute("role")=="group")
    check("exactly one aria-current dot",
          pg.locator(".portrait-dot[aria-current='true']").count()==1)
    check("portrait-4 loads (naturalWidth>0)",
          pg.eval_on_selector("img[src='img/portrait-4.jpg']","e=>e.naturalWidth")>0)

    # --- grain ---
    check("grain layer present & non-interactive",
          pg.eval_on_selector(".grain","e=>getComputedStyle(e).pointerEvents")=="none")

    # --- section readout ---
    ro = pg.locator("#brand-readout")
    check("readout starts at CV / 2026", ro.inner_text().strip()=="CV / 2026", ro.inner_text())
    pg.evaluate("document.querySelector('#projects').scrollIntoView({behavior:'instant'})")
    pg.wait_for_timeout(600)
    txt = ro.inner_text()
    check("readout tracks section on scroll", txt.strip().startswith("02"), txt)
    check("readout uses the active language (sv)", "PROJEKT" in txt.upper(), txt)

    # --- aurora idles offscreen ---
    check("aurora paused when hero offscreen",
          pg.evaluate("document.body.classList.contains('aurora-idle')"))
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})"); pg.wait_for_timeout(600)
    check("aurora resumes at top",
          not pg.evaluate("document.body.classList.contains('aurora-idle')"))

    # --- language toggle updates readout ---
    pg.evaluate("document.querySelector('#projects').scrollIntoView({behavior:'instant'})")
    pg.wait_for_timeout(500)
    pg.click("#btn-en"); pg.wait_for_timeout(500)
    check("readout follows language switch", "PROJECTS" in ro.inner_text().upper(), ro.inner_text())
    pg.click("#btn-sv"); pg.wait_for_timeout(400)

    # --- command palette ---
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(400)
    check("palette opens on Ctrl+K", pg.locator("#cmdk").is_visible())
    n_all = pg.locator(".cmdk-item").count()
    check("palette lists items", n_all >= 8, n_all)
    check("first item preselected",
          pg.locator(".cmdk-item[aria-selected='true']").count()==1)
    check("groups rendered", pg.locator(".cmdk-group").count()>=2)

    # diacritic-folded search: "sprak" must find "Språk & intressen"
    pg.fill("#cmdk-input","sprak"); pg.wait_for_timeout(300)
    txt = pg.locator(".cmdk-item .cmdk-label").first.inner_text()
    check("diacritic-insensitive search ('sprak' -> Språk)", "Spr" in txt, txt)

    # subsequence search
    pg.fill("#cmdk-input","nol"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("subsequence match finds Nexus Options Lab",
          any("Nexus" in l for l in labels), labels)

    # no matches
    pg.fill("#cmdk-input","zzzzqqq"); pg.wait_for_timeout(300)
    check("empty state shown", pg.locator(".cmdk-empty").count()==1)

    # arrow nav + enter navigates
    pg.fill("#cmdk-input","kompetens"); pg.wait_for_timeout(300)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
    check("palette closed after Enter", not pg.locator("#cmdk").is_visible())
    check("Enter navigated to #skills",
          pg.evaluate("Math.abs(document.querySelector('#skills').getBoundingClientRect().top) < 120"),
          pg.evaluate("document.querySelector('#skills').getBoundingClientRect().top"))
    check("body scroll lock released",
          pg.evaluate("document.body.style.overflow")=="" )

    # escape closes
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(300)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    check("Escape closes palette", not pg.locator("#cmdk").is_visible())

    # "/" opens
    pg.keyboard.press("/"); pg.wait_for_timeout(300)
    check("'/' opens palette", pg.locator("#cmdk").is_visible())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

    # contact-gated items: locked before verify
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("vCard hidden before verification",
          not any("kontaktkort" in l.lower() for l in labels), labels)
    check("'show contact' offered before verification",
          any("e-post" in l.lower() for l in labels), labels)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

    # verify contact, then re-check palette
    pg.evaluate("revealContact()"); pg.wait_for_timeout(300)
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("vCard offered after verification",
          any("kontaktkort" in l.lower() for l in labels), labels)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)


    # --- organisation marks & links ---
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})"); pg.wait_for_timeout(300)
    check("8 org marks rendered (2 Dios + 3 MO + IG + RMC + MA)", pg.locator(".org-mark").count()==8,
          pg.locator(".org-mark").count())
    check("marks hidden from assistive tech",
          pg.locator(".org-mark[aria-hidden='true']").count()==pg.locator(".org-mark").count())
    hrefs = pg.eval_on_selector_all("a.org-row","els=>els.map(e=>e.getAttribute('href'))")
    import collections
    want = {"https://www.dios.se":2, "https://www.morningstar.com":3,
            "https://www.ig.com":1, "https://rocky.edu":1,
            "https://www.skidgymnasiet.se/":1}
    check("org links point at the verified domains",
          collections.Counter(hrefs)==collections.Counter(want), hrefs)
    check("every org link opens safely (rel=noopener)",
          pg.eval_on_selector_all("a.org-row","els=>els.every(e=>(e.rel||'').includes('noopener'))"))
    check("every org row is now a link (no unlinked spans left)",
          pg.eval_on_selector_all(".org-row","els=>els.filter(e=>e.tagName==='SPAN').length")==0)
    check("Malung links to the RIG Alpint programme",
          pg.locator("a.org-row[href='https://www.skidgymnasiet.se/']").count()==1)
    check("link text is the org name (accessible name)",
          "Rocky Mountain College" in pg.locator("a.org-row[href='https://rocky.edu']").inner_text())
    # marks must not knock the timeline dots out of alignment
    check("timeline dot still aligns with first job",
          pg.evaluate("""(()=>{const j=document.querySelector('.job');
             const s=getComputedStyle(j,'::after');return s.top==='6px';})()"""))


    # --- starfield ---
    check("3 star layers", pg.locator(".stars").count()==3)
    check("starfield sits behind content and takes no clicks",
          pg.eval_on_selector(".starfield","e=>getComputedStyle(e).pointerEvents")=="none"
          and pg.eval_on_selector(".starfield","e=>getComputedStyle(e).zIndex")=="-1")
    # each layer must overhang by exactly one tile so the drift loop closes seamlessly
    seam = pg.evaluate("""[...document.querySelectorAll('.stars')].map(e=>{
        const tile=parseFloat(getComputedStyle(e).backgroundSize);
        return Math.abs(tile-(e.getBoundingClientRect().height-innerHeight))<1;})""")
    check("every layer loops seamlessly (overhang == tile)", all(seam), seam)
    check("clicking through the starfield reaches real content",
          "star" not in str(pg.evaluate("document.elementFromPoint(640,450).className")))
    # PROOF the stars actually paint rather than hiding behind the body background
    pg.evaluate("window.scrollTo({top:2600,behavior:'instant'})"); pg.wait_for_timeout(700)
    pg.screenshot(path=str(WORK / "_startest.png"))
    im = Image.open(str(WORK / "_startest.png")).convert("RGB")
    gut = [im.getpixel((x,y)) for x in range(4,120) for y in range(120,760)]
    bright = max(sum(q) for q in gut)
    check("stars render brightly against the void", bright > 300, f"brightest sum={bright}")
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})"); pg.wait_for_timeout(400)


    # --- PDF download button & short-print variant ---
    check("download button is a real download link",
          pg.eval_on_selector("#dl-btn","e=>e.tagName==='A' && e.hasAttribute('download')"))
    check("download href follows the active language (sv)",
          pg.eval_on_selector("#dl-btn","e=>e.getAttribute('href')")=="pdf/anton-alin-cv-sv.pdf",
          pg.eval_on_selector("#dl-btn","e=>e.getAttribute('href')"))
    pg.click("#btn-en"); pg.wait_for_timeout(300)
    check("download href follows the active language (en)",
          pg.eval_on_selector("#dl-btn","e=>e.getAttribute('href')")=="pdf/anton-alin-cv-en.pdf",
          pg.eval_on_selector("#dl-btn","e=>e.getAttribute('href')"))
    pg.click("#btn-sv"); pg.wait_for_timeout(300)

    pg.keyboard.press("Control+k"); pg.wait_for_timeout(400)
    pg.fill("#cmdk-input",""); pg.wait_for_timeout(300)
    labels = " | ".join(pg.locator(".cmdk-item .cmdk-label").all_inner_texts()).lower()
    for want in ["ladda ner cv (2 sidor)", "ladda ner cv (1 sida)",
                 "skriv ut / spara som pdf", "skriv ut kortversionen"]:
        check(f"palette offers {want!r}", want in labels, labels[:180])
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

    # The short sheet is the same DOM with sections withheld by a body class.
    pg.emulate_media(media="print")
    pg.evaluate("document.body.classList.add('print-short')"); pg.wait_for_timeout(300)
    hidden = pg.evaluate("""['#projects','#achievements','#misc']
        .map(s=>getComputedStyle(document.querySelector(s)).display)""")
    check("short variant withholds projects/achievements/interests",
          all(d=="none" for d in hidden), hidden)
    # getComputedStyle reports the unresolved counter() function, so the real
    # renumbering assertion lives in test_print.py against the rendered PDF.
    check("short variant drives section numbers from a counter",
          "counter(sec" in pg.evaluate("""getComputedStyle(
             document.querySelector('main section .section-num'),'::before').content"""))
    pg.evaluate("document.body.classList.remove('print-short')")
    pg.emulate_media(media="screen"); pg.wait_for_timeout(200)
    check("short-print class leaves no trace on screen",
          not pg.evaluate("document.body.classList.contains('print-short')"))


    # --- The menu trigger must survive on a device with no keyboard ---
    # Hiding it there once made the whole menu — sections, both PDF downloads,
    # the contact reveal — unreachable on a phone.
    tctx = b.new_context(viewport={"width":390,"height":844}, has_touch=True, is_mobile=True)
    tpg = tctx.new_page(); tpg.goto(URL); tpg.wait_for_timeout(1000)
    tpg.evaluate("setLang('sv')"); tpg.wait_for_timeout(300)
    check("touch: menu trigger is reachable",
          tpg.eval_on_selector("#cmdk-hint","e=>getComputedStyle(e).display!=='none'"))
    check("touch: the keycap is dropped, not the button",
          tpg.eval_on_selector("#cmdk-key","e=>getComputedStyle(e).display")=="none")
    check("touch: trigger still names itself for assistive tech",
          tpg.get_by_role("button", name="Meny", exact=True).count()==1)
    tpg.evaluate("setLang('en')"); tpg.wait_for_timeout(300)
    check("touch: accessible name follows the language",
          tpg.get_by_role("button", name="Menu", exact=True).count()==1
          and tpg.get_by_role("button", name="Meny", exact=True).count()==0)
    tpg.evaluate("setLang('sv')"); tpg.wait_for_timeout(300)
    tpg.click("#cmdk-hint"); tpg.wait_for_timeout(500)
    check("touch: tapping it opens the full menu",
          tpg.locator("#cmdk").is_visible() and tpg.locator(".cmdk-item").count() >= 12,
          tpg.locator(".cmdk-item").count())
    check("touch: no horizontal overflow at 390px",
          tpg.evaluate("window.scrollX")==0)
    tctx.close()


    # --- polish pass: meteor, spinning ring, fading rules, text-wrap ---
    check("meteor element lives inside the starfield",
          pg.locator(".starfield .meteor").count()==1)
    check("meteor takes no clicks",
          pg.eval_on_selector(".meteor","e=>getComputedStyle(e).pointerEvents")=="none")
    check("portrait ring spins",
          "ring-spin" in pg.eval_on_selector(".portrait-ring","e=>getComputedStyle(e).animationName"))
    check("section rules fade out instead of stopping dead",
          "gradient" in pg.eval_on_selector(".section-line","e=>getComputedStyle(e).backgroundImage"))
    check("headings balance their line breaks",
          pg.eval_on_selector(".section-title",
            "e=>{const s=getComputedStyle(e);return s.textWrapStyle||s.textWrap;}")=="balance",
          pg.eval_on_selector(".section-title",
            "e=>{const s=getComputedStyle(e);return s.textWrapStyle||s.textWrap;}"))


    # --- job durations, constellation, parallax ---
    check("all six dated roles carry a computed duration",
          pg.locator(".job-dur").count()==6, pg.locator(".job-dur").count())
    durs = pg.eval_on_selector_all(".job-dur","els=>els.map(e=>e.textContent)")
    # Fixed historical ranges are deterministic: inclusive LinkedIn-style count.
    check("NOV 2021 - SEP 2024 reads 2 år 11 mån", "2 år 11 mån" in durs, durs)
    check("JAN 2015 - OKT 2016 reads 1 år 10 mån", "1 år 10 mån" in durs, durs)
    # The open-ended role must match the same formula evaluated now.
    import datetime as _dt
    _n=_dt.date.today(); _m=(_n.year-2025)*12+(_n.month-4)+1
    _y,_r=divmod(_m,12); _want=(f"{_y} år {_r} mån" if _y and _r else f"{_y} år" if _y else f"{_r} mån")
    check("current role duration tracks today's date", _want in durs, (durs,_want))
    pg.click("#btn-en"); pg.wait_for_timeout(300)
    dure = pg.eval_on_selector_all(".job-dur","els=>els.map(e=>e.textContent)")
    check("durations follow the language (yrs/mos)",
          any("yr" in d for d in dure) and not any("år" in d for d in dure), dure)
    pg.click("#btn-sv"); pg.wait_for_timeout(300)

    check("four constellations on the page",
          pg.locator(".constellation").count()==4, pg.locator(".constellation").count())
    check("Karlavagnen has its seven stars",
          pg.locator(".const-plough circle").count()==7)
    check("Cassiopeja is the five-star W",
          pg.locator(".const-cas circle").count()==5)
    check("Orion has shoulders, belt and feet",
          pg.locator(".const-orion circle").count()==7)
    check("Svanen forms the northern cross",
          pg.locator(".const-cygnus circle").count()==5)
    check("all constellations are decorative and non-interactive",
          pg.eval_on_selector_all(".constellation",
            "els=>els.every(e=>e.getAttribute('aria-hidden')==='true' "
            +"&& getComputedStyle(e).pointerEvents==='none')"))
    check("the hero one lights on load",
          pg.eval_on_selector(".const-plough","e=>e.classList.contains('is-lit')"))
    check("section constellations hide where there is no gutter (1280px)",
          pg.eval_on_selector(".const-cygnus","e=>getComputedStyle(e).display")=="none")
    # They need a wide viewport to exist at all, so the lighting behaviour and
    # the clearance from the text column are both checked there.
    wctx = b.new_context(viewport={"width":1600,"height":900})
    wpg = wctx.new_page(); wpg.goto(URL); wpg.wait_for_timeout(1000)
    wpg.evaluate("setLang('sv')"); wpg.wait_for_timeout(300)
    check("wide: a lower constellation waits to be scrolled to",
          not wpg.eval_on_selector(".const-cygnus","e=>e.classList.contains('is-lit')"))
    wpg.evaluate("document.querySelector('#achievements').scrollIntoView({behavior:'instant'})")
    wpg.wait_for_timeout(900)
    check("wide: it lights once in view",
          wpg.eval_on_selector(".const-cygnus","e=>e.classList.contains('is-lit')"))
    wpg.evaluate("document.querySelector('#education').scrollIntoView({behavior:'instant'})")
    wpg.wait_for_timeout(400)
    clear = wpg.evaluate("""(()=>{const c=document.querySelector('.const-orion').getBoundingClientRect();
        const m=document.querySelector('main').getBoundingClientRect();
        return Math.round(m.left-c.right);})()""")
    check("wide: constellations sit clear of the text column", clear > 0, f"{clear}px")
    check("wide: they cause no horizontal scroll",
          wpg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")==0)
    wctx.close()
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})"); pg.wait_for_timeout(400)
    pg.mouse.move(200,200); pg.wait_for_timeout(250)
    pg.mouse.move(1000,600); pg.wait_for_timeout(250)
    check("pointer parallax moves the aurora",
          "matrix" in pg.eval_on_selector(".aurora-layer","e=>getComputedStyle(e).transform"),
          pg.eval_on_selector(".aurora-layer","e=>getComputedStyle(e).transform"))


    # --- SQL and Python are in the scannable skills list ---
    # innerText breaks between flex items, so read the tags and normalise.
    def tags():
        return [" ".join(t.split()) for t in
                pg.eval_on_selector_all("#skills .skill-tags-icons > span",
                                        "els=>els.map(e=>e.innerText)")]
    tg = tags()
    check("SQL is listed with its level", "SQL — god vana" in tg, tg)
    check("Python is listed with its level", "Python — grundläggande" in tg, tg)
    check("languages lead the tools group", tg[0].startswith("SQL")
          and tg[1].startswith("Python"), tg)
    # A nested qualifier must not render both languages, nor a pill inside a pill.
    check("only one language variant renders",
          not any("proficient" in t for t in tg), tg)
    check("the qualifier is plain text, not a nested pill",
          pg.eval_on_selector("#skills .skill-tags-icons > span .sv-only",
              "e=>getComputedStyle(e).backgroundColor==='rgba(0, 0, 0, 0)' "
              +"&& getComputedStyle(e).borderTopWidth==='0px'"))
    pg.click("#btn-en"); pg.wait_for_timeout(300)
    tge = tags()
    check("levels follow the language",
          "SQL — proficient" in tge and "Python — foundational" in tge
          and not any("god vana" in t for t in tge), tge)
    pg.click("#btn-sv"); pg.wait_for_timeout(300)

    check("no JS errors overall", not errors, errors)

    # --- print rendering still sane ---
    pg.emulate_media(media="print")
    pg.wait_for_timeout(300)
    check("palette hidden in print",
          pg.eval_on_selector("#cmdk","e=>getComputedStyle(e).display")=="none")
    check("starfield hidden in print",
          pg.eval_on_selector(".starfield","e=>getComputedStyle(e).display")=="none")
    check("grain hidden in print",
          pg.eval_on_selector(".grain","e=>getComputedStyle(e).display")=="none")
    check("cmdk hint hidden in print",
          pg.eval_on_selector("#cmdk-hint","e=>getComputedStyle(e).display")=="none")
    check("constellation hidden in print",
          pg.eval_on_selector(".constellation","e=>getComputedStyle(e).display")=="none")
    check("org marks still visible in print",
          pg.eval_on_selector(".org-mark","e=>getComputedStyle(e).display")!="none")
    check("org marks go light-on-white in print",
          pg.eval_on_selector(".org-mark","e=>getComputedStyle(e).backgroundColor")=="rgb(255, 255, 255)",
          pg.eval_on_selector(".org-mark","e=>getComputedStyle(e).backgroundColor"))
    pg.emulate_media(media="screen")

    pg.emulate_media(media="screen", reduced_motion="reduce"); pg.wait_for_timeout(400)
    check("reduced motion stops the drift but keeps the stars",
          pg.eval_on_selector(".stars","e=>getComputedStyle(e).animationName")=="none"
          and pg.eval_on_selector(".starfield","e=>getComputedStyle(e).display")!="none",
          pg.eval_on_selector(".stars","e=>getComputedStyle(e).animationName"))
    check("reduced motion also stills the portrait ring",
          pg.eval_on_selector(".portrait-ring","e=>getComputedStyle(e).animationName")=="none")

    b.close()

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
