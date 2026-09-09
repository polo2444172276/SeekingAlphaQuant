"""Pull current-snapshot valuation/growth/profitability metrics per ticker.

One FMP call per ticker per endpoint (no batch/multi-symbol support on the
free tier), mapped onto the raw metric names config.py's factor modules
expect. All three factors piggyback on the same set of "current snapshot"
endpoints (profile, ratios-ttm, key-metrics-ttm, financial-growth), so one
row per ticker is built here and reused by valuation/growth/profitability.
"""

import sys

import pandas as pd

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled


def _first(rows):
    return rows[0] if rows else {}


def fetch_ticker_row(client, ticker):
    """Fetch and flatten one ticker's profile + ratios + key-metrics + growth.

    Returns a ticker/sector-only row (all metrics None) if FMP 402s the
    symbol under the current plan, rather than aborting the whole panel.
    """
    try:
        profile = _first(client.get("/stable/profile", {"symbol": ticker}))
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        profile = {}

    try:
        ratios = _first(client.get("/stable/ratios-ttm", {"symbol": ticker}))
        key_metrics = _first(client.get("/stable/key-metrics-ttm", {"symbol": ticker}))
        growth = _first(client.get("/stable/financial-growth", {"symbol": ticker, "limit": 1}))
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        ratios, key_metrics, growth = {}, {}, {}

    return {
        "ticker": ticker,
        "sector": profile.get("sector"),
        # Valuation
        "pe_ratio": ratios.get("priceToEarningsRatioTTM"),
        "pb_ratio": ratios.get("priceToBookRatioTTM"),
        "ps_ratio": ratios.get("priceToSalesRatioTTM"),
        "pcf_ratio": ratios.get("priceToOperatingCashFlowRatioTTM"),
        "peg_ratio": ratios.get("priceToEarningsGrowthRatioTTM"),
        "ev_to_sales": key_metrics.get("evToSalesTTM"),
        "ev_to_ebitda": key_metrics.get("evToEBITDATTM"),
        # Growth
        "revenue_growth_yoy": growth.get("revenueGrowth"),
        "revenue_growth_3y": growth.get("threeYRevenueGrowthPerShare"),
        "revenue_growth_5y": growth.get("fiveYRevenueGrowthPerShare"),
        "eps_growth_yoy": growth.get("epsgrowth"),
        "eps_growth_3y": growth.get("threeYNetIncomeGrowthPerShare"),
        "eps_growth_5y": growth.get("fiveYNetIncomeGrowthPerShare"),
        "ebitda_growth_yoy": growth.get("ebitdaGrowth"),
        # Profitability
        "gross_margin": ratios.get("grossProfitMarginTTM"),
        "operating_margin": ratios.get("operatingProfitMarginTTM"),
        "net_margin": ratios.get("netProfitMarginTTM"),
        "ebitda_margin": ratios.get("ebitdaMarginTTM"),
        "roe": key_metrics.get("returnOnEquityTTM"),
        "roa": key_metrics.get("returnOnAssetsTTM"),
        "roic": key_metrics.get("returnOnInvestedCapitalTTM"),
    }


def build_fundamentals_panel(client, tickers):
    """Return one DataFrame, one row per ticker, with every raw metric column
    needed by the valuation/growth/profitability factor modules."""
    rows = [fetch_ticker_row(client, ticker) for ticker in tickers]
    return pd.DataFrame(rows)
