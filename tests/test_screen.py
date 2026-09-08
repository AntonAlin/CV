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
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import fontmirror
from playwright.sync_api import sync_playwright

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "  -> " + str(extra)))
    if not cond: fails.append(name)

with sync_playwright() as p:
    b = launch(p)
    pg = b.new_page(viewport={"width":1280,"height":900})
    # The sky asks NOAA for the K-index; serve a fixture so the run is deterministic and offline.
    import json as _json, datetime as _dt
    _now = _dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    KP_FIXTURE = [["time_tag", "kp", "observed", "noaa_scale"]] + [
        [(_now + _dt.timedelta(hours=3 * i)).strftime("%Y-%m-%d %H:%M:%S"), v, "predicted" if i > 0 else "observed", None]
        for i, v in enumerate(["3.00", "4.33", "4.67", "3.33", "2.00", "1.67", "1.33", "1.00", "1.00"])]
    KP_FIXTURE.insert(1, [(_now - _dt.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), "2.33", "observed", None])
    pg.route("**/services.swpc.noaa.gov/**",
             lambda route: route.fulfill(status=200, content_type="application/json", body=_json.dumps(KP_FIXTURE)))
    # Live cards: today's SE2 prices and Åreskutan weather, served from fixtures too.
    _day = _dt.date.today()
    SE2_FIXTURE = [{"SEK_per_kWh": round(0.4 + 0.9 * abs(((h - 18) % 24) - 12) / 12, 4), "EUR_per_kWh": 0.05, "EXR": 11.1,
                    "time_start": f"{_day.isoformat()}T{h:02d}:00:00+02:00", "time_end": f"{_day.isoformat()}T{(h + 1) % 24:02d}:00:00+02:00"}
                   for h in range(24)]
    _hour = _dt.datetime.now().hour
    ARE_FIXTURE = {"current": {"time": f"{_day.isoformat()}T{_hour:02d}:00", "temperature_2m": -1.3, "wind_speed_10m": 9.4, "weather_code": 71,
                               "wind_gusts_10m": 14.1, "wind_direction_10m": 250, "cloud_cover": 100, "rain": 0.0,
                               "snowfall": 0.42, "snow_depth": 0.84},
                   "hourly": {"time": [f"{_day.isoformat()}T{h:02d}:00" for h in range(24)],
                              "temperature_2m": [round(-4 + 5 * (1 - abs(h - 14) / 14), 1) for h in range(24)]}}
    pg.route("**elprisetjustnu.se/**", lambda route: route.fulfill(status=200, content_type="application/json", body=_json.dumps(SE2_FIXTURE)))
    pg.route("**/api.open-meteo.com/**", lambda route: route.fulfill(status=200, content_type="application/json", body=_json.dumps(ARE_FIXTURE)))
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console."+m.type+": "+m.text)
       if m.type=="error" and "fonts.googleapis" not in m.text and "ERR_CONNECTION" not in m.text else None)
    fontmirror.prepare(pg, URL)
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
    check("9 org marks rendered (2 Dios + 3 MO + own account + IG + RMC + MA)", pg.locator(".org-mark").count()==9,
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
    check("every org row is a link, except the own-account row which has no employer",
          pg.eval_on_selector_all(".org-row","els=>els.filter(e=>e.tagName!=='A').map(e=>!!e.closest('.job-self'))")
          == [True])
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
    # PROOF the stars actually paint rather than hiding behind the body background.
    # Forced to night and to reduced motion: day/dawn/dusk dim the stars on
    # purpose (time-of-day mood, below), which would make this measurement
    # flake depending on the wall-clock hour the suite happens to run in, and
    # the dimming is itself a transition that needs motion disabled to land
    # instantly rather than being caught mid-fade.
    orig_tod = [c for c in pg.eval_on_selector("body","e=>e.className").split()
                if c.startswith("tod-")]
    pg.emulate_media(media="screen", reduced_motion="reduce")
    pg.evaluate("""(() => {
        const b = document.body.classList;
        b.remove('tod-day','tod-dusk','tod-night','tod-dawn');
        b.add('tod-night');
        /* Åre's cloud cover veils the stars by design; measure them under a clear sky */
        document.body.style.setProperty('--wx-cloud', '0');
    })()""")
    pg.evaluate("window.scrollTo({top:2600,behavior:'instant'})"); pg.wait_for_timeout(700)
    pg.screenshot(path=str(WORK / "_startest.png"))
    im = Image.open(str(WORK / "_startest.png")).convert("RGB")
    gut = [im.getpixel((x,y)) for x in range(4,120) for y in range(120,760)]
    bright = max(sum(q) for q in gut)
    check("stars render brightly against the void", bright > 300, f"brightest sum={bright}")
    if orig_tod:
        pg.evaluate("""(cls) => {
            const b = document.body.classList;
            b.remove('tod-day','tod-dusk','tod-night','tod-dawn');
            b.add(cls);
        }""", orig_tod[0])
    pg.evaluate("(()=>{const w=cvWx.state(); if(w){document.body.style.setProperty('--wx-cloud', w.cloud.toFixed(2));}})()")
    pg.emulate_media(media="screen", reduced_motion="no-preference")
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
    tpg = tctx.new_page(); fontmirror.prepare(tpg, URL); tpg.wait_for_timeout(1000)
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
    check("all seven dated roles carry a computed duration",
          pg.locator(".job-dur").count()==7, pg.locator(".job-dur").count())
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
    wpg = wctx.new_page(); fontmirror.prepare(wpg, URL); wpg.wait_for_timeout(1000)
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
    check("Python is listed with its level", "Python — tillämpad (ML & prognoser)" in tg, tg)
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
          "SQL — proficient" in tge and "Python — applied (ML & forecasting)" in tge
          and not any("god vana" in t for t in tge), tge)
    pg.click("#btn-sv"); pg.wait_for_timeout(300)

    pg.goto(URL + "?lang=en"); pg.wait_for_timeout(800)
    check("?lang= in the URL wins over the stored choice",
          pg.eval_on_selector("body", "b=>b.classList.contains('lang-en')"))
    pg.evaluate("setLang('sv')"); pg.wait_for_timeout(300)

    # --- Music: generated, off by default, never autoplays ---
    st = pg.evaluate("cvMusic.state()")
    check("music is off on load and no audio context exists yet",
          st["playing"] is False and st["started"] is False, st)
    check("the music menu starts closed",
          pg.get_attribute("#music-menu", "hidden") is not None
          and pg.get_attribute("#music-btn", "aria-expanded") == "false")
    pg.click("#music-btn"); pg.wait_for_timeout(200)
    check("the note button opens a menu with four genres",
          pg.get_attribute("#music-menu", "hidden") is None
          and pg.locator("#music-menu [data-genre]").count() == 4)
    check("genre descriptions render in one language only",
          "Slow pads" not in pg.locator("#music-menu").inner_text()
          and "Långsamma pads" in pg.locator("#music-menu").inner_text())
    pg.click("#music-menu [data-genre='lofi']"); pg.wait_for_timeout(400)
    st = pg.evaluate("cvMusic.state()")
    check("choosing Lo-fi starts it", st["playing"] and st["genre"] == "lofi" and st["started"], st)
    check("the bar shows it is playing and the genre is marked",
          pg.eval_on_selector("#music", "e=>e.classList.contains('is-playing')")
          and pg.get_attribute("#music-menu [data-genre='lofi']", "aria-pressed") == "true"
          and not pg.eval_on_selector("#music-stop", "e=>e.disabled"))
    pg.click("#music-menu [data-genre='synthwave']"); pg.wait_for_timeout(300)
    st = pg.evaluate("cvMusic.state()")
    check("switching genre keeps playing", st["playing"] and st["genre"] == "synthwave", st)
    # Every piece must actually reach the output, not just flip a flag.
    levels = {}
    for g in ("synthwave", "ambient", "piano", "lofi"):
        pg.evaluate(f"cvMusic.play('{g}')"); pg.wait_for_timeout(1500)
        levels[g] = max(pg.evaluate("cvMusic.state().level") for _ in range(5))
    check("all four genres produce sound (audio context running)",
          pg.evaluate("cvMusic.state().ctx") == "running" and all(v > 0.003 for v in levels.values()),
          {k: round(v, 4) for k, v in levels.items()})
    pg.click("#music-menu [data-genre='synthwave']"); pg.wait_for_timeout(200)
    pg.evaluate("cvMusic.volume(0.3)")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
    check("Escape closes the menu", pg.get_attribute("#music-menu", "hidden") is not None)
    pg.click("#cmdk-hint"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("the palette has one music row that names what is playing",
          labels.count("Musik") == 1 and not any(l.startswith("Spela: ") and l[7:] in ("Ambient", "Lo-fi", "Synthwave", "Piano") for l in labels)
          and "Synthwave" in pg.locator(".cmdk-item", has_text="Musik").first.inner_text(), labels)
    pg.locator(".cmdk-item", has_text="Musik").first.click(); pg.wait_for_timeout(300)
    check("choosing it opens the music menu", pg.get_attribute("#music-menu", "hidden") is None)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.evaluate("cvMusic.stop()"); pg.wait_for_timeout(200)
    check("stop stops", not pg.evaluate("cvMusic.state().playing")
          and not pg.eval_on_selector("#music", "e=>e.classList.contains('is-playing')"))
    pg.reload(); pg.wait_for_timeout(1000)
    st = pg.evaluate("cvMusic.state()")
    check("a return visit remembers the genre and volume but stays silent",
          st["playing"] is False and st["started"] is False
          and st["genre"] == "synthwave" and abs(st["volume"] - 0.3) < .01, st)
    pg.evaluate("setLang('sv')"); pg.wait_for_timeout(300)
    pg.emulate_media(media="print")
    check("the music control stays off paper",
          pg.eval_on_selector("#music", "e=>getComputedStyle(e).display") == "none")
    pg.emulate_media(media="screen")

    # --- Moon and space weather ---
    check("the moon's phase is computed from a real ephemeris",
          pg.evaluate("cvSky.moon(new Date('2000-01-21T04:40:00Z')).fraction") > .98
          and pg.evaluate("cvSky.moon(new Date('2000-01-06T18:14:00Z')).fraction") < .01
          and abs(pg.evaluate("cvSky.moon(new Date('2000-01-14T13:34:00Z')).fraction") - .5) < .07
          and pg.evaluate("cvSky.moon(new Date('2000-01-14T13:34:00Z')).waxing") is True)
    # The moon line belongs to the night; force it for the checks below and restore after
    day_classes = pg.evaluate("[...document.body.classList].filter(c=>c.startsWith('tod-'))")
    pg.evaluate("document.body.classList.remove('tod-day','tod-dusk','tod-dawn','tod-night'); document.body.classList.add('tod-night'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    pg.wait_for_timeout(100)
    check("tonight's moon is drawn with its lit fraction",
          pg.locator("#hero-moon svg path.moon-lit").count() == 1
          and abs(float(pg.get_attribute("#hero-moon", "data-fraction")) - pg.evaluate("cvSky.moon().fraction")) < .01)
    kpst = pg.evaluate("cvSky.kp()")
    check("the K-index forecast is parsed: current now, tonight's peak from the next 24 h",
          kpst and kpst["now"] == 3.0 and abs(kpst["tonight"] - 4.67) < .01, kpst)
    check("an active night strengthens the aurora and the sky line says so",
          pg.evaluate("document.body.classList.contains('kp-quiet')") is False
          and pg.get_attribute("#sky-line", "hidden") is None
          and "Kp 4.7" in pg.locator("#sky-line").inner_text()
          and "goda chanser" in pg.locator("#sky-line").inner_text()
          and "%" in pg.locator("#sky-line").inner_text(), pg.locator("#sky-line").inner_text())
    _recent = (_now - _dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    check("a quiet recent reading parses, a stale or malformed one is rejected",
          pg.evaluate("cvSky.parse([['t','kp','o','s'],['%s','1.0','observed',null]]).tonight" % _recent) == 1.0
          and pg.evaluate("cvSky.parse([{time_tag:'%s',kp:'2.67',observed:'observed',noaa_scale:null},{time_tag:'%s',kp:'5.00',observed:'predicted',noaa_scale:'G1'}]).tonight" % (_recent, (_now + _dt.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"))) == 5.0
          and pg.evaluate("cvSky.parse([['t','kp','o','s'],['2020-01-01 00:00:00','1.0','observed',null]])") is None
          and pg.evaluate("cvSky.parse('nonsense')") is None)
    pg.click("#btn-en"); pg.wait_for_timeout(200)
    check("the sky line follows the language", "Aurora tonight" in pg.locator("#sky-line").inner_text())
    pg.click("#btn-sv"); pg.wait_for_timeout(200)
    pg.emulate_media(media="print")
    check("moon and sky line stay off paper",
          pg.eval_on_selector("#hero-moon", "e=>getComputedStyle(e).display") == "none"
          and pg.eval_on_selector("#sky-line", "e=>getComputedStyle(e).display") == "none")
    pg.emulate_media(media="screen")
    pg.evaluate("document.body.classList.remove('tod-night'); document.body.classList.add('tod-day'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    pg.wait_for_timeout(100)
    check("by day the line keeps the forecast but drops the moon",
          "Kp" in pg.locator("#sky-line").inner_text() and "%" not in pg.locator("#sky-line").inner_text())
    pg.evaluate("document.body.classList.remove('tod-day'); document.body.classList.add(%r); document.dispatchEvent(new CustomEvent('cv:tod'))" % (day_classes[0] if day_classes else "tod-day"))
    # Without the forecast the page must stay quiet and error-free
    fctx = b.new_context(viewport={"width":1280,"height":900}); fpg = fctx.new_page()
    ferr = []; fpg.on("pageerror", lambda e: ferr.append(str(e)))
    fpg.route("**/services.swpc.noaa.gov/**", lambda route: route.abort())
    fpg.route("**elprisetjustnu.se/**", lambda route: route.abort())
    fpg.route("**/api.open-meteo.com/**", lambda route: route.abort())
    fontmirror.prepare(fpg, URL); fpg.wait_for_timeout(900)
    check("offline, the live cards keep their drawings and stay quiet",
          fpg.locator(".project-card.has-live").count() == 0
          and fpg.locator('[data-live="se2"] .live-note').get_attribute("hidden") is not None
          and fpg.locator('[data-live="se2"] .project-chart.is-static').evaluate("e=>getComputedStyle(e).display") == "block")
    fpg.evaluate("document.body.classList.remove('tod-day','tod-dusk','tod-dawn'); document.body.classList.add('tod-night'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    fpg.wait_for_timeout(100)
    check("no forecast: the moon still shows at night, the aurora keeps its default, no errors",
          fpg.evaluate("cvSky.kp()") is None and fpg.get_attribute("#sky-line", "hidden") is None
          and "Kp" not in fpg.locator("#sky-line").inner_text() and "%" in fpg.locator("#sky-line").inner_text()
          and not any(c in fpg.evaluate("document.body.className") for c in ("kp-quiet", "kp-active", "kp-storm"))
          and not ferr, ferr)
    fpg.evaluate("document.body.classList.remove('tod-night'); document.body.classList.add('tod-day'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    fpg.wait_for_timeout(100)
    check("no forecast by day: the line stays hidden", fpg.get_attribute("#sky-line", "hidden") is not None)
    fctx.close()

    # --- Live cards ---
    lv = pg.evaluate("cvLive.state()")
    se2c = pg.locator('[data-live="se2"]'); arec = pg.locator('[data-live="are"]')
    check("the SE2 card draws today's real price curve with the current hour marked",
          lv["se2"] and lv["se2"]["n"] == 24 and se2c.locator(".project-chart.is-live circle.live-now").count() == 1
          and se2c.evaluate("e=>e.classList.contains('has-live')")
          and "kr/kWh" in se2c.locator(".live-note").inner_text() and "topp" in se2c.locator(".live-note").inner_text(),
          lv["se2"] and {k: lv["se2"][k] for k in ("n", "cur", "max")})
    check("the drawn SE2 chart yields to the live one on screen",
          se2c.locator(".project-chart.is-static").evaluate("e=>getComputedStyle(e).display") == "none")
    check("the ÅreWeather card reads Åreskutan's temperature, wind and sky",
          lv["are"] and lv["are"]["temp"] == -1.3 and lv["are"]["code"] == 71
          and all(w in arec.locator(".live-note").inner_text() for w in ("Åreskutan", "−1,3", "°C", "m/s", "snö"))
          and arec.locator(".project-chart.is-live").count() == 1, arec.locator(".live-note").inner_text())
    check("snow on Åreskutan falls in the hero and is measured in the sky line",
          pg.evaluate("document.body.classList.contains('is-snowing')")
          and pg.locator(".hero .hero-snow i").count() > 20
          and "Snödjup Åreskutan" in pg.locator("#sky-line").inner_text()
          and "84\xa0cm" in pg.locator("#sky-line").inner_text()
          and "snöar nu" in pg.locator("#sky-line").inner_text(), pg.locator("#sky-line").inner_text())
    # --- Åre's weather paints the sky ---
    # Pin the hour: the deck colours and cloud tints differ by phase, and the
    # suite runs at all times of day
    pg.evaluate("document.body.classList.remove('tod-dusk','tod-dawn','tod-night'); document.body.classList.add('tod-day'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    FIX = {"temp": -1.3, "wind": 9.4, "gust": 14.1, "dir": 250, "code": 71, "cloud": 100, "rain": 0, "snowfall": 0.42, "snowDepth": 0.84}
    wx = pg.evaluate("cvWx.state()")
    aur = lambda: float(pg.eval_on_selector(".aurora-layer", "e=>getComputedStyle(e).opacity"))
    deck = lambda: float(pg.eval_on_selector(".hero-deck", "e=>getComputedStyle(e).opacity"))
    check("the report classifies as an overcast, snowing sky and the body carries it",
          wx and wx["sky"] == "overcast" and wx["kind"] == "snow" and wx["cloud"] == 1 and not wx["blizzard"]
          and all(c in pg.evaluate("document.body.className").split() for c in ("has-wx", "wx-overcast", "wx-snow"))
          and pg.evaluate("getComputedStyle(document.body).getPropertyValue('--wx-cloud').trim()") == "1", wx)
    pg.wait_for_timeout(2900)   # the registered property eases over 2.6 s
    check("overcast hides the aurora and stars almost entirely, and lays a cloud deck",
          aur() < 0.05 and deck() > 0.95
          and float(pg.eval_on_selector(".stars-far", "e=>getComputedStyle(e).opacity")) < 0.2, (aur(), deck()))
    check("the sky line opens with Åre right now: temperature, snowfall and wind",
          all(w in pg.locator("#sky-line").inner_text() for w in ("Åreskutan 1\xa0420 m", "just nu", "\u22121,3\xa0°C", "snöfall", "9\xa0m/s", "Modellvärde", "Open-Meteo")),
          pg.locator("#sky-line").inner_text())
    pg.evaluate("cvWx.apply({temp: 11.2, wind: 2, gust: 3, dir: 90, code: 0, cloud: 4, rain: 0, snowfall: 0})"); pg.wait_for_timeout(2900)
    check("a clear sky brings the aurora and stars back and removes the snow",
          "wx-clear" in pg.evaluate("document.body.className") and aur() > 0.5 and deck() < 0.02
          and pg.locator(".hero .hero-snow").count() == 0
          and "klart" in pg.locator("#sky-line").inner_text() and "11,2" in pg.locator("#sky-line").inner_text(), (aur(), deck()))
    pg.evaluate("cvWx.apply({temp: -8, wind: 16, gust: 24, dir: 270, code: 75, cloud: 100, rain: 0, snowfall: 3.1})"); pg.wait_for_timeout(200)
    st = pg.evaluate("cvWx.state()")
    check("a blizzard: wind-leaning heavy snow, a whitened deck and its own word",
          st["blizzard"] and "wx-blizzard" in pg.evaluate("document.body.className")
          and pg.locator(".hero .hero-snow i").count() >= 150
          and pg.evaluate("parseFloat(getComputedStyle(document.body).getPropertyValue('--wx-tilt'))") >= 20
          and "snöstorm" in pg.locator("#sky-line").inner_text()
          and pg.evaluate("getComputedStyle(document.body).getPropertyValue('--wx-deck-1').trim()").startswith("rgba(206"), st)
    pg.evaluate("cvWx.apply({temp: 6, wind: 6, gust: 9, dir: 200, code: 63, cloud: 92, rain: 2.4, snowfall: 0})"); pg.wait_for_timeout(200)
    check("rain: streaks instead of flakes",
          "wx-rain" in pg.evaluate("document.body.className") and pg.locator(".hero .hero-rain i").count() >= 80
          and pg.locator(".hero .hero-snow").count() == 0 and "regn" in pg.locator("#sky-line").inner_text())
    pg.evaluate("cvWx.apply({temp: 2, wind: 1, gust: 2, dir: 10, code: 45, cloud: 100, rain: 0, snowfall: 0})"); pg.wait_for_timeout(200)
    check("fog: three drifting banks", "wx-fog" in pg.evaluate("document.body.className")
          and pg.locator(".hero .hero-fog i").count() == 3 and pg.locator(".hero .hero-rain").count() == 0
          and "dimma" in pg.locator("#sky-line").inner_text())
    pg.evaluate("cvWx.apply({temp: 18, wind: 4, gust: 12, dir: 180, code: 95, cloud: 80, rain: 5, snowfall: 0})"); pg.wait_for_timeout(200)
    check("thunder: the flash layer animates over heavy rain",
          "wx-thunder" in pg.evaluate("document.body.className")
          and pg.eval_on_selector(".hero-flash", "e=>getComputedStyle(e).animationName") == "wx-flash"
          and pg.locator(".hero .hero-rain i").count() >= 140 and "åska" in pg.locator("#sky-line").inner_text())
    pg.evaluate("cvWx.apply({temp: 3, wind: 2, gust: 3, dir: 10, code: 3, cloud: 100, rain: 0, snowfall: 0})")
    pg.evaluate("document.body.classList.remove('tod-day','tod-dusk','tod-dawn'); document.body.classList.add('tod-night'); document.dispatchEvent(new CustomEvent('cv:tod'))"); pg.wait_for_timeout(200)
    pg.wait_for_timeout(2800)   # clouds fade over 2.6 s
    check("an overcast night says so next to the aurora forecast, under night-tinted clouds",
          "mulet i Åre just nu" in pg.locator("#sky-line").inner_text()
          and pg.eval_on_selector(".hero-cloud.c1", "e=>String(Math.round(parseFloat(getComputedStyle(e).opacity)*100)/100)") == "0.32", pg.locator("#sky-line").inner_text())
    pg.evaluate("document.body.classList.remove('tod-night'); document.body.classList.add('tod-day'); document.dispatchEvent(new CustomEvent('cv:tod'))")
    pg.evaluate("cvWx.apply({temp: 9, wind: 3, gust: 5, dir: 10, code: 2, cloud: 40, rain: 0, snowfall: 0})"); pg.wait_for_timeout(200)
    pg.wait_for_timeout(2800)   # clouds fade over 2.6 s
    ops = [pg.eval_on_selector(".hero-cloud.c%d" % i, "e=>String(Math.round(parseFloat(getComputedStyle(e).opacity)*100)/100)") for i in (1, 2, 3, 4, 5)]
    check("partly cloudy by day shows the two far clouds, not all five", ops == ["0", "0", "0.9", "0", "0.9"], ops)
    check("the badge sits in the hero's top-right, above the portrait and clear of the bar",
          pg.evaluate("(()=>{const b=document.getElementById('sky-line').getBoundingClientRect(), p=document.querySelector('.portrait-frame').getBoundingClientRect(), bar=document.querySelector('.controlbar').getBoundingClientRect(), w=document.querySelector('.hero-content').getBoundingClientRect(); return b.top>=bar.bottom && b.bottom<=p.top+2 && Math.abs(b.right-w.right)<30 && b.width<=270;})()"),
          pg.evaluate("(()=>{const b=document.getElementById('sky-line').getBoundingClientRect(); return [b.top,b.bottom,b.right,b.width];})()"))
    check("the badge carries an icon, a big temperature and a caption",
          pg.locator("#sky-line .wx-ico svg").count() == 1 and pg.locator("#sky-line .wx-temp").count() == 1
          and float(pg.eval_on_selector("#sky-line .wx-temp", "e=>parseFloat(getComputedStyle(e).fontSize)")) >= 18
          and pg.locator("#sky-line .wx-cap").inner_text() == "Åreskutan 1\xa0420 m · just nu"
          and pg.locator("#sky-line .wx-src").count() == 1)
    sunpos = pg.evaluate("[getComputedStyle(document.body).getPropertyValue('--sun-x').trim(), getComputedStyle(document.body).getPropertyValue('--sun-y').trim(), cvTod.sun(new Date('2026-06-21T02:00:00Z')).az, cvTod.sun(new Date('2026-06-21T11:08:00Z')).az, cvTod.sun(new Date('2026-06-21T19:00:00Z')).az]")
    check("the sun is placed by Åre's real azimuth: east in the morning, south at noon, west in the evening",
          sunpos[0].endswith("%") and sunpos[1].endswith("%") and 25 < sunpos[2] < 100 and 170 < sunpos[3] < 190 and 260 < sunpos[4] < 330, sunpos)
    check("thunder also draws a bolt, a blizzard also blows gusts",
          pg.evaluate("(()=>{cvWx.apply({temp:18,wind:4,gust:12,dir:180,code:95,cloud:80,rain:5,snowfall:0}); const b=document.querySelector('.hero .hero-bolt svg path'); cvWx.apply({temp:-8,wind:16,gust:24,dir:270,code:75,cloud:100,rain:0,snowfall:3.1}); const g=document.querySelectorAll('.hero .hero-gust i').length; return !!b && g>=5 && !document.querySelector('.hero .hero-bolt');})()"))
    cl = pg.evaluate("[cvWx.classify({code:71, wind:3}).blizzard, cvWx.classify({code:71, wind:11}).blizzard, cvWx.classify({code:2}).sky, cvWx.classify({code:0, cloud:60}).sky, cvWx.classify({code:61, rain:0.2}).rate, cvWx.classify({code:53}).drizzle]")
    check("the classifier: wind makes a blizzard, cover beats the code, drizzle is drizzle", cl == [False, True, "partly", "cloudy", 1, True], cl)
    pg.evaluate("cvWx.apply(" + _json.dumps(FIX) + ")"); pg.wait_for_timeout(200)
    pg.emulate_media(media="print")
    check("no weather layers on paper", all(pg.eval_on_selector(sel, "e=>getComputedStyle(e).display") == "none" for sel in (".hero-deck", ".hero-flash")))
    pg.emulate_media(media="screen")
    pg.emulate_media(media="print")
    check("no snow on paper", pg.eval_on_selector(".hero-snow", "e=>getComputedStyle(e).display") == "none")
    pg.emulate_media(media="screen")
    pg.click("#btn-en"); pg.wait_for_timeout(200)
    check("live notes follow the language",
          "SE2 now" in se2c.locator(".live-note").inner_text() and "snow" in arec.locator(".live-note").inner_text())
    pg.click("#btn-sv"); pg.wait_for_timeout(200)
    mcc = pg.locator("[data-mc]")
    mcc.scroll_into_view_if_needed(); pg.wait_for_timeout(900)
    lv = pg.evaluate("cvLive.state()")
    check("the Monte Carlo card simulates paths on a canvas once in view",
          mcc.evaluate("e=>e.classList.contains('has-mc')") and lv["mc"] and lv["mc"]["step"] > 0 and lv["mc"]["paths"] == 60
          and 0 <= lv["mc"]["up"] <= 1 and "σ" in mcc.locator(".mc-note").inner_text(), lv["mc"])
    box = mcc.locator(".mc-wrap").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2); pg.wait_for_timeout(250)
    check("dragging sideways sets the volatility",
          abs(pg.evaluate("cvLive.state().mc.sigma") - (0.08 + 0.9 * 0.72)) < .03, pg.evaluate("cvLive.state().mc.sigma"))
    pg.emulate_media(media="print")
    check("paper carries no charts at all: neither live curves, notes nor the simulation",
          se2c.locator(".project-chart.is-live").evaluate("e=>getComputedStyle(e).display") == "none"
          and se2c.locator(".live-note").evaluate("e=>getComputedStyle(e).display") == "none"
          and mcc.locator(".mc-wrap").evaluate("e=>getComputedStyle(e).display") == "none"
          and mcc.locator(".project-chart.is-static").evaluate("e=>getComputedStyle(e).display") == "none")
    pg.emulate_media(media="screen")

    # --- Skimo easter egg ---
    check("the race starts hidden", pg.get_attribute("#ski", "hidden") is not None)
    for k in ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"]:
        pg.keyboard.press(k)
    pg.wait_for_timeout(200)
    check("the Konami code opens the race", pg.get_attribute("#ski", "hidden") is None
          and pg.evaluate("cvSki.state().x") == 0 and not pg.evaluate("cvSki.state().running"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
    pg.evaluate("cvSki.open(300)"); pg.wait_for_timeout(100)
    # Hammering is ignored: ten presses 20 ms apart count as about two strokes
    for _ in range(10):
        pg.keyboard.press("Space"); pg.wait_for_timeout(20)
    st = pg.evaluate("cvSki.state()")
    check("the clock starts on the first stroke and hammering the key barely counts",
          st["running"] and st["phase"] == "climb" and st["v"] < 250, st)
    # A rhythm climbs to the summit
    for _ in range(80):
        if pg.evaluate("cvSki.state().phase") == "descent": break
        pg.keyboard.press("Space"); pg.wait_for_timeout(150)
    check("a steady rhythm reaches the summit", pg.evaluate("cvSki.state().phase") == "descent")
    # Downhill: holding the key tucks; gravity does the rest
    pg.keyboard.down("Space"); pg.wait_for_timeout(120)
    check("holding the key on the descent tucks", pg.evaluate("cvSki.state().tuck") is True)
    finished = True
    try:
        pg.wait_for_function("cvSki.state().done", timeout=12000)
    except Exception:
        finished = False
    pg.keyboard.up("Space")
    st = pg.evaluate("cvSki.state()")
    check("the descent ends at the finish flag with the time kept",
          finished and st["done"] and st["x"] == st["len"] and st["elapsed"] > 0 and st["crashes"] >= 0
          and pg.evaluate("+localStorage.getItem('cv-ski-best')") > 0
          and "s" in pg.locator("#ski-best").inner_text().lower(), st)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
    check("Escape closes the race", pg.get_attribute("#ski", "hidden") is not None
          and pg.evaluate("document.body.style.overflow") == "")
    pg.click("#cmdk-hint"); pg.wait_for_timeout(250)
    check("the egg is not listed until searched", "Skimo-loppet (påskägg)" not in pg.locator(".cmdk-item .cmdk-label").all_inner_texts())
    pg.fill("#cmdk-input", "ski"); pg.wait_for_timeout(250)
    check("searching 'ski' finds it", "Skimo-loppet (påskägg)" in pg.locator(".cmdk-item .cmdk-label").all_inner_texts())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

    # --- Guess the company ---
    data = pg.evaluate("cvQuiz.data()")
    check("sixteen companies with long, positive, month-complete series",
          len(data) == 16 and all(len(d["p"]) >= 60 and min(d["p"]) > 0 for d in data)
          and all(len(d["p"]) == (int(d["e"][:4]) - int(d["s"][:4])) * 12 + (int(d["e"][5:7]) - int(d["s"][5:7])) + 1 for d in data),
          [(d["t"], len(d["p"])) for d in data])
    check("the game lives in the bar beside the music, not among the projects",
          pg.locator(".controls #quiz-btn").count() == 1
          and pg.locator(".projects-grid > .project-card").count() == 5
          and pg.eval_on_selector("#quiz-btn", "e=>e.previousElementSibling.id") == "music")
    check("the quiz starts closed", pg.get_attribute("#quiz", "hidden") is not None)
    pg.click("#quiz-btn"); pg.wait_for_timeout(300)
    st = pg.evaluate("cvQuiz.state()")
    check("the bar button opens round one with four names and a chart",
          pg.get_attribute("#quiz", "hidden") is None and st["round"] == 0 and st["score"] == 0
          and pg.locator("#quiz-body .quiz-opts button").count() == 4
          and pg.locator("#quiz-body svg path.quiz-line").count() == 1
          and pg.locator("#quiz-body .quiz-axis").count() >= 2, st)
    check("a time bar counts the bonus down while a round is open",
          pg.locator("#quiz-time-fill").count() == 1
          and pg.locator("#quiz-time-num").inner_text().startswith("+"))
    check("the chart names its scale and its window",
          pg.locator("#quiz-body .quiz-scale").inner_text().lower().split(" · ")[0] in ("logskala", "linjär")
          and " – " in pg.locator("#quiz-body .quiz-scale").inner_text())
    names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts()
    ans = pg.evaluate("cvQuiz.answer()")
    check("the answer is among the four options", any(ans in n for n in names), (ans, names))
    # A wrong answer first, to see it marked and scored
    wrong = next(i for i, n in enumerate(names) if ans not in n)
    pg.locator("#quiz-body .quiz-opts button").nth(wrong).click(); pg.wait_for_timeout(200)
    check("a wrong pick is marked, the right one revealed, no points",
          pg.locator("#quiz-body .quiz-opts button.is-wrong").count() == 1
          and pg.locator("#quiz-body .quiz-opts button.is-right").count() == 1
          and pg.evaluate("cvQuiz.state().score") == 0
          and ans in pg.locator("#quiz-body .quiz-reveal-name").inner_text())
    check("the reveal reports return, CAGR and drawdown",
          all(w in pg.locator("#quiz-body .quiz-stats").inner_text().lower() for w in ("totalavkastning", "cagr", "största nedgång")))
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    check("Enter moves to round two", pg.evaluate("cvQuiz.state().round") == 1
          and pg.locator("#quiz-round").inner_text() == "2")
    # Keyboard answer on round two: find the right key and press it
    names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts(); ans = pg.evaluate("cvQuiz.answer()")
    key = next(i for i, n in enumerate(names) if ans in n) + 1
    pg.keyboard.press(str(key)); pg.wait_for_timeout(200)
    st = pg.evaluate("cvQuiz.state()")
    check("a number key answers; a quick correct pick scores 100 plus a time bonus",
          140 <= st["score"] <= 150 and st["timeBonus"] == st["score"] - 100
          and pg.locator("#quiz-body .quiz-opts button.is-wrong").count() == 0, st)
    check("the reveal itemises right, time and streak",
          all(w in pg.locator("#quiz-body .quiz-hint").inner_text() for w in ("rätt", "tid", "svit")))
    # Play out the rest correctly; the streak bonus should lift the total above 6 x 100
    for _ in range(6):
        pg.keyboard.press("Enter"); pg.wait_for_timeout(120)
        names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts(); ans = pg.evaluate("cvQuiz.answer()")
        pg.keyboard.press(str(next(i for i, n in enumerate(names) if ans in n) + 1)); pg.wait_for_timeout(120)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    st = pg.evaluate("cvQuiz.state()")
    check("eight rounds end on a result screen with a grade and a stored best",
          st["state"] == "final" and st["score"] > 1200
          and pg.locator("#quiz-body .quiz-final-grade").inner_text() != ""
          and pg.evaluate("+localStorage.getItem('cv-quiz-best')") == st["score"], st)
    share = pg.evaluate("cvQuiz.share()")
    check("the result can be shared as a line of squares with the score and the URL",
          share.startswith("Gissa bolaget · " + str(st["score"]) + " p · ") and share.count("\U0001F7E9") == 7
          and share.count("\U0001F7E5") == 1 and share.endswith("https://antonalin.github.io/CV/"), share)
    # Daily round: the same date gives everyone the same eight questions
    # --- Higher or lower? mode ---
    pg.evaluate("cvQuiz.start(false, 'updown')"); pg.wait_for_timeout(300)
    st = pg.evaluate("cvQuiz.state()")
    check("the higher-or-lower mode shows the company, two options, a cut line and a question mark",
          st["mode"] == "updown" and pg.evaluate("cvQuiz.answer()") in ("up", "down")
          and pg.locator("#quiz-body .quiz-opts.is-updown button").count() == 2
          and pg.locator("#quiz-body svg .quiz-cut").count() == 1 and pg.locator("#quiz-body svg .quiz-q").count() == 1
          and pg.locator("#quiz-body svg .quiz-line-next").count() == 0
          and pg.locator("#quiz-body .quiz-ud-name b").count() == 1
          and pg.get_attribute("#quiz-mode", "aria-pressed") == "true"
          and pg.get_attribute("#quiz-title-ud", "hidden") is None and pg.get_attribute("#quiz-title-guess", "hidden") is not None, st)
    ans = pg.evaluate("cvQuiz.answer()")
    pg.keyboard.press("1" if ans == "up" else "2"); pg.wait_for_timeout(300)
    st = pg.evaluate("cvQuiz.state()")
    check("a right up/down call scores, draws the dashed continuation in the matching colour and names the next-12-month return",
          st["answered"] and st["score"] >= 100 and st["marks"] == [True]
          and pg.locator("#quiz-body svg .quiz-line-next.is-" + ans).count() == 1
          and pg.locator("#quiz-body svg .quiz-q").count() == 0
          and pg.locator("#quiz-body .quiz-opts button.is-right").count() == 1
          and "%" in pg.locator("#quiz-body .quiz-stats").inner_text(), st)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    ans = pg.evaluate("cvQuiz.answer()")
    pg.keyboard.press("2" if ans == "up" else "1"); pg.wait_for_timeout(200)
    st = pg.evaluate("cvQuiz.state()")
    check("a wrong call scores nothing and marks the wrong button",
          st["marks"] == [True, False] and st["streak"] == 0
          and pg.locator("#quiz-body .quiz-opts button.is-wrong").count() == 1
          and pg.locator("#quiz-body .quiz-opts button.is-right").count() == 1, st)
    for _ in range(6):
        pg.keyboard.press("Enter"); pg.wait_for_timeout(120)
        a = pg.evaluate("cvQuiz.answer()"); pg.keyboard.press("1" if a == "up" else "2"); pg.wait_for_timeout(120)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    st = pg.evaluate("cvQuiz.state()")
    check("the mode has its own best score and share text",
          st["state"] == "final" and pg.evaluate("+localStorage.getItem('cv-quiz-best-ud')") == st["score"]
          and pg.evaluate("cvQuiz.share()").lower().startswith("upp eller ner?")
          and pg.locator("#quiz-body .quiz-final [data-act='mode']").count() == 1, st)
    pg.click("#quiz-mode"); pg.wait_for_timeout(200)
    check("the header button toggles back to guess-the-company",
          pg.evaluate("cvQuiz.state().mode") == "guess" and pg.locator("#quiz-body .quiz-opts button").count() == 4)

    pg.evaluate("cvQuiz.start(true)"); pg.wait_for_timeout(200)
    first = [pg.evaluate("cvQuiz.answer()")]
    for _ in range(2):
        names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts(); a = pg.evaluate("cvQuiz.answer()")
        pg.keyboard.press(str(next(i for i, n in enumerate(names) if a in n) + 1)); pg.wait_for_timeout(100); pg.keyboard.press("Enter"); pg.wait_for_timeout(100)
        first.append(pg.evaluate("cvQuiz.answer()"))
    pg.evaluate("localStorage.removeItem('cv-quiz-daily')"); pg.evaluate("cvQuiz.start(true)"); pg.wait_for_timeout(200)
    again = [pg.evaluate("cvQuiz.answer()")]
    for _ in range(2):
        names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts(); a = pg.evaluate("cvQuiz.answer()")
        pg.keyboard.press(str(next(i for i, n in enumerate(names) if a in n) + 1)); pg.wait_for_timeout(100); pg.keyboard.press("Enter"); pg.wait_for_timeout(100)
        again.append(pg.evaluate("cvQuiz.answer()"))
    check("the daily round is the same sequence every time that day",
          first == again and pg.get_attribute("#quiz-daily", "aria-pressed") == "true"
          and pg.evaluate("cvQuiz.state().daily") is not None, (first, again))
    for _ in range(6):
        names = pg.locator("#quiz-body .quiz-opts button").all_inner_texts(); a = pg.evaluate("cvQuiz.answer()")
        pg.keyboard.press(str(next(i for i, n in enumerate(names) if a in n) + 1)); pg.wait_for_timeout(100); pg.keyboard.press("Enter"); pg.wait_for_timeout(100)
    daily_score = pg.evaluate("cvQuiz.state().score")
    check("finishing the daily round stores it and numbers the result",
          pg.evaluate("cvQuiz.state().state") == "final" and "#" in pg.evaluate("cvQuiz.share()")
          and pg.evaluate("JSON.parse(localStorage.getItem('cv-quiz-daily')).score") == daily_score)
    pg.evaluate("cvQuiz.start(true)"); pg.wait_for_timeout(200)
    check("a second daily start the same day shows the stored result rather than a new game",
          pg.evaluate("cvQuiz.state().state") == "final" and pg.evaluate("cvQuiz.state().score") == daily_score
          and pg.locator("#quiz-body .quiz-final-daily").count() == 1)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
    check("Escape closes the quiz and unlocks the page",
          pg.get_attribute("#quiz", "hidden") is not None
          and pg.evaluate("document.body.style.overflow") == "")
    pg.click("#cmdk-hint"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("the palette lists the game and the daily round, and leaves the replay to the map",
          "Spela: Gissa bolaget" in labels and "Spela: Dagens omgång" in labels and "Spela: Upp eller ner?" in labels and "Om den här sidan" in labels and "Spela upp karriärkartan" not in labels)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.emulate_media(media="print")
    check("the game button stays off paper and the projects keep their odd-card rule",
          pg.eval_on_selector("#quiz-btn", "e=>getComputedStyle(e).display") == "none"
          and pg.eval_on_selector(".projects-grid > .project-card:last-child",
                                  "e=>getComputedStyle(e).gridColumnStart+'/'+getComputedStyle(e).gridColumnEnd") == "1/-1")
    pg.emulate_media(media="screen")

    check("no JS errors overall", not errors, errors)

    # --- New since your last visit ---
    check("a first visit shows no card and only notes the date",
          pg.locator(".news-card").count() == 0 and pg.evaluate("localStorage.getItem('cv-last-visit')") == pg.evaluate("new Date().toLocaleDateString('sv-SE')"))
    check("nothing is newer than today", pg.evaluate("cvNews.items(new Date().toLocaleDateString('sv-SE')).length") == 0
          and pg.evaluate("cvNews.check()") is False)
    shown = pg.evaluate("cvNews.check('2026-09-06')"); pg.wait_for_timeout(200)
    n = pg.evaluate("cvNews.items('2026-09-06').length")
    check("a reader last here on 6 Sep gets a card listing what came after, at most four rows",
          shown and n >= 4 and pg.locator(".news-card").count() == 1
          and pg.locator(".news-card .news-list li").count() == min(n, 4)
          and "nytt sedan ditt senaste besök" in pg.locator(".news-card").inner_text().lower()
          and "2026-09-06" in pg.locator(".news-card .news-foot").inner_text()
          and pg.locator(".news-card a").count() >= 4)
    check("a reader last here on 7 Sep sees fewer rows than one from 6 Sep",
          pg.evaluate("cvNews.items('2026-09-07').length") < n)
    pg.evaluate("setLang('en')"); pg.wait_for_timeout(150)
    check("the card follows the language", "new since your last visit" in pg.locator(".news-card").inner_text().lower())
    pg.evaluate("setLang('sv')"); pg.wait_for_timeout(150)
    pg.emulate_media(media="print")
    check("the card never prints", pg.evaluate("getComputedStyle(document.querySelector('.news-card')).display") == "none")
    pg.emulate_media(media="screen")
    pg.evaluate("localStorage.setItem('cv-last-visit', '2026-09-06')")
    pg.locator(".news-card .news-close").click(); pg.wait_for_timeout(150)
    check("closing it remembers today's date", pg.locator(".news-card").count() == 0
          and pg.evaluate("localStorage.getItem('cv-last-visit')") == pg.evaluate("new Date().toLocaleDateString('sv-SE')"))
    pg.evaluate("cvNews.check('2026-09-06')"); pg.wait_for_timeout(150)
    pg.locator(".news-card a[data-i]").first.click(); pg.wait_for_timeout(300)
    check("a row's action link runs it and closes the card",
          pg.locator(".news-card").count() == 0 and pg.get_attribute("#quiz", "hidden") is None)
    pg.evaluate("cvQuiz.close()")
    pg.evaluate("cvNews.check('2026-09-06')"); pg.wait_for_timeout(150)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
    check("Escape closes the card", pg.locator(".news-card").count() == 0)

    # --- Daily market strip ---
    MK = {"updated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": [
        {"id": "SPY", "label": "S&P 500", "kind": "etf", "price": 641.87, "chg": 0.00418, "day": "2026-09-08"},
        {"id": "QQQ", "label": "Nasdaq 100", "kind": "etf", "price": 572.4, "chg": -0.00469, "day": "2026-09-08"},
        {"id": "EURSEK", "label": "EUR/SEK", "kind": "fx", "price": 11.045, "chg": 0.00227, "day": "2026-09-08"}]}
    check("the market strip lives in the stock game, not in the CV or its footer",
          pg.locator("#quiz .quiz #market-strip").count() == 1 and pg.locator("footer #market-strip").count() == 0)
    check("the market strip stays hidden from a file:// copy", pg.get_attribute("#market-strip", "hidden") is not None
          and pg.evaluate("cvMarkets.state()") is None)
    ok = pg.evaluate("cvMarkets.render(" + _json.dumps(MK) + ")"); pg.wait_for_timeout(100)
    txt = pg.locator("#market-strip").inner_text()
    check("a fresh file renders a chip per item with a signed one-decimal move and the close date",
          ok and pg.get_attribute("#market-strip", "hidden") is None
          and pg.locator("#market-strip .mk").count() == 3
          and pg.locator("#market-strip .mk[data-id='SPY'] .mk-c.is-up").count() == 1
          and pg.locator("#market-strip .mk[data-id='QQQ'] .mk-c.is-down").count() == 1
          and "641,87" in txt and "11,045" in txt and "+0,4\xa0%" in txt and "\u22120,5\xa0%" in txt
          and "2026-09-08" in txt and "stängning" in txt.lower(), txt)
    pg.evaluate("setLang('en')"); pg.wait_for_timeout(100)
    txt = pg.locator("#market-strip").inner_text()
    check("the strip follows the language", "641.87" in txt and "close" in txt.lower(), txt)
    pg.evaluate("setLang('sv')"); pg.wait_for_timeout(100)
    pg.emulate_media(media="print")
    check("the strip never prints", pg.evaluate("getComputedStyle(document.getElementById('market-strip')).display") == "none")
    pg.emulate_media(media="screen")
    stale = dict(MK, updated="2026-01-05T21:20:00Z")
    check("a stale file hides the strip again",
          pg.evaluate("cvMarkets.render(" + _json.dumps(stale) + ")") is False
          and pg.get_attribute("#market-strip", "hidden") is not None)
    check("a bad file hides it too", pg.evaluate("cvMarkets.render({})") is False)

    # --- About this page ---
    check("the about panel starts closed and has a footer link", pg.get_attribute("#about", "hidden") is not None
          and pg.locator("#footer-about").count() == 1)
    pg.keyboard.press("?"); pg.wait_for_timeout(200)
    check("? opens the about panel with the tech list and the shortcut table",
          pg.get_attribute("#about", "hidden") is None
          and pg.locator("#about .about-grid li").count() >= 5
          and pg.locator("#about .about-keys dt").count() >= 5
          and "kortkommandon" in pg.locator("#about").inner_text().lower()
          and pg.locator("#about a[href='https://github.com/AntonAlin/CV']").count() == 1
          and pg.evaluate("document.body.style.overflow") == "hidden")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
    check("Escape closes it and restores scrolling", pg.get_attribute("#about", "hidden") is not None
          and pg.evaluate("document.body.style.overflow") == "")
    pg.click("#footer-about"); pg.wait_for_timeout(200)
    check("the footer link opens it without following the href",
          pg.get_attribute("#about", "hidden") is None and not pg.url.endswith("#"))
    pg.evaluate("cvAbout.close()")
    pg.evaluate("cvQuiz.open()"); pg.wait_for_timeout(100); pg.keyboard.press("?"); pg.wait_for_timeout(100)
    check("? does nothing while another panel is open", pg.get_attribute("#about", "hidden") is not None)
    pg.evaluate("cvQuiz.close()")
    pg.emulate_media(media="print")
    check("the footer about-link never prints", pg.evaluate("getComputedStyle(document.getElementById('footer-about')).display") == "none")
    pg.emulate_media(media="screen")

    # --- Skills point at their evidence ---
    fabric = pg.locator("#skills .skill-tags > span", has_text="Microsoft Fabric").first
    check("tags with proof in the text are marked clickable with a count, others are not",
          fabric.evaluate("e=>e.classList.contains('has-evidence') && +e.dataset.hits>=3 && e.getAttribute('role')==='button'")
          and not pg.locator("#skills .skill-tags > span", has_text="Pitchbook").first.evaluate("e=>e.classList.contains('has-evidence')"))
    fabric.click(); pg.wait_for_timeout(600)
    check("clicking Fabric lights its bullets, the SE2 card and the current role's bar, and says how many",
          pg.locator("#experience li.is-evidence").count() >= 2
          and pg.locator('[data-live="se2"].is-evidence').count() == 1
          and pg.locator(".career-bar.is-evidence").count() >= 1
          and fabric.get_attribute("aria-pressed") == "true"
          and "träffar" in pg.locator(".evidence-pill").inner_text(), pg.evaluate("cvEvidence.hits()"))
    try:
        pg.wait_for_function("(()=>{const e=document.querySelector('#experience li.is-evidence');if(!e)return false;const r=e.getBoundingClientRect();return r.top>0&&r.bottom<innerHeight;})()", timeout=3000)
        settled = True
    except Exception:
        settled = False
    check("the first hit is scrolled into view", settled)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
    check("Escape clears every mark", pg.evaluate("cvEvidence.hits()") == 0 and pg.locator(".evidence-pill").count() == 0
          and fabric.get_attribute("aria-pressed") == "false")
    fabric.click(); pg.wait_for_timeout(200); fabric.click(); pg.wait_for_timeout(200)
    check("a second click on the same tag clears too", pg.evaluate("cvEvidence.hits()") == 0)
    pg.emulate_media(media="print")
    check("the count never prints", fabric.evaluate("e=>getComputedStyle(e,'::after').content") in ("none", "normal"))
    pg.emulate_media(media="screen")

    # --- Career map ---
    n_roles = pg.locator("#experience .job-period[data-from]").count()
    check("career map draws one bar per dated role",
          pg.locator(".career-bar").count() == n_roles, pg.locator(".career-bar").count())
    check("exactly one bar is the current role", pg.locator(".career-bar.is-current").count() == 1)
    check("the map's employer marks are not counted as org-link marks",
          pg.locator(".career-map .org-mark").count() == 0
          and pg.locator(".career-map .career-mark").count() == 4)
    check("the own-account row is drawn but not counted as an employer",
          "3 arbetsgivare" in pg.locator(".career-map figcaption").inner_text()
          and "Egen räkning" in pg.locator(".career-map").inner_text()
          and "Own account" not in pg.locator(".career-map").inner_text(),
          pg.locator(".career-map figcaption").inner_text())
    bars = pg.eval_on_selector_all(".career-bar",
        "els=>els.map(e=>({w:parseFloat(e.style.width), label:e.getAttribute('aria-label')}))")
    widest = max(bars, key=lambda b: b["w"])
    check("the longest role draws the widest bar", "Content Researcher" in widest["label"], widest)
    cur = [b for b in bars if "NUTID" in b["label"]][0]["label"]
    check("a bar label carries the period once and the duration once",
          cur.count("NUTID") == 1 and cur.count("mån") == 1 and "Diös" in cur, cur)
    cap = pg.locator("#career-map figcaption").inner_text()
    check("map caption counts roles and employers", "7 roller" in cap and "3 arbetsgivare" in cap, cap)
    pg.locator("#career-map").scroll_into_view_if_needed(); pg.wait_for_timeout(1300)
    check("bars draw in once the map is in view",
          pg.eval_on_selector("#career-map", "e=>e.classList.contains('is-lit')")
          and pg.eval_on_selector(".career-bar", "e=>e.getBoundingClientRect().width") > 4)
    pg.click(".career-bar.is-current")
    # Smooth scroll over reveal transitions: wait for the landing rather than a fixed pause.
    landed = True
    try:
        pg.wait_for_function(
            "(()=>{const e=document.querySelector('#experience .job.is-current');const r=e.getBoundingClientRect();"
            +"return r.top>=60&&r.top<220&&e.classList.contains('is-hit');})()", timeout=3000)
    except Exception:
        landed = False
    check("clicking a bar jumps to that role, clear of the sticky bar, and lights it", landed,
          pg.eval_on_selector("#experience .job.is-current","e=>e.getBoundingClientRect().top"))
    # Replay: the bars regrow behind a year cursor, then everything settles back
    pg.evaluate("cvCareer.replay(700)"); pg.wait_for_timeout(350)
    mid = pg.eval_on_selector_all(".career-bar", "els=>els.map(e=>e.style.transform)")
    check("replay sweeps a cursor and grows the bars behind it",
          pg.evaluate("cvCareer.playing()") and pg.locator("#career-map .career-cursor b").count() == 1
          and pg.locator("#career-map .career-cursor b").inner_text().isdigit()
          and any(t.startswith("scaleX(0") for t in mid) and any(t == "scaleX(1)" for t in mid)
          and "Stopp" in pg.locator("#career-map .career-replay").inner_text(), mid)
    pg.wait_for_timeout(1700)
    check("replay ends on its own with the map whole again",
          not pg.evaluate("cvCareer.playing()") and pg.locator("#career-map .career-cursor").count() == 0
          and pg.eval_on_selector_all(".career-bar", "els=>els.every(e=>e.style.transform==='')")
          and "Spela upp" in pg.locator("#career-map .career-replay").inner_text())
    pg.click("#btn-en"); pg.wait_for_timeout(400)
    cap_en = pg.locator("#career-map figcaption").inner_text()
    check("map caption and bar labels follow the language",
          "7 roles" in cap_en and "present" in cap_en
          and "PRESENT" in pg.eval_on_selector(".career-bar.is-current","e=>e.getAttribute('aria-label')"),
          cap_en)
    pg.click("#btn-sv"); pg.wait_for_timeout(400)

    # --- Palette: search inside the text ---
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})"); pg.wait_for_timeout(300)
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(400)
    # Group headers are uppercase via CSS, and innerText honours that.
    def groups():
        return [g.upper() for g in pg.locator(".cmdk-group").all_inner_texts()]
    check("text hits stay hidden until there is a query", "I TEXTEN" not in groups(), groups())
    pg.fill("#cmdk-input", "mifid"); pg.wait_for_timeout(300)
    labels = pg.locator(".cmdk-item .cmdk-label").all_inner_texts()
    check("a term finds the exact bullet it sits in ('mifid' -> MiFID II)",
          any("MiFID" in l for l in labels), labels)
    check("text hits are grouped under 'I texten' and say where they are",
          "I TEXTEN" in groups()
          and any("Morningstar" in m for m in pg.locator(".cmdk-item .cmdk-meta").all_inner_texts()),
          groups())
    # 'mifid' also sits in a skill tag now; choose the Morningstar bullet explicitly.
    pg.locator(".cmdk-item", has_text="MiFID").filter(
        has=pg.locator(".cmdk-meta", has_text="Morningstar")).first.click()
    # A long smooth scroll; wait for the landing rather than guessing its duration.
    landed = True
    try:
        pg.wait_for_function(
            "(()=>{const li=[...document.querySelectorAll('#experience li')]"
            +".find(l=>l.textContent.includes('MiFID'));const r=li.getBoundingClientRect();"
            +"return li.classList.contains('is-hit')&&r.top>0&&r.bottom<innerHeight;})()",
            timeout=3000)
    except Exception:
        landed = False
    check("Enter lands on that line, in view, and lights it",
          landed and not pg.locator("#cmdk").is_visible())
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(300)
    pg.fill("#cmdk-input", "mfd"); pg.wait_for_timeout(300)
    check("body text never matches by subsequence, only by substring",
          not any("MiFID" in l for l in pg.locator(".cmdk-item .cmdk-label").all_inner_texts()))
    pg.fill("#cmdk-input", "fabric"); pg.wait_for_timeout(300)
    check("skill pills are searchable too",
          "Microsoft Fabric" in pg.locator(".cmdk-item .cmdk-label").all_inner_texts())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

    # --- Skip link ---
    # Chromium resumes Tab from wherever focus last was, even after a blur, so
    # "press Tab from the top" is not a thing a test can do. Check the two
    # properties directly: first focusable in the document, and in view once
    # focused.
    pg.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    first = pg.evaluate("document.querySelector('a[href],button,input,[tabindex]:not([tabindex=\"-1\"])')"
                        +".classList.contains('skip-link')")
    pg.evaluate("document.querySelector('.skip-link').focus()")
    # It slides in over 150ms; wait for it to arrive rather than measuring at 0ms.
    arrived = True
    try:
        pg.wait_for_function("document.querySelector('.skip-link').getBoundingClientRect().top >= 0",
                             timeout=2000)
    except Exception:
        arrived = False
    check("the skip link is the first focusable element and comes into view when focused",
          first and arrived, (first, arrived))
    pg.keyboard.press("Enter"); pg.wait_for_timeout(400)
    check("it hands focus to the main content", pg.evaluate("document.activeElement.id==='main'"))

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
    check("career map and skip link are screen-only",
          pg.eval_on_selector("#career-map","e=>getComputedStyle(e).display")=="none"
          and pg.eval_on_selector(".skip-link","e=>getComputedStyle(e).display")=="none")
    pg.emulate_media(media="screen")

    # A request for more contrast gets real hairlines and no grain
    pg.emulate_media(media="screen", contrast="more"); pg.wait_for_timeout(300)
    check("prefers-contrast: more strengthens the hairlines and drops the grain",
          ".24" in pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hairline')")
          and pg.eval_on_selector(".grain","e=>getComputedStyle(e).display")=="none")
    pg.emulate_media(media="screen", contrast="no-preference")

    pg.emulate_media(media="screen", reduced_motion="reduce"); pg.wait_for_timeout(400)
    check("reduced motion stops the drift but keeps the stars",
          pg.eval_on_selector(".stars","e=>getComputedStyle(e).animationName")=="none"
          and pg.eval_on_selector(".starfield","e=>getComputedStyle(e).display")!="none",
          pg.eval_on_selector(".stars","e=>getComputedStyle(e).animationName"))
    check("reduced motion also stills the portrait ring",
          pg.eval_on_selector(".portrait-ring","e=>getComputedStyle(e).animationName")=="none")

    # --- Time-of-day mood ---
    cls_on_load = pg.eval_on_selector("body", "e=>e.className").split()
    check("exactly one time-of-day phase is applied on load",
          len([c for c in cls_on_load if c.startswith("tod-")]) == 1, cls_on_load)
    check("the ambient wash sits inside the starfield",
          pg.locator(".starfield .starfield-glow").count()==1)
    check("one sun and five clouds exist, decorative and inert",
          pg.locator(".hero-sun").count()==1 and pg.locator(".hero-cloud").count()==5
          and pg.eval_on_selector_all(".hero-sun,.hero-cloud",
              "els=>els.every(e=>e.getAttribute('aria-hidden')==='true' "
              +"&& getComputedStyle(e).pointerEvents==='none')"))

    # A fixed clock plus a pinned timezone makes "the visitor's local hour"
    # deterministic to test, rather than depending on when CI happens to run.
    tzctx = b.new_context(timezone_id="UTC")
    # The hour alone must paint these pages: no live Åre report, no forecast
    for _pat in ("**/api.open-meteo.com/**", "**/services.swpc.noaa.gov/**", "**elprisetjustnu.se/**"):
        tzctx.route(_pat, lambda route: route.abort())
    seen = {}
    star_op = {}
    # Åre, 10 January: civil dawn about 07:20Z, sunrise 08:40Z, sunset 13:35Z, dark by 14:55Z.
    for fixed, want in [
        ("2026-01-10T02:00:00Z", "tod-night"),
        ("2026-01-10T08:00:00Z", "tod-dawn"),
        ("2026-01-10T11:00:00Z", "tod-day"),
        ("2026-01-10T14:15:00Z", "tod-dusk"),
    ]:
        tpg = tzctx.new_page()
        tpg.clock.set_fixed_time(fixed)
        fontmirror.prepare(tpg, URL)
        cls = tpg.eval_on_selector("body", "e=>e.className")
        check(f"phase at {fixed} is {want}", want in cls.split(), cls)
        seen[want] = tpg.evaluate(
            "getComputedStyle(document.body).getPropertyValue('--tod-2').trim()")
        tpg.wait_for_timeout(2800)   # the phase eases in over 2.6 s; read the settled value
        star_op[want] = float(tpg.eval_on_selector(".stars-far",
            "e=>getComputedStyle(e).opacity"))
        if want == "tod-day":
            check("the sun is visible by day",
                  float(tpg.eval_on_selector(".hero-sun", "e=>getComputedStyle(e).opacity")) > 0)
            check("the clouds drift by day",
                  float(tpg.eval_on_selector(".hero-cloud", "e=>getComputedStyle(e).opacity")) > 0
                  and tpg.eval_on_selector(".hero-cloud", "e=>getComputedStyle(e).animationPlayState")
                      == "running")
        else:
            check(f"sun and clouds stay hidden at {want}",
                  float(tpg.eval_on_selector(".hero-sun", "e=>getComputedStyle(e).opacity")) == 0
                  and float(tpg.eval_on_selector(".hero-cloud", "e=>getComputedStyle(e).opacity")) == 0)
        tpg.close()
    # The sun's altitude itself: noon at midsummer is about 50° over Åre, and the
    # midnight sun leaves the sky in twilight rather than night.
    tpg = tzctx.new_page(); fontmirror.prepare(tpg, URL)
    noon = tpg.evaluate("cvTod.sun(new Date('2026-06-21T11:08:00Z')).alt")
    check("solar altitude at midsummer noon is about 50 degrees", abs(noon - 50) < 1.5, noon)
    check("midsummer midnight over Åre is twilight, never night",
          tpg.evaluate("cvTod.phase(new Date('2026-06-21T00:00:00Z'))") in ("tod-dawn", "tod-dusk")
          and tpg.evaluate("cvTod.phase(new Date('2026-12-21T02:00:00Z'))") == "tod-night"
          and tpg.evaluate("cvTod.phase(new Date('2026-12-21T19:00:00Z'))") == "tod-night")
    tpg.close()
    tzctx.close()
    check("different phases actually carry different aurora colours",
          len(set(seen.values())) > 1, seen)
    check("stars are gone by day, faint in twilight, full at night",
          star_op["tod-day"] == 0 and 0 < star_op["tod-dusk"] < star_op["tod-night"] == 1
          and 0 < star_op["tod-dawn"] < star_op["tod-night"], star_op)

    pg.emulate_media(media="print")
    check("the sun and clouds are hidden in print",
          pg.eval_on_selector(".hero-sun","e=>getComputedStyle(e).display")=="none"
          and pg.eval_on_selector(".hero-cloud","e=>getComputedStyle(e).display")=="none")
    pg.emulate_media(media="screen")

    b.close()

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
