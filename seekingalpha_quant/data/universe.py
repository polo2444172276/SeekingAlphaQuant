"""Ticker universe for the daily snapshot.

Full S&P 500 constituent list, read from data/sp500_constituents.csv.
FMP's own sp500-constituent endpoint 402s even on the paid Starter plan, so
that file is populated from a separate free source instead (see
scripts/update_universe.py) and only refreshed occasionally, not on every
snapshot run. Falls back to a small hand-maintained watchlist if the CSV
hasn't been generated yet.
"""

import csv
import os

_CONSTITUENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "sp500_constituents.csv",
)

_FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "WMT", "PG", "MA", "HD", "CVX", "ABBV", "MRK", "KO",
    "PEP", "COST", "AVGO", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "LIN",
]


def _load_tickers():
    if not os.path.exists(_CONSTITUENTS_PATH):
        return list(_FALLBACK_TICKERS)
    with open(_CONSTITUENTS_PATH, newline="") as f:
        return [row["ticker"] for row in csv.DictReader(f)]


TICKERS = _load_tickers()
