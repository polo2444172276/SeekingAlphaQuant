"""Refresh data/sp500_membership_changes.csv from a community-maintained source.

FMP has no point-in-time S&P 500 membership endpoint at any tier we've
tried, so historical add/remove events come from a separate free source
instead. Run this occasionally (a handful of reconstitution events a
year) -- not on every snapshot.

Usage:
    python scripts/update_membership_history.py
"""

import csv
import io
import os
import sys

import requests

SOURCE_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/"
    "master/sp500_changes_since_2019.csv"
)
OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "sp500_membership_changes.csv"
)


def _split_tickers(cell):
    # Cell is empty, a single ticker, or a quoted comma-list e.g. "CTVA,DD".
    # Same dash-for-dot normalization as update_universe.py (FMP uses BRK-B,
    # this source style uses BRK.B for share classes).
    if not cell:
        return []
    return [t.strip().replace(".", "-") for t in cell.split(",") if t.strip()]


def main():
    resp = requests.get(SOURCE_URL, timeout=30)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for row in reader:
        added = _split_tickers(row["add"])
        removed = _split_tickers(row["remove"])
        for ticker in added:
            rows.append({"date": row["date"], "action": "add", "ticker": ticker})
        for ticker in removed:
            rows.append({"date": row["date"], "action": "remove", "ticker": ticker})
    rows.sort(key=lambda r: (r["date"], r["action"], r["ticker"]))

    out_path = os.path.abspath(OUT_PATH)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "action", "ticker"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} membership-change events to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
