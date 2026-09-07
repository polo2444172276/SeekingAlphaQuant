"""EPS Revisions factor — PROXY implementation.

Seeking Alpha's real EPS Revisions factor tracks how a stock's consensus
EPS estimate has changed over time (e.g. the estimate 30/90 days ago vs.
today). FMP does not expose historical point-in-time consensus snapshots,
and true sell-side revision history vendors (Zacks/Nasdaq Data Link,
Intrinio's Zacks bundle, Estimize) were deliberately not integrated for
this project (see plan doc). Instead this factor proxies revision momentum
with net analyst upgrades minus downgrades over trailing windows. Treat
this factor's output as directionally useful, not a faithful replica.
"""

from seekingalpha_quant.config import EPS_REVISIONS_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the EPS_REVISIONS_METRICS columns."""
    out = df[["ticker", sector_col]].copy()
    out["eps_revisions_score"] = compute_factor_score(df, EPS_REVISIONS_METRICS, sector_col)
    out["eps_revisions_grade"] = out["eps_revisions_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
