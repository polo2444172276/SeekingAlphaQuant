"""Configuration for the Seeking Alpha Quant Rating replica.

Exact Seeking Alpha weights and percentile cutoffs are not publicly
disclosed. The values below are a documented, configurable approximation —
tune them in one place rather than scattering magic numbers through the
factor/scoring code.
"""

import os

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE_URL = "https://financialmodelingprep.com"

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")

# --- Metrics per factor -----------------------------------------------
# higher_is_better=False means the raw metric is inverted before ranking
# (e.g. a lower P/E is a better valuation score).
VALUATION_METRICS = {
    "pe_ratio": {"higher_is_better": False},
    "pb_ratio": {"higher_is_better": False},
    "ps_ratio": {"higher_is_better": False},
    "pcf_ratio": {"higher_is_better": False},
    "peg_ratio": {"higher_is_better": False},
    "ev_to_sales": {"higher_is_better": False},
    "ev_to_ebitda": {"higher_is_better": False},
}

GROWTH_METRICS = {
    "revenue_growth_yoy": {"higher_is_better": True},
    "revenue_growth_3y": {"higher_is_better": True},
    "revenue_growth_5y": {"higher_is_better": True},
    "eps_growth_yoy": {"higher_is_better": True},
    "eps_growth_3y": {"higher_is_better": True},
    "eps_growth_5y": {"higher_is_better": True},
    "ebitda_growth_yoy": {"higher_is_better": True},
}

PROFITABILITY_METRICS = {
    "gross_margin": {"higher_is_better": True},
    "operating_margin": {"higher_is_better": True},
    "net_margin": {"higher_is_better": True},
    "ebitda_margin": {"higher_is_better": True},
    "roe": {"higher_is_better": True},
    "roa": {"higher_is_better": True},
    "roic": {"higher_is_better": True},
}

MOMENTUM_METRICS = {
    "return_1m": {"higher_is_better": True},
    "return_3m": {"higher_is_better": True},
    "return_6m": {"higher_is_better": True},
    "return_9m": {"higher_is_better": True},
    "return_ytd": {"higher_is_better": True},
    "return_12m": {"higher_is_better": True},
}

# Proxy metrics — see plan/README for why this is not a true point-in-time
# consensus-estimate revision, only an analyst upgrade/downgrade proxy.
EPS_REVISIONS_METRICS = {
    "net_upgrades_1m": {"higher_is_better": True},
    "net_upgrades_3m": {"higher_is_better": True},
}

FACTOR_METRICS = {
    "valuation": VALUATION_METRICS,
    "growth": GROWTH_METRICS,
    "profitability": PROFITABILITY_METRICS,
    "momentum": MOMENTUM_METRICS,
    "eps_revisions": EPS_REVISIONS_METRICS,
}

# --- Combining factors into an overall rating ---------------------------
FACTOR_WEIGHTS = {
    "valuation": 0.20,
    "growth": 0.20,
    "profitability": 0.20,
    "momentum": 0.20,
    "eps_revisions": 0.20,
}

# Percentile (0-100, inclusive lower bound) -> letter grade, highest first.
GRADE_CUTOFFS = [
    (97, "A+"),
    (90, "A"),
    (80, "A-"),
    (70, "B+"),
    (60, "B"),
    (50, "B-"),
    (40, "C+"),
    (30, "C"),
    (20, "C-"),
    (15, "D+"),
    (10, "D"),
    (5, "D-"),
    (0, "F"),
]

# Percentile (0-100, inclusive lower bound) -> overall rating, highest first.
RATING_CUTOFFS = [
    (80, "Strong Buy"),
    (60, "Buy"),
    (40, "Hold"),
    (20, "Sell"),
    (0, "Strong Sell"),
]


def percentile_to_grade(percentile):
    for cutoff, grade in GRADE_CUTOFFS:
        if percentile >= cutoff:
            return grade
    return GRADE_CUTOFFS[-1][1]


def percentile_to_rating(percentile):
    for cutoff, rating in RATING_CUTOFFS:
        if percentile >= cutoff:
            return rating
    return RATING_CUTOFFS[-1][1]
