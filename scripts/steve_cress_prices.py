"""Daily OHLC + dividend-adjusted close for the Steven Cress analysis.

Yahoo chart API first; if Yahoo has nothing (delisted names), falls back to
FMP's /stable/historical-price-eod endpoints. The FMP key is injected by the
session's network proxy, so requests send a placeholder header only.

Delisted handling:
  * zero-volume trailing rows (FMP pads the delisting day) are dropped;
  * LTHM: FMP splices Arcadium Lithium (ALTM) prices under the LTHM symbol
    from 2024-01-04; those rows are multiplied by the 2.406 ALTM-per-LTHM
    merger ratio so the series is continuous for a Livent holder.
Rows are cached per process in memory.
"""
import json
import ssl
import sys
import time
import urllib.request
from datetime import date, datetime, timezone

_CACHE = {}
MERGER_SPLICE = {"LTHM": (date(2024, 1, 4), 2.406)}


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 3:
                raise
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def _yahoo(t):
    js = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
              "?period1=1640995200&period2=9999999999&interval=1d&events=div,splits",
              {"User-Agent": "research-script/1.0"})
    if not js or not js.get("chart", {}).get("result"):
        return []
    res = js["chart"]["result"][0]
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    if not q.get("close"):
        return []
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    out = []
    for i, ts in enumerate(res.get("timestamp") or []):
        row = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i])
        if None in row:
            continue
        out.append((datetime.fromtimestamp(ts, timezone.utc).date(),) + row)
    return out


def _fmp(t):
    h = {"apikey": "proxy-injected"}
    base = "https://financialmodelingprep.com/stable/historical-price-eod"
    full = _get(f"{base}/full?symbol={t}&from=2022-01-01", h) or []
    adj = _get(f"{base}/dividend-adjusted?symbol={t}&from=2022-01-01", h) or []
    adj = {x["date"]: x.get("adjClose") for x in adj}
    out = []
    for x in sorted(full, key=lambda x: x["date"]):
        if not x.get("volume"):
            continue
        d = date.fromisoformat(x["date"])
        a = adj.get(x["date"]) or x["close"]
        out.append((d, x["open"], x["high"], x["low"], x["close"], a))
    if t in MERGER_SPLICE:
        cut, ratio = MERGER_SPLICE[t]
        out = [r if r[0] < cut else (r[0],) + tuple(v * ratio for v in r[1:]) for r in out]
    return out


def get(ticker):
    """List of (date, open, high, low, close, adj_close), ascending."""
    if ticker not in _CACHE:
        rows = _yahoo(ticker)
        src = "yahoo"
        if not rows:
            rows, src = _fmp(ticker), "fmp"
        if not rows:
            print(f"  ! no data for {ticker}", file=sys.stderr)
        elif src == "fmp":
            print(f"  · {ticker}: FMP fallback, {len(rows)} rows, last {rows[-1][0]}", file=sys.stderr)
        _CACHE[ticker] = rows
        time.sleep(0.15)
    return _CACHE[ticker]
