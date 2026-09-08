#!/usr/bin/env python3
"""Refresh the daily market strip in data/markets.json.

Fetches the latest quote for a few broad ETFs and two SEK crosses from
Alpha Vantage (key in ALPHAVANTAGE_KEY) and writes a small JSON file the
page reads from its own origin. Five calls a run, well inside a free key's
daily allowance; the script sleeps between calls to stay under 5 a minute.

    python tools/update-markets.py                     # fetch and write data/markets.json
    python tools/update-markets.py --fixture-dir DIR   # read DIR/<ID>.json instead of the network
    python tools/update-markets.py --out FILE          # write elsewhere (dry run)

The file keeps its previous contents when every fetch fails, so a bad day
at the API never blanks the strip; a single failed item is dropped for
that run and the rest are written.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "markets.json"
API = "https://www.alphavantage.co/query"

# id, label, kind, api symbol(s). Labels are the same in both languages.
ITEMS = [
    ("SPY", "S&P 500", "etf", "SPY"),
    ("QQQ", "Nasdaq 100", "etf", "QQQ"),
    ("EWD", "MSCI Sweden", "etf", "EWD"),
    ("EURSEK", "EUR/SEK", "fx", ("EUR", "SEK")),
    ("USDSEK", "USD/SEK", "fx", ("USD", "SEK")),
]


def get(params, key):
    q = urllib.parse.urlencode(dict(params, apikey=key))
    with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_etf(obj, item_id):
    q = obj.get("Global Quote") or {}
    price = float(q["05. price"])
    prev = float(q["08. previous close"])
    day = q["07. latest trading day"]
    if not (price > 0 and prev > 0) or len(day) != 10:
        raise ValueError(f"{item_id}: bad quote {q}")
    return {"price": round(price, 2), "chg": round(price / prev - 1, 5), "day": day}


def parse_fx(obj, item_id):
    series = obj.get("Time Series FX (Daily)") or {}
    days = sorted(series)[-2:]
    if len(days) < 2:
        raise ValueError(f"{item_id}: fewer than two days {list(series)[:3]}")
    last, prev = float(series[days[-1]]["4. close"]), float(series[days[-2]]["4. close"])
    if not (last > 0 and prev > 0):
        raise ValueError(f"{item_id}: bad closes")
    return {"price": round(last, 3), "chg": round(last / prev - 1, 5), "day": days[-1]}


def fetch_item(item, key, fixture_dir):
    item_id, label, kind, sym = item
    if fixture_dir:
        obj = json.loads((pathlib.Path(fixture_dir) / f"{item_id}.json").read_text(encoding="utf-8"))
    elif kind == "etf":
        obj = get({"function": "GLOBAL_QUOTE", "symbol": sym}, key)
    else:
        obj = get({"function": "FX_DAILY", "from_symbol": sym[0], "to_symbol": sym[1], "outputsize": "compact"}, key)
    if "Note" in obj or "Information" in obj:
        raise ValueError(f"{item_id}: API limit: {obj.get('Note') or obj.get('Information')}")
    data = parse_etf(obj, item_id) if kind == "etf" else parse_fx(obj, item_id)
    return dict(id=item_id, label=label, kind=kind, **data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-dir")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    key = os.environ.get("ALPHAVANTAGE_KEY", "")
    if not a.fixture_dir and not key:
        sys.exit("ALPHAVANTAGE_KEY is not set")

    items, failed = [], []
    for i, item in enumerate(ITEMS):
        if i and not a.fixture_dir:
            time.sleep(13)     # five calls a minute on a free key
        try:
            items.append(fetch_item(item, key, a.fixture_dir))
            print(f"{item[0]:7} {items[-1]['price']:>10} {items[-1]['chg']*100:+.2f}%  {items[-1]['day']}")
        except Exception as e:      # one bad item never blocks the rest
            failed.append(item[0])
            print(f"{item[0]:7} FAILED: {e}", file=sys.stderr)

    if not items:
        sys.exit("every item failed; keeping the previous file")
    out = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(items)} items{', failed: ' + ', '.join(failed) if failed else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
