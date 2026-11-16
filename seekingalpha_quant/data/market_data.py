"""DB-first daily prices: read from Supabase `prices_daily`; for tickers the
database lacks (or doesn't cover from `start`), fetch from FMP, upsert into
the database, and return. Follows the data-first rule in CLAUDE.md.
"""

import datetime as dt

import requests

from seekingalpha_quant.data import supabase_db as db

FMP = "https://financialmodelingprep.com/stable/historical-price-eod"


def _fmp_daily(symbol, start):
    h = {"apikey": "proxy-injected"}  # real key injected by the session proxy
    full = requests.get(f"{FMP}/full", params={"symbol": symbol, "from": start}, headers=h, timeout=60).json()
    adj = requests.get(f"{FMP}/dividend-adjusted", params={"symbol": symbol, "from": start}, headers=h, timeout=60).json()
    if not isinstance(full, list):
        return []
    adj = {x["date"]: x.get("adjClose") for x in adj} if isinstance(adj, list) else {}
    return [{"date": x["date"], "open": x["open"], "high": x["high"], "low": x["low"], "close": x["close"],
             "adj_close": adj.get(x["date"]) or x["close"], "volume": int(x.get("volume") or 0)}
            for x in full if x.get("volume")]


def load_daily(symbols, start="2018-01-01", market="US", fill_missing=True, verbose=True):
    """{symbol: [ {date, open, high, low, close, adj_close, volume}, ... ] ascending}."""
    ids = db.security_ids(market)
    out = {}
    wanted = [s for s in symbols if s in ids]
    for i in range(0, len(wanted), 40):
        chunk = wanted[i:i + 40]
        by_id = {ids[s]: s for s in chunk}
        rows = db.select("prices_daily", {
            "security_id": f"in.({','.join(str(ids[s]) for s in chunk)})",
            "date": f"gte.{start}",
            "select": "security_id,date,open,high,low,close,adj_close,volume",
            "order": "security_id,date"})
        for r in rows:
            out.setdefault(by_id[r.pop("security_id")], []).append(r)
    missing = [s for s in symbols if not out.get(s)]
    if missing and fill_missing:
        for s in missing:
            recs = _fmp_daily(s, start)
            if not recs:
                if verbose:
                    print(f"  ! {s}: not in DB and FMP has no data")
                continue
            if s not in ids:
                db.upsert("securities", [{"market": market, "symbol": s}], on_conflict="market,symbol")
                ids = db.security_ids(market)
            db.upsert("prices_daily", [dict(r, security_id=ids[s], source="fmp") for r in recs],
                      on_conflict="security_id,date", batch=5000)
            out[s] = recs
            if verbose:
                print(f"  + {s}: {len(recs)} rows fetched from FMP and cached to DB")
    for s in out:
        for r in out[s]:
            if isinstance(r["date"], str):
                r["date"] = dt.date.fromisoformat(r["date"])
    return out
