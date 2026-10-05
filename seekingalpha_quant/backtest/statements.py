"""Point-in-time quarterly financial statements -> a TTM (trailing-twelve-
month) series per ticker, gated by each filing's real public `acceptedDate`
(not its fiscal period-end `date`) so a historical backtest never "knows"
about a quarter's numbers before they were actually filed.

FMP's Starter plan 402s the pre-computed historical ratio endpoints
(`/stable/ratios`, `/stable/key-metrics` with `period=quarter`), so ratios
get computed manually elsewhere (fundamentals_pit.py) from the raw line
items this module assembles.
"""

import datetime as dt
import sys

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled

STATEMENT_PATHS = {
    "income": "/stable/income-statement",
    "balance": "/stable/balance-sheet-statement",
    "cashflow": "/stable/cash-flow-statement",
}


def fetch_quarterly_statements(client, ticker, limit=100):
    """One call per statement type, each returning up to `limit` quarters
    (FMP's Starter plan supports ~100 quarters/~25 years in one call --
    no per-quarter fetching needed)."""
    try:
        return {
            name: client.get(path, {"symbol": ticker, "period": "quarter", "limit": limit})
            for name, path in STATEMENT_PATHS.items()
        }
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return {name: [] for name in STATEMENT_PATHS}


def _parse_accepted_date(row):
    """The date this filing was actually made public -- use this to gate
    point-in-time knowability, never the fiscal period-end `date`."""
    raw = row.get("acceptedDate") or row.get("filingDate")
    if raw:
        return dt.date.fromisoformat(raw[:10])
    # Conservative fallback for the rare row missing both fields: assume a
    # typical ~45-day filing lag after the fiscal period end.
    return dt.date.fromisoformat(row["date"]) + dt.timedelta(days=45)


def _sum_or_none(rows, field):
    """Sum a field across 4 trailing quarters -- None (not a silently
    understated sum) if any quarter is missing the field, since a missing
    value corrupting a TTM total is worse than an explicit gap."""
    values = [r.get(field) for r in rows]
    if any(v is None for v in values):
        return None
    return sum(values)


def build_ttm_series(statements):
    """Return a list of dicts, one per fiscal quarter (oldest first), each
    a trailing-twelve-month snapshot as of that quarter's `accepted_date`:
    {period_end, accepted_date, ttm_revenue, ttm_net_income, ttm_ebitda,
    ttm_gross_profit, ttm_operating_income, ttm_operating_cash_flow,
    ttm_income_tax_expense, ttm_pretax_income, total_equity, total_assets,
    total_debt, cash}. Needs at least 4 quarters of income-statement
    history; returns [] otherwise (e.g. a recent IPO)."""
    income = statements["income"]
    if len(income) < 4:
        return []

    inc_by_date = {row["date"]: row for row in income}
    bal_by_date = {row["date"]: row for row in statements["balance"]}
    cf_by_date = {row["date"]: row for row in statements["cashflow"]}
    dates = sorted(inc_by_date.keys(), reverse=True)  # newest first, as FMP returns them

    rows = []
    for i in range(len(dates) - 3):
        window = dates[i:i + 4]
        trailing_income = [inc_by_date[d] for d in window]
        trailing_cashflow = [cf_by_date[d] for d in window if d in cf_by_date]

        bal_row = bal_by_date.get(dates[i], {})
        cash = bal_row.get("cashAndCashEquivalents")
        if cash is None:
            cash = bal_row.get("cashAndShortTermInvestments")

        rows.append({
            "period_end": dt.date.fromisoformat(dates[i]),
            "accepted_date": _parse_accepted_date(inc_by_date[dates[i]]),
            "ttm_revenue": _sum_or_none(trailing_income, "revenue"),
            "ttm_net_income": _sum_or_none(trailing_income, "netIncome"),
            "ttm_eps": _sum_or_none(trailing_income, "eps"),
            "ttm_ebitda": _sum_or_none(trailing_income, "ebitda"),
            "ttm_gross_profit": _sum_or_none(trailing_income, "grossProfit"),
            "ttm_operating_income": _sum_or_none(trailing_income, "operatingIncome"),
            "ttm_income_tax_expense": _sum_or_none(trailing_income, "incomeTaxExpense"),
            "ttm_pretax_income": _sum_or_none(trailing_income, "incomeBeforeTax"),
            "ttm_operating_cash_flow": (
                _sum_or_none(trailing_cashflow, "operatingCashFlow")
                if len(trailing_cashflow) == 4 else None
            ),
            "total_equity": bal_row.get("totalStockholdersEquity"),
            "total_assets": bal_row.get("totalAssets"),
            "total_debt": bal_row.get("totalDebt"),
            "cash": cash,
        })

    rows.sort(key=lambda r: r["period_end"])  # ascending, for i-4/i-12/i-20 lookback indexing
    return rows
