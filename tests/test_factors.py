import numpy as np
import pandas as pd

from seekingalpha_quant.factors.base import compute_factor_score, sector_percentile
from seekingalpha_quant.factors import eps_revisions, growth, momentum, profitability, valuation


def test_sector_percentile_higher_is_better():
    value = pd.Series([10, 20, 30, 100, 200, 300])
    sector = pd.Series(["Tech", "Tech", "Tech", "Energy", "Energy", "Energy"])
    pct = sector_percentile(value, sector, higher_is_better=True)
    # Within each 3-stock sector, ranks are 1/3, 2/3, 3/3 -> 33.3, 66.7, 100
    assert pct.iloc[0] < pct.iloc[1] < pct.iloc[2]
    assert pct.iloc[2] == 100.0
    assert pct.iloc[3] < pct.iloc[4] < pct.iloc[5]


def test_sector_percentile_lower_is_better_inverts():
    value = pd.Series([10, 20, 30])
    sector = pd.Series(["Tech", "Tech", "Tech"])
    higher = sector_percentile(value, sector, higher_is_better=True)
    lower = sector_percentile(value, sector, higher_is_better=False)
    # value[0]=10 is the smallest: worst rank when higher is better,
    # best rank when lower is better.
    assert higher.iloc[0] < lower.iloc[0]
    assert higher.iloc[2] > lower.iloc[2]


def test_sector_percentile_preserves_nan():
    value = pd.Series([10, np.nan, 30])
    sector = pd.Series(["Tech", "Tech", "Tech"])
    pct = sector_percentile(value, sector, higher_is_better=True)
    assert pd.isna(pct.iloc[1])


def test_compute_factor_score_ignores_missing_metrics_per_row():
    df = pd.DataFrame(
        {
            "sector": ["Tech", "Tech", "Tech"],
            "a": [1, 2, 3],
            "b": [np.nan, 20, 30],
        }
    )
    metrics = {"a": {"higher_is_better": True}, "b": {"higher_is_better": True}}
    score = compute_factor_score(df, metrics)
    # Row 0 only has metric 'a' populated; score should still be computed
    # from that single metric rather than becoming NaN.
    assert not pd.isna(score.iloc[0])
    assert len(score) == 3


def test_valuation_compute_lower_pe_scores_higher():
    df = pd.DataFrame(
        {
            "ticker": ["CHEAP", "MID", "EXPENSIVE"],
            "sector": ["Tech", "Tech", "Tech"],
            "pe_ratio": [10, 20, 30],
            "pb_ratio": [1, 2, 3],
            "ps_ratio": [1, 2, 3],
            "pcf_ratio": [1, 2, 3],
            "peg_ratio": [1, 2, 3],
            "ev_to_sales": [1, 2, 3],
            "ev_to_ebitda": [1, 2, 3],
        }
    )
    out = valuation.compute(df)
    cheap_score = out.loc[out["ticker"] == "CHEAP", "valuation_score"].iloc[0]
    expensive_score = out.loc[out["ticker"] == "EXPENSIVE", "valuation_score"].iloc[0]
    assert cheap_score > expensive_score
    assert out.loc[out["ticker"] == "CHEAP", "valuation_grade"].iloc[0] is not None


def test_growth_compute_higher_growth_scores_higher():
    df = pd.DataFrame(
        {
            "ticker": ["SLOW", "FAST"],
            "sector": ["Tech", "Tech"],
            "revenue_growth_yoy": [0.01, 0.30],
            "revenue_growth_3y": [0.01, 0.30],
            "revenue_growth_5y": [0.01, 0.30],
            "eps_growth_yoy": [0.01, 0.30],
            "eps_growth_3y": [0.01, 0.30],
            "eps_growth_5y": [0.01, 0.30],
            "ebitda_growth_yoy": [0.01, 0.30],
        }
    )
    out = growth.compute(df)
    slow = out.loc[out["ticker"] == "SLOW", "growth_score"].iloc[0]
    fast = out.loc[out["ticker"] == "FAST", "growth_score"].iloc[0]
    assert fast > slow


def test_profitability_and_momentum_and_eps_revisions_smoke():
    prof_df = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "sector": ["Tech", "Tech"],
            "gross_margin": [0.3, 0.6],
            "operating_margin": [0.1, 0.2],
            "net_margin": [0.05, 0.15],
            "ebitda_margin": [0.1, 0.25],
            "roe": [0.1, 0.2],
            "roa": [0.05, 0.1],
            "roic": [0.05, 0.15],
        }
    )
    prof_out = profitability.compute(prof_df)
    assert set(["ticker", "sector", "profitability_score", "profitability_grade"]) <= set(
        prof_out.columns
    )

    mom_df = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "sector": ["Tech", "Tech"],
            "return_1m": [0.01, 0.05],
            "return_3m": [0.01, 0.05],
            "return_6m": [0.01, 0.05],
            "return_9m": [0.01, 0.05],
            "return_ytd": [0.01, 0.05],
            "return_12m": [0.01, 0.05],
        }
    )
    mom_out = momentum.compute(mom_df)
    assert mom_out.loc[mom_out["ticker"] == "B", "momentum_score"].iloc[0] > mom_out.loc[
        mom_out["ticker"] == "A", "momentum_score"
    ].iloc[0]

    eps_df = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "sector": ["Tech", "Tech"],
            "net_upgrades_1m": [-2, 3],
            "net_upgrades_3m": [-5, 8],
        }
    )
    eps_out = eps_revisions.compute(eps_df)
    assert eps_out.loc[eps_out["ticker"] == "B", "eps_revisions_score"].iloc[0] > eps_out.loc[
        eps_out["ticker"] == "A", "eps_revisions_score"
    ].iloc[0]
