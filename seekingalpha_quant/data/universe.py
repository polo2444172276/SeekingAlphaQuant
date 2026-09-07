"""Ticker universe for the daily snapshot.

Full point-in-time S&P 500 reconstruction (data/universe.py per the plan
doc) needs FMP's sp500-constituent endpoint, which is paywalled on the
free tier. Until that's available (or a different source is added), this
is a hand-maintained watchlist — edit freely to track whatever names you
care about.
"""

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "WMT", "PG", "MA", "HD", "CVX", "ABBV", "MRK", "KO",
    "PEP", "COST", "AVGO", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "LIN",
]
