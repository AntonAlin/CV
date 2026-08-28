"""Make the suites render with the real webfonts, or fail saying they didn't.

The page pulls Inter, Fraunces and JetBrains Mono from Google Fonts. A sandbox
without outbound access to fonts.googleapis.com renders every one of them as
the browser's default serif instead — silently, since the stylesheet simply
fails and the cascade falls through. Layout measurements taken that way are
meaningless: they paginate differently from CI, which does have the real fonts.

That is not hypothetical. A print regression reached main because the local run
was measuring fallback fonts and reported the sheet well filled when it was not.

So: mirror the fonts to disk once (curl reaches the network here even where the
browser cannot), serve them to Chromium from that mirror, and let the suites
assert that the faces really are in use.
"""
import pathlib
import re
import subprocess

CSS_URL = ("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500"
           "&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500"
           "&display=swap")
# Google serves different files per user agent; pin one so the mirror is stable.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

DIR = pathlib.Path(__file__).parent / ".fonts"
FAMILIES = ("Inter", "Fraunces", "JetBrains Mono")

_mirror = None          # {url: local path}, or {} when unavailable
_reported = False


def _fetch(url, dest):
    r = subprocess.run(["curl", "-sSf", "-A", UA, "-o", str(dest), url],
                       capture_output=True, text=True)
    return r.returncode == 0 and dest.exists() and dest.stat().st_size > 400


def _build():
    """Download the stylesheet and every font file it names. Cached on disk."""
    DIR.mkdir(exist_ok=True)
    css = DIR / "fonts.css"
    if not css.exists() and not _fetch(CSS_URL, css):
        return {}
    urls = sorted(set(re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)",
                                 css.read_text())))
    if not urls:
        return {}
    out = {}
    for i, u in enumerate(urls):
        f = DIR / f"font{i}.woff2"
        if not f.exists() and not _fetch(u, f):
            return {}
        out[u] = f
    return out


def arm(page):
    """Serve the font requests on this page from the mirror, if there is one.

    A miss is not fatal here — the browser may well reach Google directly, as
    it does in CI. `assert_real_fonts` is what decides whether the render can
    be trusted.
    """
    global _mirror
    if _mirror is None:
        _mirror = _build()
    if not _mirror:
        return False
    css = (DIR / "fonts.css").read_text()
    page.route("https://fonts.googleapis.com/**",
               lambda r: r.fulfill(status=200, content_type="text/css", body=css))

    def serve(route):
        f = _mirror.get(route.request.url.split("?")[0])
        route.abort() if f is None else route.fulfill(
            status=200, content_type="font/woff2", body=f.read_bytes())

    page.route("https://fonts.gstatic.com/**", serve)
    return True


def assert_real_fonts(page):
    """Stop the run unless the three families are genuinely rendering.

    document.fonts.check is no use on its own: with no @font-face declared at
    all it happily returns true. Compare rendered widths against the generic
    fallbacks instead — that is the thing measurement actually depends on.
    """
    global _reported
    page.evaluate("document.fonts.ready")
    widths = page.evaluate("""(families) => {
      const measure = stack => {
        const s = document.createElement('span');
        s.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;'
                        + 'font-size:64px;font-family:' + stack;
        s.textContent = 'Handelshogskolan Stockholm 2026';
        document.body.appendChild(s);
        const w = s.getBoundingClientRect().width;
        s.remove();
        return w;
      };
      const out = {};
      for (const f of families) out[f] = measure("'" + f + "',serif");
      out.__serif = measure('serif');
      return out;
    }""", list(FAMILIES))
    missing = [f for f in FAMILIES if abs(widths[f] - widths["__serif"]) < 0.5]
    if missing:
        raise SystemExit(
            "\nFATAL: rendering with fallback fonts, so every layout "
            "measurement below would be wrong.\n"
            f"  not loaded: {', '.join(missing)}\n"
            "  This sandbox cannot reach fonts.googleapis.com from inside "
            "Chromium.\n"
            "  Fix: allow curl to reach fonts.googleapis.com so tools/.fonts "
            "can be built,\n"
            "  or run the suite where the browser can load them directly.\n")
    if not _reported:
        _reported = True
        print(f"fonts: {', '.join(FAMILIES)} loaded")
