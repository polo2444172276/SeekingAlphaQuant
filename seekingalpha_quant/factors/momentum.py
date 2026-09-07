from seekingalpha_quant.config import MOMENTUM_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the MOMENTUM_METRICS columns."""
    out = df[["ticker", sector_col]].copy()
    out["momentum_score"] = compute_factor_score(df, MOMENTUM_METRICS, sector_col)
    out["momentum_grade"] = out["momentum_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
