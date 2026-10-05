"""Historical market cap, for computing point-in-time price-based ratios
(P/E, P/B, EV/EBITDA, ...) that FMP's Starter plan won't hand over
pre-computed for historical dates."""

import datetime as dt
import sys

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled


def fetch_market_cap_history(client, ticker, start, end):
    """Returns a list of {"date": date, "market_cap": float} sorted
    ascending. A single call covers the whole range (confirmed up to 5000
    rows/~20 years in one shot -- no pagination needed at a 7-year scale)."""
    try:
        rows = client.get(
            "/stable/historical-market-capitalization",
            {"symbol": ticker, "from": start.isoformat(), "to": end.isoformat()},
        )
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return []
    out = [
        {"date": dt.date.fromisoformat(row["date"]), "market_cap": row.get("marketCap")}
        for row in rows
    ]
    out.sort(key=lambda r: r["date"])
    return out


def market_cap_as_of(mc_history, as_of):
    """Latest known market cap on or before `as_of` -- a plain backward
    lookup (mc_history is small, a few thousand rows at most; no need for
    pandas merge_asof machinery here)."""
    best = None
    for row in mc_history:
        if row["date"] > as_of:
            break
        best = row["market_cap"]
    return best
