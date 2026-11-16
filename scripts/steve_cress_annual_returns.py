"""Returns of Steven Cress's annual "Top 10 Stocks For <year>" lists.

For each list, per ticker and equal-weighted, vs SPY:
  entry  = close on the first trading day on/after publication
  exit   = last close of the target year (latest close if the year is ongoing),
           and separately the latest close ("to date")
Both price return (split-adjusted close) and total return (dividend-adjusted
close) are reported, since published scorecards may use either.

Writes data/steve_cress/annual_returns.csv. Stdlib only.
"""
import csv
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "data", "steve_cress", "top_stocks_picks.csv")
OUT = os.path.join(ROOT, "data", "steve_cress", "annual_returns.csv")


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
    close = res["indicators"]["quote"][0]["close"]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or close
    return [(datetime.fromtimestamp(t, timezone.utc).date(), c, a)
            for t, c, a in zip(ts, close, adj) if c is not None and a is not None]


def window(series, start, end):
    a = next((x for x in series if x[0] >= start), None)
    b = None
    for x in series:
        if x[0] > end:
            break
        b = x
    if not a or not b or b[0] <= a[0]:
        return None
    return a, b


def main():
    picks = [p for p in csv.DictReader(open(PICKS)) if "H2" not in p["list"]]
    lists = {}
    for p in picks:
        lists.setdefault(p["list"], []).append(p)
    prices = {t: fetch(t) for t in sorted({p["ticker"] for p in picks} | {"SPY"})}
    today = date.today()

    out = []
    print(f"{'list':<6}{'horizon':<9}{'n':>3}{'price':>9}{'total':>9}{'SPY px':>9}{'SPY tot':>9}")
    for lst in sorted(lists):
        pub = date.fromisoformat(lists[lst][0]["published_et"][:10])
        for horizon, end in (("in_year", min(date(int(lst), 12, 31), today)), ("to_date", today)):
            if horizon == "to_date" and end == min(date(int(lst), 12, 31), today):
                continue
            pr, tr = [], []
            for p in lists[lst] + [{"ticker": "SPY"}]:
                t = p["ticker"]
                w = window(prices[t], pub, end)
                if w is None:
                    out.append([lst, horizon, t, "", "", "", "", "", "", "no price data"])
                    continue
                (d0, c0, a0), (d1, c1, a1) = w
                r_p, r_t = c1 / c0 - 1, a1 / a0 - 1
                out.append([lst, horizon, t, d0, round(c0, 4), d1, round(c1, 4),
                            round(r_p, 4), round(r_t, 4), ""])
                if t == "SPY":
                    spy = (r_p, r_t)
                else:
                    pr.append(r_p)
                    tr.append(r_t)
            ew_p, ew_t = sum(pr) / len(pr), sum(tr) / len(tr)
            out.append([lst, horizon, "EQUAL_WEIGHT", "", "", "", "", round(ew_p, 4), round(ew_t, 4), f"n={len(pr)}"])
            print(f"{lst:<6}{horizon:<9}{len(pr):>3}{ew_p:>9.2%}{ew_t:>9.2%}{spy[0]:>9.2%}{spy[1]:>9.2%}")

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list", "horizon", "ticker", "entry_date", "entry_close", "exit_date", "exit_close",
                    "price_return", "total_return", "note"])
        w.writerows(out)


if __name__ == "__main__":
    main()
