"""Shared sector-relative percentile ranking used by every factor."""

import pandas as pd


def sector_percentile(series, sector, higher_is_better=True):
    """Rank each value within its sector group as a 0-100 percentile.

    NaNs are ignored for ranking purposes and returned as NaN (a missing
    metric should not silently count against or for a stock).
    """
    df = pd.DataFrame({"value": series, "sector": sector})
    ranked = df.groupby("sector")["value"].rank(pct=True, na_option="keep")
    percentile = ranked * 100
    if not higher_is_better:
        percentile = 100 - percentile
    return percentile


def compute_factor_score(df, metrics, sector_col="sector"):
    """Combine a set of raw metric columns into one 0-100 factor score.

    `metrics` is a {column_name: {"higher_is_better": bool}} mapping, e.g.
    seekingalpha_quant.config.VALUATION_METRICS. Equal-weights the metric
    percentiles present for a given row and ignores missing ones, rather
    than requiring every metric to be populated.
    """
    percentile_cols = []
    for column, spec in metrics.items():
        pct_col = f"_pct_{column}"
        df[pct_col] = sector_percentile(
            df[column], df[sector_col], higher_is_better=spec["higher_is_better"]
        )
        percentile_cols.append(pct_col)

    score = df[percentile_cols].mean(axis=1, skipna=True)
    df = df.drop(columns=percentile_cols)
    return score
