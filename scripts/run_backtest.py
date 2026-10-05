"""One-time (or occasionally re-run to extend forward) point-in-time
historical backfill: quarterly Valuation/Growth/Profitability/EPS Revisions
+ daily Momentum/overall, for the S&P 500 (including tickers removed from
the index since the start date, to avoid survivorship bias).

Writes data/history/quarterly_fundamentals.parquet and
data/history/daily_history.parquet (gitignored -- generated data, not
committed).

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --start 2019-01-01 --end 2026-09-09
    python scripts/run_backtest.py --tickers AAPL MSFT NVDA   # small test run
"""

import argparse
import datetime as dt
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seekingalpha_quant.backtest import market_cap, membership, momentum_pit, rebalance, statements, storage
from seekingalpha_quant.data.fmp_client import FMPClient, SymbolNotEntitled
from seekingalpha_quant.data.universe import TICKERS


def fetch_grades(client, ticker):
    """Individual analyst grade-action events (date/action), full history
    in one call -- confirmed live that FMP ignores `limit` on this
    endpoint and just returns everything available (back to ~2012 for
    well-covered names)."""
    try:
        return client.get("/stable/grades", {"symbol": ticker})
    except SymbolNotEntitled as exc:
        print(f"[skip] {ticker}: {exc}", file=sys.stderr)
        return None


def fetch_sector(client, ticker):
    try:
        profile = client.get("/stable/profile", {"symbol": ticker})
    except SymbolNotEntitled:
        return None
    return profile[0].get("sector") if profile else None


def main():
    parser = argparse.ArgumentParser(description="Point-in-time historical backfill.")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default=dt.date.today().isoformat())
    parser.add_argument("--tickers", nargs="*", help="Subset of tickers (default: full ever-member universe)")
    args = parser.parse_args()

    if not os.environ.get("FMP_API_KEY"):
        sys.exit("FMP_API_KEY is not set. Copy .env.example to .env and fill in your key.")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    client = FMPClient()

    current_members = set(TICKERS)
    changes = membership.load_changes()
    universe = args.tickers or sorted(membership.ever_members(current_members, changes))

    # The bootstrap rebalance point (one quarter before `start`, see below)
    # needs market cap data too, or its price-based ratios come back empty.
    first_rebalance = dt.date(start.year - 1, 12, 31)

    print(f"Fetching data for {len(universe)} tickers...", file=sys.stderr)
    ticker_data = {}
    price_histories = {}
    for i, ticker in enumerate(universe, 1):
        print(f"  [{i}/{len(universe)}] {ticker}", file=sys.stderr)
        stmts = statements.fetch_quarterly_statements(client, ticker)
        ttm = statements.build_ttm_series(stmts)
        mc_history = market_cap.fetch_market_cap_history(client, ticker, first_rebalance, end)
        sector = fetch_sector(client, ticker)
        grades = fetch_grades(client, ticker)
        price_df = momentum_pit.fetch_price_history_range(client, ticker, start, end)

        ticker_data[ticker] = {
            "ttm": ttm, "sector": sector, "mc_history": mc_history, "grades": grades,
        }
        if not price_df.empty:
            price_histories[ticker] = momentum_pit.build_daily_returns(price_df)

    print("Building quarterly fundamentals panel...", file=sys.stderr)
    # first_rebalance (computed above) is one extra rebalance point before
    # `start` so the first days in range have real carried-forward
    # fundamentals instead of a gap.
    rebalance_dates = rebalance.quarterly_rebalance_dates(first_rebalance, end)
    quarterly_df = rebalance.build_quarterly_panel(rebalance_dates, ticker_data, current_members, changes)
    print(f"  {len(quarterly_df)} rows", file=sys.stderr)

    print("Building daily momentum + overall panel...", file=sys.stderr)
    trading_dates = set()
    for ret_df in price_histories.values():
        trading_dates.update(ret_df.index)
    trading_dates = sorted(d for d in trading_dates if start <= d <= end)
    daily_df = rebalance.build_daily_panel(trading_dates, quarterly_df, price_histories, current_members, changes)
    print(f"  {len(daily_df)} rows", file=sys.stderr)

    storage.save_quarterly(quarterly_df)
    storage.save_daily(daily_df)
    print(f"Saved to {storage.QUARTERLY_PATH} and {storage.DAILY_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
