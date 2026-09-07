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


def _net_upgrades(grades, days):
    if grades is None:
        return None
    cutoff = dt.date.today() - dt.timedelta(days=days)
    net = 0
    for row in grades:
        date = row.get("date")
        if not date:
            continue
        if dt.date.fromisoformat(date) < cutoff:
            continue
        action = (row.get("action") or "").lower()
        if action in UPGRADE_ACTIONS:
            net += 1
        elif action in DOWNGRADE_ACTIONS:
            net -= 1
    return net


def compute_eps_revisions_row(client, ticker):
    try:
        grades = client.get("/stable/grades", {"symbol": ticker, "limit": 100})
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
