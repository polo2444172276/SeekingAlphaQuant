"""EPS Revisions proxy data: net analyst upgrades minus downgrades.

See seekingalpha_quant/factors/eps_revisions.py for why this proxies
Seeking Alpha's real (consensus-estimate-history) factor rather than
replicating it.
"""

import datetime as dt
import sys

import pandas as pd

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled

UPGRADE_ACTIONS = {"upgrade", "initiate"}
DOWNGRADE_ACTIONS = {"downgrade"}


def _net_upgrades(grades, days, as_of=None):
    if grades is None:
        return None
    anchor = as_of or dt.date.today()
    cutoff = anchor - dt.timedelta(days=days)
    net = 0
    for row in grades:
        date = row.get("date")
        if not date:
            continue
        graded_on = dt.date.fromisoformat(date)
        if graded_on < cutoff:
            continue
        # The live daily snapshot only ever sees grades up to "today" (its
        # `grades` list is always freshly fetched as-of now). The
        # historical backfill fetches a ticker's *entire* grades history
        # once and reuses it for every past rebalance date, so it must
        # explicitly exclude anything graded after `anchor` -- otherwise
        # a historical quarter would leak future analyst-rating info.
        if graded_on > anchor:
            continue
        action = (row.get("action") or "").lower()
        if action in UPGRADE_ACTIONS:
            net += 1
        elif action in DOWNGRADE_ACTIONS:
            net -= 1
    return net


def compute_eps_revisions_row(client, ticker):
    try:
        grades = client.get("/stable/grades", {"symbol": ticker, "limit": 100}, daily_cache=True)
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        grades = None  # not the same as [] (genuinely no rating changes) — must not score as 0
    return {
        "ticker": ticker,
        "net_upgrades_1m": _net_upgrades(grades, 30),
        "net_upgrades_3m": _net_upgrades(grades, 91),
    }


def build_eps_revisions_panel(client, tickers):
    rows = [compute_eps_revisions_row(client, ticker) for ticker in tickers]
    return pd.DataFrame(rows)
