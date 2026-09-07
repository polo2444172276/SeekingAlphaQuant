import pandas as pd
import pytest

from seekingalpha_quant.config import percentile_to_grade, percentile_to_rating
from seekingalpha_quant.scoring.combine import combine_factors


def _factor_frame(factor, ticker_scores, sector="Tech"):
    tickers = list(ticker_scores)
    scores = [ticker_scores[t] for t in tickers]
    return pd.DataFrame(
        {
            "ticker": tickers,
            "sector": [sector] * len(tickers),
            f"{factor}_score": scores,
            f"{factor}_grade": [percentile_to_grade(s) for s in scores],
        }
    )


def test_percentile_to_grade_boundaries():
    assert percentile_to_grade(100) == "A+"
    assert percentile_to_grade(97) == "A+"
    assert percentile_to_grade(96.9) == "A"
    assert percentile_to_grade(0) == "F"
    assert percentile_to_grade(4.9) == "F"


def test_percentile_to_rating_boundaries():
    assert percentile_to_rating(100) == "Strong Buy"
    assert percentile_to_rating(80) == "Strong Buy"
    assert percentile_to_rating(79.9) == "Buy"
    assert percentile_to_rating(0) == "Strong Sell"


def test_combine_factors_all_present_equal_weight():
    frames = {
        "valuation": _factor_frame("valuation", {"AAA": 90, "BBB": 10}),
        "growth": _factor_frame("growth", {"AAA": 90, "BBB": 10}),
        "profitability": _factor_frame("profitability", {"AAA": 90, "BBB": 10}),
        "momentum": _factor_frame("momentum", {"AAA": 90, "BBB": 10}),
        "eps_revisions": _factor_frame("eps_revisions", {"AAA": 90, "BBB": 10}),
    }
    combined = combine_factors(frames)

    aaa = combined.loc[combined["ticker"] == "AAA"].iloc[0]
    bbb = combined.loc[combined["ticker"] == "BBB"].iloc[0]

    assert aaa["overall_score"] == pytest.approx(90)
    assert bbb["overall_score"] == pytest.approx(10)
    assert aaa["overall_rating"] == "Strong Buy"
    assert bbb["overall_rating"] == "Strong Sell"


def test_combine_factors_missing_factor_for_one_ticker_renormalizes():
    frames = {
        "valuation": _factor_frame("valuation", {"AAA": 100, "BBB": 100}),
        "growth": _factor_frame("growth", {"AAA": 100, "BBB": 100}),
        "profitability": _factor_frame("profitability", {"AAA": 100, "BBB": 100}),
        "momentum": _factor_frame("momentum", {"AAA": 100, "BBB": 100}),
        # BBB has no eps_revisions coverage at all
        "eps_revisions": _factor_frame("eps_revisions", {"AAA": 100}),
    }
    combined = combine_factors(frames)
    bbb = combined.loc[combined["ticker"] == "BBB"].iloc[0]
    # BBB's other 4 factors are all 100, so its renormalized overall score
    # should still be 100, not dragged down by a missing (not zero) factor.
    assert bbb["overall_score"] == pytest.approx(100)


def test_combine_factors_all_factors_missing_gives_nan_not_a_crash():
    # A ticker with zero factor coverage at all (e.g. a symbol the data
    # provider won't serve any endpoint for) must produce NaN score/rating,
    # not raise when computing overall_rating.
    nan = float("nan")
    frames = {
        "valuation": _factor_frame("valuation", {"AAA": 100, "GATED": nan}),
        "growth": _factor_frame("growth", {"AAA": 100, "GATED": nan}),
        "profitability": _factor_frame("profitability", {"AAA": 100, "GATED": nan}),
        "momentum": _factor_frame("momentum", {"AAA": 100, "GATED": nan}),
        "eps_revisions": _factor_frame("eps_revisions", {"AAA": 100, "GATED": nan}),
    }
    combined = combine_factors(frames)
    gated = combined.loc[combined["ticker"] == "GATED"].iloc[0]
    assert pd.isna(gated["overall_score"])
    assert gated["overall_rating"] is None


def test_combine_factors_raises_on_missing_factor_key():
    frames = {
        "valuation": _factor_frame("valuation", {"AAA": 90}),
    }
    with pytest.raises(ValueError):
        combine_factors(frames)
