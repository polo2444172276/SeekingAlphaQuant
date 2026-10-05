"""Quarterly + daily point-in-time panel builders.

Takes per-ticker data that's already been fetched (scripts/run_backtest.py
does the I/O) and assembles cross-sectional DataFrames at each
rebalance/trading date, reusing the existing factor-scoring code
(factors/*.compute(), scoring.combine.combine_factors) completely
unmodified -- these modules' only job is producing correctly-shaped input.

Two separate resolutions, per the project's requirement:
- Valuation/Growth/Profitability/EPS Revisions: quarterly (build_quarterly_panel)
- Momentum, and therefore the combined overall score: daily
  (build_daily_panel), carrying forward each ticker's latest *known*
  quarterly fundamentals rather than recomputing them every day.
"""

import pandas as pd

from seekingalpha_quant.backtest.fundamentals_pit import compute_point_in_time_row, latest_known_index
from seekingalpha_quant.backtest.market_cap import market_cap_as_of
from seekingalpha_quant.backtest.membership import reconstruct_membership
from seekingalpha_quant.data.estimates import _net_upgrades
from seekingalpha_quant.factors import eps_revisions, growth, momentum, profitability, valuation
from seekingalpha_quant.scoring.combine import combine_factors

QUARTERLY_FACTOR_COLS = [
    "valuation_score", "valuation_grade",
    "growth_score", "growth_grade",
    "profitability_score", "profitability_grade",
    "eps_revisions_score", "eps_revisions_grade",
]


def quarterly_rebalance_dates(start, end):
    """Calendar quarter-end dates from `start` through the latest one
    on/before `end`."""
    return [d.date() for d in pd.date_range(start, end, freq="QE")]


def build_quarterly_panel(rebalance_dates, ticker_data, current_members, changes):
    """ticker_data: {ticker: {"ttm": [...], "sector": str,
    "mc_history": [...], "grades": [...] or None}} (see
    statements.build_ttm_series / market_cap.fetch_market_cap_history).

    Returns one DataFrame, one row per (rebalance_date, ticker): raw metric
    columns + valuation/growth/profitability/eps_revisions score+grade
    (NOT momentum, NOT overall -- daily-only, see build_daily_panel).
    """
    frames = []
    for r_date in rebalance_dates:
        active = reconstruct_membership(r_date, current_members, changes)
        rows = []
        for ticker in sorted(active):
            data = ticker_data.get(ticker)
            if not data or not data.get("ttm"):
                continue
            idx = latest_known_index(data["ttm"], r_date)
            if idx is None:
                continue
            mc = market_cap_as_of(data["mc_history"], r_date)
            rows.append({
                "ticker": ticker,
                "sector": data["sector"],
                "fundamentals_accepted_date": data["ttm"][idx]["accepted_date"],
                **compute_point_in_time_row(data["ttm"], idx, mc),
                "net_upgrades_1m": _net_upgrades(data["grades"], 30, as_of=r_date),
                "net_upgrades_3m": _net_upgrades(data["grades"], 91, as_of=r_date),
            })
        if not rows:
            continue

        cross_section = pd.DataFrame(rows)
        val = valuation.compute(cross_section)
        gro = growth.compute(cross_section)
        prof = profitability.compute(cross_section)
        eps = eps_revisions.compute(cross_section)

        merged = cross_section
        for factor_df in (val, gro, prof, eps):
            score_grade_cols = [c for c in factor_df.columns if c not in ("ticker", "sector")]
            merged = merged.merge(factor_df[["ticker"] + score_grade_cols], on="ticker")
        merged.insert(0, "rebalance_date", r_date)
        frames.append(merged)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_daily_panel(trading_dates, quarterly_df, daily_returns, current_members, changes):
    """daily_returns: {ticker: DataFrame indexed by date with return_1m..
    return_12m/return_ytd (see momentum_pit.build_daily_returns)}.
    quarterly_df: output of build_quarterly_panel.

    Returns one DataFrame, one row per (date, ticker): momentum (fresh,
    every day) + the latest *known-as-of-that-day* quarterly fundamentals
    (carried forward, not recomputed) + overall_score/overall_rating via
    the existing combine_factors().
    """
    quarterly_by_ticker = {
        ticker: grp.sort_values("rebalance_date").to_dict("records")
        for ticker, grp in quarterly_df.groupby("ticker")
    }

    frames = []
    for d in trading_dates:
        active = reconstruct_membership(d, current_members, changes)

        mom_rows = []
        for ticker in sorted(active):
            ret_df = daily_returns.get(ticker)
            if ret_df is None or d not in ret_df.index:
                continue
            r = ret_df.loc[d]
            mom_rows.append({
                "ticker": ticker,
                "return_1m": r["return_1m"], "return_3m": r["return_3m"],
                "return_6m": r["return_6m"], "return_9m": r["return_9m"],
                "return_12m": r["return_12m"], "return_ytd": r["return_ytd"],
            })
        if not mom_rows:
            continue
        mom_df = pd.DataFrame(mom_rows)

        fund_rows = []
        for ticker in mom_df["ticker"]:
            hist = quarterly_by_ticker.get(ticker)
            if not hist:
                continue
            candidates = [h for h in hist if h["rebalance_date"] <= d]
            if not candidates:
                continue
            latest = candidates[-1]
            fund_rows.append({
                "ticker": ticker,
                "sector": latest["sector"],
                "fundamentals_rebalance_date": latest["rebalance_date"],
                **{c: latest[c] for c in QUARTERLY_FACTOR_COLS},
            })
        if not fund_rows:
            continue
        fund_df = pd.DataFrame(fund_rows)

        cross_section = mom_df.merge(fund_df, on="ticker", how="inner")
        if cross_section.empty:
            continue

        mom_scored = momentum.compute(cross_section)
        cross_section = cross_section.merge(
            mom_scored[["ticker", "momentum_score", "momentum_grade"]], on="ticker"
        )

        factor_frames = {
            f: cross_section[["ticker", "sector", f"{f}_score", f"{f}_grade"]]
            for f in ("valuation", "growth", "profitability", "momentum", "eps_revisions")
        }
        combined = combine_factors(factor_frames)
        combined = combined.merge(
            cross_section[[
                "ticker", "return_1m", "return_3m", "return_6m", "return_9m",
                "return_12m", "return_ytd", "fundamentals_rebalance_date",
            ]],
            on="ticker",
        )
        combined.insert(0, "date", d)
        frames.append(combined)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
