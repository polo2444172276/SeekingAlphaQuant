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

# One metric per sector, each only populated for the sector(s) it applies
# to (every other row is NaN for that column) -- sector_percentile ranks
# within-sector and treats NaN as "no opinion", so a ticker in a
# not-yet-covered sector (Energy, Industrials, Basic Materials, Utilities)
# just gets sector_specific_score = None rather than a penalized 0.
# See seekingalpha_quant/data/sector_specific.py for how each is computed
# and why the others (same-store sales, SaaS net-revenue-retention,
# regulated utility ROE, O&G reserves) aren't -- they aren't in any
# standard financial statement, so there's nothing to compute from FMP.
SECTOR_SPECIFIC_METRICS = {
    "rule_of_40": {"higher_is_better": True},        # Technology, Communication Services
    "nim_proxy": {"higher_is_better": True},          # Financial Services
    "ffo_margin": {"higher_is_better": True},         # Real Estate
    "rd_intensity": {"higher_is_better": True},       # Healthcare
    "inventory_turnover": {"higher_is_better": True}, # Consumer Cyclical, Consumer Defensive
}

FACTOR_METRICS = {
    "valuation": VALUATION_METRICS,
    "growth": GROWTH_METRICS,
    "profitability": PROFITABILITY_METRICS,
    "momentum": MOMENTUM_METRICS,
    "eps_revisions": EPS_REVISIONS_METRICS,
    "sector_specific": SECTOR_SPECIFIC_METRICS,
}

# --- Combining factors into an overall rating ---------------------------
# Equal-weighted across all six -- sector_specific is missing (None) for
# roughly a third of sectors, but combine_factors() already renormalizes
# over whichever factors are present per ticker, same as any other
# missing-data case.
FACTOR_WEIGHTS = {
    "valuation": 1 / 6,
    "growth": 1 / 6,
    "profitability": 1 / 6,
    "momentum": 1 / 6,
    "eps_revisions": 1 / 6,
    "sector_specific": 1 / 6,
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


# --- Small-cap / "under the radar" screen -------------------------------
# Thresholds for scripts/run_smallcap_snapshot.py's coverage+liquidity
# screen (not part of the 5-factor Quant Rating weighting -- these filter
# which rows are worth a human's attention, they don't affect any score).
SMALLCAP_MAX_COVERAGE = 5          # total analyst ratings outstanding (grades-consensus)
SMALLCAP_MIN_DOLLAR_VOLUME = 5_000_000  # trailing-20-day average $ volume


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
