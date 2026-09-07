"""One-off: today's Seeking-Alpha-style Quant factor grades for the configured
ticker universe (seekingalpha_quant/data/universe.py).

Usage:
    python scripts/run_snapshot.py
    python scripts/run_snapshot.py --tickers AAPL MSFT
"""

import argparse
import datetime as dt
import os
import sys

from dotenv import load_dotenv

# Must run before importing seekingalpha_quant.config, which reads
# FMP_API_KEY from the environment at import time.
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seekingalpha_quant.data.fmp_client import FMPClient
from seekingalpha_quant.data.universe import TICKERS
from seekingalpha_quant.data.fundamentals import build_fundamentals_panel
from seekingalpha_quant.data.prices import build_momentum_panel
from seekingalpha_quant.data.estimates import build_eps_revisions_panel
from seekingalpha_quant.factors import valuation, growth, profitability, momentum, eps_revisions
from seekingalpha_quant.scoring.combine import combine_factors


def main():
    parser = argparse.ArgumentParser(description="Run today's factor-grade snapshot.")
    parser.add_argument("--tickers", nargs="*", help="Subset of tickers (default: full universe)")
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "data", "snapshots"))
    args = parser.parse_args()

    if not os.environ.get("FMP_API_KEY"):
        sys.exit("FMP_API_KEY is not set. Copy .env.example to .env and fill in your key.")

    tickers = args.tickers or TICKERS
    client = FMPClient()

    print(f"Fetching fundamentals for {len(tickers)} tickers...", file=sys.stderr)
    fundamentals_df = build_fundamentals_panel(client, tickers)

    print(f"Fetching price history for momentum...", file=sys.stderr)
    momentum_df = build_momentum_panel(client, tickers)
    momentum_df = momentum_df.merge(fundamentals_df[["ticker", "sector"]], on="ticker", how="left")

    print(f"Fetching analyst grade changes for EPS revisions proxy...", file=sys.stderr)
    eps_df = build_eps_revisions_panel(client, tickers)
    eps_df = eps_df.merge(fundamentals_df[["ticker", "sector"]], on="ticker", how="left")

    factor_frames = {
        "valuation": valuation.compute(fundamentals_df),
        "growth": growth.compute(fundamentals_df),
        "profitability": profitability.compute(fundamentals_df),
        "momentum": momentum.compute(momentum_df),
        "eps_revisions": eps_revisions.compute(eps_df),
    }

    result = combine_factors(factor_frames)
    result = result.sort_values("overall_score", ascending=False)

    display_cols = [
        "ticker", "sector",
        "valuation_grade", "growth_grade", "profitability_grade",
        "momentum_grade", "eps_revisions_grade",
        "overall_score", "overall_rating",
    ]
    print(result[display_cols].to_string(index=False))

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{dt.date.today().isoformat()}.csv")
    result.to_csv(out_path, index=False)
    print(f"\nSaved snapshot to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
