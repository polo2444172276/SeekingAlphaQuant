"""Raw inputs for the sector-specific factor (factors/sector_specific.py).

Unlike the other factors, these metrics aren't available from FMP's
precomputed ratios-ttm/key-metrics-ttm/financial-growth endpoints -- they
need line items straight off the income statement / balance sheet
(latest annual report, same "one snapshot, not a true TTM" simplification
already used by financial-growth elsewhere in this codebase).

Only sectors with a defined metric get fetched at all -- Energy,
Industrials, Basic Materials and Utilities are deliberately skipped (both
to save API calls and because every metric considered for them either
isn't in any standard financial statement at all, e.g. O&G reserves, or
needs data FMP doesn't expose, e.g. regulated-utility allowed ROE -- see
config.py's comment on SECTOR_SPECIFIC_METRICS).

rule_of_40 (Technology / Communication Services) is the one exception
computed here only partially -- it needs revenue_growth_yoy and
net_margin, which the caller already has from fundamentals.py's panel, so
it's finished off by the caller (see scripts/run_snapshot.py) rather than
refetched.
"""

import sys

import pandas as pd

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled

SECTORS_WITH_METRIC = {
    "Real Estate",
    "Financial Services",
    "Technology",
    "Communication Services",
    "Healthcare",
    "Consumer Cyclical",
    "Consumer Defensive",
}


def _first(rows):
    return rows[0] if rows else {}


def fetch_ticker_row(client, ticker, sector):
    row = {
        "ticker": ticker,
        "rule_of_40": None,
        "nim_proxy": None,
        "ffo_margin": None,
        "rd_intensity": None,
        "inventory_turnover": None,
    }
    if sector not in SECTORS_WITH_METRIC:
        return row

    try:
        income = _first(client.get(
            "/stable/income-statement", {"symbol": ticker, "period": "annual", "limit": 1},
            daily_cache=True,
        ))
        balance = _first(client.get(
            "/stable/balance-sheet-statement", {"symbol": ticker, "period": "annual", "limit": 1},
            daily_cache=True,
        ))
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return row

    revenue = income.get("revenue")

    if sector == "Real Estate" and revenue:
        net_income = income.get("netIncome")
        dep_amort = income.get("depreciationAndAmortization")
        if net_income is not None and dep_amort is not None:
            # FFO (NAREIT definition, simplified) = net income + D&A,
            # expressed as a margin on revenue so it's comparable across
            # REITs of different sizes.
            row["ffo_margin"] = (net_income + dep_amort) / revenue

    elif sector == "Financial Services":
        total_assets = balance.get("totalAssets")
        nii = income.get("netInterestIncome")
        if nii is not None and total_assets:
            # True NIM divides by *average earning assets* (loans +
            # securities), a bank-specific balance-sheet aggregate FMP
            # doesn't expose generically -- total assets is a rougher
            # proxy that will understate true NIM, but ranks banks
            # against each other in roughly the right order.
            row["nim_proxy"] = nii / total_assets

    elif sector == "Healthcare" and revenue:
        rd = income.get("researchAndDevelopmentExpenses")
        if rd is not None:
            row["rd_intensity"] = rd / revenue

    elif sector in ("Consumer Cyclical", "Consumer Defensive"):
        inventory = balance.get("inventory")
        cogs = income.get("costOfRevenue")
        if inventory and cogs is not None:
            row["inventory_turnover"] = cogs / inventory

    # rule_of_40 (Technology / Communication Services) is filled in by the
    # caller -- see module docstring.
    return row


def build_sector_specific_panel(client, tickers, sectors):
    """tickers and sectors must be parallel (same order/length) -- the
    caller already has sector from the fundamentals panel, no need to
    refetch /stable/profile here."""
    rows = [
        fetch_ticker_row(client, ticker, sector)
        for ticker, sector in zip(tickers, sectors)
    ]
    return pd.DataFrame(rows)
