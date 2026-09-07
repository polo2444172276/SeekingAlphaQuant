from seekingalpha_quant.config import PROFITABILITY_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the PROFITABILITY_METRICS columns."""
    out = df[["ticker", sector_col]].copy()
    out["profitability_score"] = compute_factor_score(df, PROFITABILITY_METRICS, sector_col)
    out["profitability_grade"] = out["profitability_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
