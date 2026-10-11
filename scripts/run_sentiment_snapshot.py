"""Daily job: refresh the CNN Fear & Greed snapshot the dashboard's
Sentiment tab reads from.

Single continuously-updated JSON file (not one dated file per day) --
same reasoning as run_volatility_snapshot.py, this is a time series
re-fetched in full each run, not a cross-sectional ranking.

Usage:
    python scripts/run_sentiment_snapshot.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seekingalpha_quant.data.sentiment import fetch_sentiment

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sentiment", "latest.json")


def main():
    snapshot = fetch_sentiment()

    out_path = os.path.abspath(OUT_PATH)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Saved sentiment snapshot to {out_path}", file=sys.stderr)
    print(f"Overall: {snapshot['overall']['score']} ({snapshot['overall']['rating']})")
    for c in snapshot["components"]:
        print(f"  {c['label']}: {c['score']} ({c['rating']})")


if __name__ == "__main__":
    main()
