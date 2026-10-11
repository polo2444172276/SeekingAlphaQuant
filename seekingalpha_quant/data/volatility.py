"""Daily close history for market-wide volatility/risk gauges -- VIX, the
ICE BofA MOVE index, and the CBOE SKEW index (the standard tradable proxy
for options-market tail-risk/put-call skew) -- via free Yahoo Finance data.

Not on FMP: the Starter plan 402s both ^MOVE and ^SKEW quotes/history
("Premium Query Parameter"), and its options-chain endpoints return an
empty list for every symbol tried (AAPL/SPY/QQQ) -- no FMP-based skew
metric is reachable under the current plan. Yahoo has all three for free,
so this module skips FMP entirely and doesn't touch its request quota.
"""

import pandas as pd
import yfinance as yf

SYMBOLS = {"vix": "^VIX", "move": "^MOVE", "skew": "^SKEW"}


def fetch_volatility_history(period="1y"):
    """Returns a DataFrame indexed by date with columns vix/move/skew.

    A symbol that fails to fetch (e.g. a transient Yahoo hiccup) is simply
    omitted as a column rather than failing the whole snapshot.
    """
    series = {}
    for col, symbol in SYMBOLS.items():
        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty:
            continue
        close = hist["Close"]
        close.index = close.index.tz_localize(None).normalize()
        series[col] = close

    if not series:
        return pd.DataFrame(columns=["vix", "move", "skew"])

    df = pd.DataFrame(series)
    df.index.name = "date"
    return df.sort_index()
