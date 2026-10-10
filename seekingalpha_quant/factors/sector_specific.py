from seekingalpha_quant.config import SECTOR_SPECIFIC_METRICS, percentile_to_grade
from seekingalpha_quant.factors.base import compute_factor_score


def compute(df, sector_col="sector"):
    """df must contain 'ticker', sector_col, and the SECTOR_SPECIFIC_METRICS
    columns (see seekingalpha_quant/data/sector_specific.py). Each metric is
    only populated for the sector(s) it applies to, so a ticker in a
    not-yet-covered sector naturally scores None instead of 0."""
    out = df[["ticker", sector_col]].copy()
    out["sector_specific_score"] = compute_factor_score(df, SECTOR_SPECIFIC_METRICS, sector_col)
    out["sector_specific_grade"] = out["sector_specific_score"].apply(
        lambda p: percentile_to_grade(p) if p == p else None
    )
    return out
