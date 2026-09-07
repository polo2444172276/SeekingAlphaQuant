from seekingalpha_quant.config import GROWTH_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the GROWTH_METRICS columns."""
    out = df[["ticker", sector_col]].copy()
    out["growth_score"] = compute_factor_score(df, GROWTH_METRICS, sector_col)
    out["growth_grade"] = out["growth_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
