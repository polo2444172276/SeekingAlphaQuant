"""Combine the five per-factor scores into one overall Quant Rating."""

import functools

import pandas as pd

from seekingalpha_quant.config import FACTOR_WEIGHTS, percentile_to_rating

FACTORS = ("valuation", "growth", "profitability", "momentum", "eps_revisions", "sector_specific")


def combine_factors(factor_frames, sector_col="sector"):
    """factor_frames: {factor_name: DataFrame(ticker, sector_col, f'{factor_name}_score', f'{factor_name}_grade')}

    Returns one DataFrame keyed by ticker with every factor's score/grade,
    plus overall_score (weighted average of factor scores, ignoring any
    factor missing for a given ticker and renormalizing the weights that
    are present) and overall_rating.
    """
    missing = set(FACTORS) - set(factor_frames)
    if missing:
        raise ValueError(f"missing factor frames: {sorted(missing)}")

    merged = functools.reduce(
        lambda left, right: pd.merge(left, right, on=["ticker", sector_col], how="outer"),
        (factor_frames[f] for f in FACTORS),
    )

    score_cols = [f"{f}_score" for f in FACTORS]
    weights = pd.Series({f"{f}_score": FACTOR_WEIGHTS[f] for f in FACTORS})

    scores = merged[score_cols]
    present_weight = scores.notna().mul(weights, axis=1).sum(axis=1)
    weighted_sum = scores.mul(weights, axis=1).sum(axis=1, skipna=True)
    # float("nan"), not pd.NA: keeps `overall` a plain float64 Series so the
    # `p == p` NaN-check below (NaN != NaN) works instead of raising on
    # pd.NA's ambiguous boolean value.
    overall = weighted_sum / present_weight.replace(0, float("nan"))

    merged["overall_score"] = overall
    merged["overall_rating"] = merged["overall_score"].apply(
        lambda p: percentile_to_rating(p) if p == p else None
    )
    return merged
