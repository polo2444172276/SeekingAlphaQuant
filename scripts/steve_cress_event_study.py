"""Post-publication price reaction to Steven Cress / SA Quant picks.

Event = one (publication time, ticker) pair from any source:
  annual Top 10, H2 Top 10, Alpha Picks (deduped by picked date + ticker).

Reference price = last close BEFORE readers could act:
  * published pre-market / non-trading day / intraday -> previous session close
    (intraday publications make that same session "day 1")
  * published after 16:00 ET -> that session's close; day 1 = next session
  * Alpha Picks have dates only; treated as pre-market/intraday on that date.

For trading days k = 1..6 after publication, records Open/High/Low/Close of
day k divided by the reference close, minus 1 (raw), and the same minus SPY's
corresponding return (abnormal). Also the running max High over days 1..k.

Writes data/steve_cress/event_study.csv (long form). Stdlib only.
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
D = os.path.join(ROOT, "data", "steve_cress")
OUT = os.path.join(D, "event_study.csv")
DAYS = 6

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import steve_cress_prices as prices  # noqa: E402


def fetch_ohlc(ticker):
    """(date, open, high, low, close) rows; Yahoo with FMP fallback."""
    return [r[:5] for r in prices.get(ticker)]


def load_events():
    ev = {}
    for r in csv.DictReader(open(os.path.join(D, "top_stocks_picks.csv"))):
        src = "H2 Top 10" if "H2" in r["list"] else "Annual Top 10"
        d, hm = r["published_et"].split()
        ev[(src, d, r["ticker"])] = hm
    seen = set()
    for f in ("alpha_picks_current.csv", "alpha_picks_closed.csv"):
        for r in csv.DictReader(open(os.path.join(D, f))):
            k = (r["picked"], r["ticker"])
            if k not in seen:
                seen.add(k)
                ev[("Alpha Picks", r["picked"], r["ticker"])] = None
    return ev


def main():
    events = load_events()
    tickers = sorted({k[2] for k in events} | {"SPY"})
    px = {}
    for t in tickers:
        px[t] = fetch_ohlc(t)
        time.sleep(0.2)
    spy = {row[0]: row for row in px["SPY"]}

    rows, skipped = [], []
    for (src, d, t), hm in sorted(events.items()):
        s = px.get(t) or []
        pub = date.fromisoformat(d)
        after_close = hm is not None and hm >= "16:00"
        if after_close:
            idx_ref = max((i for i, x in enumerate(s) if x[0] <= pub), default=None)
        else:
            idx_ref = max((i for i, x in enumerate(s) if x[0] < pub), default=None)
        if idx_ref is None or idx_ref + 1 >= len(s):
            skipped.append((src, d, t))
            continue
        ref = s[idx_ref]
        sref = spy.get(ref[0])
        run_hi = -1e9
        for k in range(1, DAYS + 1):
            if idx_ref + k >= len(s):
                break
            day = s[idx_ref + k]
            sd = spy.get(day[0])
            run_hi = max(run_hi, day[2])
            vals = {"open": day[1], "high": day[2], "low": day[3], "close": day[4], "max_high_to_date": run_hi}
            svals = None
            if sd and sref:
                svals = {"open": sd[1], "high": sd[2], "low": sd[3], "close": sd[4], "max_high_to_date": None}
            for field, v in vals.items():
                raw = v / ref[4] - 1
                if svals and svals[field] is not None:
                    abn = raw - (svals[field] / sref[4] - 1)
                elif svals and field == "max_high_to_date":
                    # SPY benchmark for running max: SPY close-to-close over same window
                    abn = raw - (sd[4] / sref[4] - 1)
                else:
                    abn = None
                rows.append([src, d, hm or "", t, ref[0], round(ref[4], 4), k, day[0], field,
                             round(raw, 5), "" if abn is None else round(abn, 5)])

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "published", "published_time_et", "ticker", "ref_date", "ref_close",
                    "day", "date", "field", "raw_return", "abnormal_vs_spy"])
        w.writerows(rows)
    print("events:", len(events), "used:", len({(r[0], r[1], r[3]) for r in rows}), "skipped:", skipped)


if __name__ == "__main__":
    main()
