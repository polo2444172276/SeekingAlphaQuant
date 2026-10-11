"""Daily job: refresh the VIX / MOVE / SKEW history the dashboard's
Volatility tab reads from.

Unlike the factor snapshots (one dated CSV per day), this is a single,
continuously-updated time series file -- re-fetched and overwritten each
run, since Yahoo Finance is free and a full trailing year is a tiny
download. No point accumulating one near-duplicate file per day.

Usage:
    python scripts/run_volatility_snapshot.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seekingalpha_quant.data.volatility import fetch_volatility_history

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "volatility", "history.csv")


def main():
    df = fetch_volatility_history()
    if df.empty:
        sys.exit("No volatility data fetched from Yahoo Finance.")

    out_path = os.path.abspath(OUT_PATH)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path)
    print(f"Saved {len(df)} rows to {out_path}", file=sys.stderr)
    print(df.tail(3).to_string())


if __name__ == "__main__":
    main()
