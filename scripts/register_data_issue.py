"""Register a bad-data issue in data_issues (see seekingalpha_quant/data/market_data.py).

  # replace a date range with Yahoo adjclose/OHLC, recording how far off the raw data was
  python scripts/register_data_issue.py override-yahoo MTUM --from 2021-12-01 \
      --reason "FMP dividend-adjusted series over-deducts dividends"

  # keep the data but warn every reader
  python scripts/register_data_issue.py flag SBNY --from 2023-03-13 --reason "..."

  # drop rows
  python scripts/register_data_issue.py exclude XYZ --from 2024-01-02 --to 2024-01-05 --reason "..."

  # list active issues
  python scripts/register_data_issue.py list
"""
import argparse
import json
import os
import ssl
import sys
import urllib.request
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import pandas as pd  # noqa: E402

from seekingalpha_quant.data import market_data as md  # noqa: E402


def yahoo_rows(symbol, start, end):
    p1 = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
    p2 = int(datetime.combine(end, datetime.min.time(), timezone.utc).timestamp()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div,splits")
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r:
        res = json.load(r)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out = []
    for i, ts in enumerate(res["timestamp"]):
        if q["close"][i] is None or adj[i] is None:
            continue
        d = datetime.fromtimestamp(ts, timezone.utc).date()
        if start <= d <= end:
            out.append({"date": d.isoformat(), "open": q["open"][i], "high": q["high"][i], "low": q["low"][i],
                        "close": q["close"][i], "adj_close": adj[i], "volume": int(q["volume"][i] or 0)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["override-yahoo", "flag", "exclude", "list"])
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--reason")
    a = ap.parse_args()

    if a.cmd == "list":
        print(md.issues().to_string(index=False))
        return
    if not (a.symbol and a.reason):
        ap.error("symbol and --reason are required")

    if a.cmd in ("flag", "exclude"):
        iid = md.add_issue(a.symbol, a.cmd, a.reason, a.start, a.end)
        print(f"issue #{iid}: {a.cmd} {a.symbol} {a.start or '…'} → {a.end or '…'}")
        return

    start = date.fromisoformat(a.start) if a.start else date(2000, 1, 1)
    end = date.fromisoformat(a.end) if a.end else date.today()
    rows = yahoo_rows(a.symbol, start, end)
    if not rows:
        sys.exit(f"Yahoo returned nothing for {a.symbol}")
    raw = md.get_prices(a.symbol, rows[0]["date"], rows[-1]["date"], apply_overrides=False)
    y = pd.DataFrame(rows).assign(date=lambda d: pd.to_datetime(d.date)).set_index("date")
    j = raw.set_index("date").join(y, rsuffix="_new", how="inner")
    ratio = j.adj_close / j.adj_close_new
    evidence = {"rows": len(rows), "raw_sources": sorted(raw.source.unique().tolist()),
                "raw_over_new_adj_min": round(float(ratio.min()), 4),
                "raw_over_new_adj_max": round(float(ratio.max()), 4),
                "worst_date": str(ratio.sub(1).abs().idxmax().date())}
    iid = md.add_price_override(a.symbol, rows, a.reason, source="yahoo", evidence=evidence)
    print(f"issue #{iid}: override {a.symbol} {rows[0]['date']} → {rows[-1]['date']} ({len(rows)} rows) {evidence}")


if __name__ == "__main__":
    main()
