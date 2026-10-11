"""CNN Fear & Greed Index and its 7 components.

Not an official/documented API -- this is the same undocumented JSON
endpoint CNN's own fear-and-greed page calls client-side
(production.dataviz.cnn.io), widely relied on by open-source trackers.
It 418s without a browser-like User-Agent + Referer, and CNN could change
or kill it without notice -- callers should treat failures as expected
and non-fatal (see scripts/run_sentiment_snapshot.py).

The raw payload has 9 sub-series, but market_momentum_sp500/sp125 share
one score (S&P 500 vs its 125-day average) and market_volatility_vix/
vix_50 share one score (VIX vs its 50-day average) -- those are each a
single CNN-defined component, just exposing both the raw series and the
moving-average series it's computed against. COMPONENTS below collapses
them back down to the actual 7.
"""

import datetime as dt

import requests

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Accept": "application/json, text/plain, */*",
}

COMPONENTS = [
    {"key": "market_momentum_sp500", "label": "Market Momentum"},
    {"key": "stock_price_strength", "label": "Stock Price Strength"},
    {"key": "stock_price_breadth", "label": "Stock Price Breadth"},
    {"key": "put_call_options", "label": "Put and Call Options"},
    {"key": "market_volatility_vix", "label": "Market Volatility"},
    {"key": "junk_bond_demand", "label": "Junk Bond Demand"},
    {"key": "safe_haven_demand", "label": "Safe Haven Demand"},
]


def fetch_sentiment(timeout=20):
    """Returns {"date", "overall": {...}, "components": [...]}."""
    response = requests.get(URL, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    fg = data["fear_and_greed"]
    historical = [
        {
            "date": dt.datetime.utcfromtimestamp(point["x"] / 1000).date().isoformat(),
            "score": point["y"],
        }
        for point in data["fear_and_greed_historical"]["data"]
    ]

    components = []
    for c in COMPONENTS:
        sub = data[c["key"]]
        components.append({
            "key": c["key"],
            "label": c["label"],
            "score": round(sub["score"], 1),
            "rating": sub["rating"],
        })

    return {
        "date": dt.datetime.utcfromtimestamp(data["fear_and_greed_historical"]["timestamp"] / 1000)
        .date()
        .isoformat(),
        "overall": {
            "score": round(fg["score"], 1),
            "rating": fg["rating"],
            "previous_close": round(fg["previous_close"], 1),
            "previous_1_week": round(fg["previous_1_week"], 1),
            "previous_1_month": round(fg["previous_1_month"], 1),
            "previous_1_year": round(fg["previous_1_year"], 1),
            "historical": historical,
        },
        "components": components,
    }
