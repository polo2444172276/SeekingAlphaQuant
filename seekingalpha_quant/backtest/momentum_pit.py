"""Daily rolling momentum returns for a full historical price series --
the same "nearest trading day on/before the target date" arithmetic as
seekingalpha_quant.data.prices._return_since/_return_ytd, but vectorized
across every trading day at once (the historical backfill needs momentum
for ~1900 days x ~700 tickers; the original per-date truncate-and-lookup
approach would mean ~1.3M individual DataFrame slices, far too slow)."""

import sys

import pandas as pd

from seekingalpha_quant.data.fmp_client import SymbolNotEntitled

_WINDOWS = {
    "return_1m": 30,
    "return_3m": 91,
    "return_6m": 182,
    "return_9m": 273,
    "return_12m": 365,
}


def fetch_price_history_range(client, ticker, start, end):
    """Full-range dividend-adjusted price history (unlike
    data.prices.fetch_price_history, which is hardcoded to a 380-day
    trailing window ending "today" -- the backfill needs an explicit
    multi-year start/end instead). Confirmed live that a 7-year range
    returns in one call, no pagination needed."""
    try:
        rows = client.get(
            "/stable/historical-price-eod/dividend-adjusted",
            {"symbol": ticker, "from": start.isoformat(), "to": end.isoformat()},
        )
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def build_daily_returns(price_df, close_col="adjClose"):
    """price_df: DataFrame indexed by date, with `close_col`. Returns a
    DataFrame indexed by the same trading dates with columns
    return_1m/3m/6m/9m/12m/ytd."""
    s = price_df[close_col].dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if s.empty:
        return pd.DataFrame(columns=list(_WINDOWS) + ["return_ytd"])

    out = pd.DataFrame(index=s.index)
    for col, days_ago in _WINDOWS.items():
        target = s.index - pd.Timedelta(days=days_ago)
        past = s.reindex(target, method="ffill")
        out[col] = s.values / past.values - 1

    # YTD: baseline = last trading day on/before Jan 1 of that date's year;
    # if history doesn't reach back that far (e.g. the ticker's first
    # calendar year in range), fall back to that year's earliest observed
    # price instead -- same fallback prices._return_ytd documents.
    year_starts = pd.to_datetime({"year": s.index.year, "month": 1, "day": 1})
    baseline_ytd = pd.Series(
        s.reindex(year_starts.values, method="ffill").values, index=s.index
    )
    first_of_year = s.groupby(s.index.year).transform("first")
    baseline_ytd = baseline_ytd.fillna(first_of_year)
    out["return_ytd"] = s.values / baseline_ytd.values - 1

    # Normalize to plain date objects -- callers compare against
    # datetime.date values throughout (rebalance dates, trading_dates),
    # and `date in DatetimeIndex` silently always returns False (pandas
    # doesn't coerce for membership tests), which would make every
    # lookup miss without this.
    out.index = out.index.date
    return out
