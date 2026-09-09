"""Refresh data/sp500_constituents.csv from a community-maintained source.

FMP's own sp500-constituent endpoint 402s even on the paid Starter plan (see
README's "Known FMP plan gap"), so the ticker/sector list itself comes from
a separate, free, non-FMP source instead. Run this occasionally (S&P 500
membership changes only a few times a year) -- not on every snapshot.

Usage:
    python scripts/update_universe.py
"""

import csv
import io
import os
import sys

import requests

SOURCE_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "main/data/constituents.csv"
)
OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "sp500_constituents.csv"
)


def main():
    resp = requests.get(SOURCE_URL, timeout=30)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for row in reader:
        # FMP uses a dash for the share-class separator (BRK-B), this source
        # uses a dot (BRK.B).
        ticker = row["Symbol"].strip().replace(".", "-")
        rows.append({
            "ticker": ticker,
            "name": row["Security"],
            "sector": row["GICS Sector"],
        })
    rows.sort(key=lambda r: r["ticker"])

    out_path = os.path.abspath(OUT_PATH)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "name", "sector"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} tickers to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
