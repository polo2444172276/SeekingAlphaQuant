"""Performance of Steven Cress's annual "Top Stocks" picks (Seeking Alpha).

Stdlib only. Pulls daily adjusted closes from Yahoo's chart API, then for
each year's list computes, per ticker and equal-weighted:
  * in-year return: first close on/after publication -> last close of that year
    (latest close for the current year)
  * to-date return: first close on/after publication -> latest close
benchmarked against SPY and QQQ over the same windows. Adjusted closes, so
dividends are reinvested.

Usage: python scripts/steve_cress_picks_returns.py
"""
import csv
import json
import os
import ssl
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "data", "steve_cress", "top_stocks_picks.csv")
OUT = os.path.join(ROOT, "data", "steve_cress", "returns.csv")
BENCHMARKS = ["SPY", "QQQ"]


def fetch(ticker):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           "?period1=1640995200&period2=9999999999&interval=1d&events=div,splits")
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
                res = json.load(r)["chart"]["result"][0]
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                print(f"  ! {ticker}: {e}", file=sys.stderr)
                return []
            time.sleep(2 ** attempt)
    ts = res.get("timestamp") or []
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    return [(datetime.fromtimestamp(t, timezone.utc).date(), p) for t, p in zip(ts, adj) if p is not None]


def first_on_or_after(series, d):
    return next(((dd, p) for dd, p in series if dd >= d), None)


def last_on_or_before(series, d):
    out = None
    for dd, p in series:
        if dd > d:
            break
        out = (dd, p)
    return out


def main():
    with open(PICKS) as f:
        picks = list(csv.DictReader(f))
    tickers = sorted({p["ticker"] for p in picks} | set(BENCHMARKS))
    prices = {}
    for t in tickers:
        prices[t] = fetch(t)
        time.sleep(0.3)

    rows = []
    by_year = defaultdict(list)
    for p in picks:
        by_year[p["list"]].append(p)

    def window(t, start, end):
        s = prices.get(t) or []
        a = first_on_or_after(s, start)
        b = last_on_or_before(s, end)
        if not a or not b or b[0] <= a[0]:
            return None
        return a, b, b[1] / a[1] - 1

    today = date.today()
    summary = []
    for year in sorted(by_year):
        pub = datetime.strptime(by_year[year][0]["published_et"][:10], "%Y-%m-%d").date()
        year_end = min(date(int(year[:4]), 12, 31), today)
        for horizon, end in (("in_year", year_end), ("to_date", today)):
            rets = []
            for p in by_year[year]:
                w = window(p["ticker"], pub, end)
                if w is None:
                    rows.append([year, horizon, p["ticker"], "", "", "", "", "no data"])
                    continue
                (d0, p0), (d1, p1), r = w
                stale = " (last price " + d1.isoformat() + ")" if (end - d1).days > 10 else ""
                rows.append([year, horizon, p["ticker"], d0, f"{p0:.4f}", d1, f"{p1:.4f}", f"{r:.4f}"])
                if stale:
                    rows[-1][-1] += stale
                rets.append(r)
            ew = sum(rets) / len(rets) if rets else float("nan")
            bm = {b: (window(b, pub, end) or (None, None, float("nan")))[2] for b in BENCHMARKS}
            hits = sum(r > bm["SPY"] for r in rets)
            summary.append((year, horizon, len(rets), ew, bm["SPY"], bm["QQQ"], hits))

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "horizon", "ticker", "entry_date", "entry_adj", "exit_date", "exit_adj", "return"])
        w.writerows(rows)

    print(f"{'list':<8}{'horizon':<9}{'n':>3}{'EW picks':>10}{'SPY':>9}{'QQQ':>9}{'beat SPY':>10}")
    for y, h, n, ew, spy, qqq, hits in summary:
        print(f"{y:<8}{h:<9}{n:>3}{ew:>10.1%}{spy:>9.1%}{qqq:>9.1%}{hits:>6}/{n}")
    print(f"\nPer-ticker detail -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
