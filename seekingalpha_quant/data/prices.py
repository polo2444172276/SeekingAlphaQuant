"""Daily price history and trailing-return momentum metrics per ticker."""

import datetime as dt
import sys

import pandas as pd

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled


def fetch_price_history(client, ticker, lookback_days=380):
    """Fetch daily adjusted close history covering the trailing `lookback_days`.

    Uses dividend-adjusted close (both split- and dividend-adjusted), not
    FMP's plain "full" endpoint -- that one is split-adjusted only, which
    understates trailing returns for higher-dividend-yield names.

    Well under FMP's ~5000-row-per-request cap, so a single call suffices
    (unlike the multi-decade backfill case in the sibling backtest project).
    Returns an empty DataFrame if FMP 402s the symbol under the current plan.
    """
    start = (dt.date.today() - dt.timedelta(days=lookback_days)).isoformat()
    try:
        rows = client.get(
            "/stable/historical-price-eod/dividend-adjusted",
            {"symbol": ticker, "from": start},
        )
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _return_since(df, close_col, days_ago):
    if df.empty:
        return None
    target = df.index.max() - pd.Timedelta(days=days_ago)
    past = df[df.index <= target]
    if past.empty:
        return None
    start_price = past[close_col].iloc[-1]
    end_price = df[close_col].iloc[-1]
    if not start_price:
        return None
    return end_price / start_price - 1


def _return_ytd(df, close_col):
    if df.empty:
        return None
    year_start = pd.Timestamp(year=df.index.max().year, month=1, day=1)
    past = df[df.index <= year_start]
    if past.empty:
        # No trading day on/before Jan 1 in range (e.g. new listing) — use the
        # earliest available bar this year as the baseline instead.
        this_year = df[df.index.year == df.index.max().year]
        if this_year.empty:
            return None
        start_price = this_year[close_col].iloc[0]
    else:
        start_price = past[close_col].iloc[-1]
    end_price = df[close_col].iloc[-1]
    if not start_price:
        return None
    return end_price / start_price - 1


def compute_momentum_row(client, ticker):
    df = fetch_price_history(client, ticker)
    close_col = "adjClose"
    return {
        "ticker": ticker,
        "return_1m": _return_since(df, close_col, 30),
        "return_3m": _return_since(df, close_col, 91),
        "return_6m": _return_since(df, close_col, 182),
        "return_9m": _return_since(df, close_col, 273),
        "return_12m": _return_since(df, close_col, 365),
        "return_ytd": _return_ytd(df, close_col),
    }


def build_momentum_panel(client, tickers):
    rows = [compute_momentum_row(client, ticker) for ticker in tickers]
    return pd.DataFrame(rows)
