#!/usr/bin/env python3
"""Refresh the stock-quiz data embedded in index.html.

Reads tools/stocks.txt, fetches monthly adjusted closes for each symbol from
Alpha Vantage (key in ALPHAVANTAGE_KEY), validates the series and rewrites
the `var DATA = [...]` line inside index.html in place. The page itself never
fetches: the game works offline from this embedded blob.

    python tools/update-stocks.py                 # fetch and rewrite
    python tools/update-stocks.py --csv-dir DIR   # read DIR/<SYMBOL>.csv instead of the network
    python tools/update-stocks.py --out FILE      # write the page elsewhere (dry run)

A symbol whose series fails validation keeps the series already embedded,
so a bad day at the API never degrades the game. Free keys allow 25 calls
a day and 5 a minute; the fetch sleeps between calls accordingly.
"""
import argparse
import csv
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
LIST = ROOT / "tools" / "stocks.txt"
START = "2008-01"          # never embed older months than this
MIN_POINTS = 60            # a series shorter than five years is not a fair puzzle
API = "https://www.alphavantage.co/query"


def read_list(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            sys.exit(f"stocks.txt: expected 4 fields, got {len(parts)}: {line!r}")
        rows.append({"t": parts[0], "n": parts[1], "sv": parts[2], "en": parts[3]})
    return rows


def fetch_csv(symbol, key):
    q = urllib.parse.urlencode({"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol,
                                "datatype": "csv", "apikey": key})
    with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
        return r.read().decode("utf-8")


def parse(text):
    """CSV -> (start 'YYYY-MM', end 'YYYY-MM', [adjusted closes oldest first]) or None."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "adjusted close" not in reader.fieldnames:
        return None
    by_month = {}
    for row in reader:
        month = row["timestamp"][:7]
        try:
            v = float(row["adjusted close"])
        except (TypeError, ValueError):
            return None
        if month >= START:
            by_month[month] = v                # one row per month in this series
    if not by_month:
        return None
    months = sorted(by_month)
    # Reject gaps: every month between first and last must be present
    y, m = map(int, months[0].split("-"))
    expected = []
    while f"{y:04d}-{m:02d}" <= months[-1]:
        expected.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    if expected != months:
        return None
    vals = [by_month[k] for k in months]
    if len(vals) < MIN_POINTS or min(vals) <= 0:
        return None
    return months[0], months[-1], vals


def sig4(v):
    return float(f"{v:.4g}")


def load_embedded(page_text):
    m = re.search(r"^    var DATA = (\[.*\]);$", page_text, re.M)
    if not m:
        sys.exit("index.html: could not find the `var DATA = [...]` line")
    return json.loads(m.group(1)), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", type=pathlib.Path, help="read <SYMBOL>.csv files from here instead of fetching")
    ap.add_argument("--out", type=pathlib.Path, help="write the rewritten page here instead of index.html")
    ap.add_argument("--sleep", type=float, default=13.0, help="seconds between API calls")
    args = ap.parse_args()

    key = os.environ.get("ALPHAVANTAGE_KEY", "")
    if not args.csv_dir and not key:
        sys.exit("ALPHAVANTAGE_KEY is not set (or pass --csv-dir)")

    page_text = PAGE.read_text(encoding="utf-8")
    embedded, match = load_embedded(page_text)
    previous = {d["t"]: d for d in embedded}
    wanted = read_list(LIST)

    out, refreshed, kept, dropped = [], [], [], []
    for i, meta in enumerate(wanted):
        sym = meta["t"]
        text = None
        try:
            if args.csv_dir:
                f = args.csv_dir / f"{sym}.csv"
                text = f.read_text(encoding="utf-8") if f.exists() else None
            else:
                if i:
                    time.sleep(args.sleep)
                text = fetch_csv(sym, key)
        except Exception as e:      # network, HTTP, decoding: keep what we have
            print(f"{sym}: fetch failed ({e})")
        parsed = parse(text) if text else None
        if parsed:
            start, end, vals = parsed
            out.append({**meta, "s": start, "e": end, "p": [sig4(v) for v in vals]})
            refreshed.append(sym)
        elif sym in previous:
            out.append({**previous[sym], **{k: meta[k] for k in ("n", "sv", "en")}})
            kept.append(sym)
        else:
            dropped.append(sym)

    if not out:
        sys.exit("no series at all; leaving index.html untouched")
    if len(out) < 8:
        sys.exit(f"only {len(out)} usable series; refusing to shrink the quiz below eight")

    blob = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    new_text = page_text[:match.start(1)] + blob + page_text[match.end(1):]
    target = args.out or PAGE
    target.write_text(new_text, encoding="utf-8")

    print(f"refreshed {len(refreshed)}: {' '.join(refreshed) or '-'}")
    print(f"kept      {len(kept)}: {' '.join(kept) or '-'}")
    print(f"dropped   {len(dropped)}: {' '.join(dropped) or '-'}")
    print(f"wrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target} "
          f"({len(out)} companies, {sum(len(d['p']) for d in out)} points, {len(blob)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
