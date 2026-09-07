from seekingalpha_quant.config import VALUATION_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the VALUATION_METRICS columns."""
    out = df[["ticker", sector_col]].copy()
    out["valuation_score"] = compute_factor_score(df, VALUATION_METRICS, sector_col)
    out["valuation_grade"] = out["valuation_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
