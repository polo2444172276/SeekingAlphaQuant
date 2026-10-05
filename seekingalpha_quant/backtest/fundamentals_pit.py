"""Point-in-time TTM line items + historical market cap -> the exact raw
metric columns seekingalpha_quant.config.FACTOR_METRICS expects for
Valuation/Growth/Profitability, so factors/{valuation,growth,profitability}.py's
existing compute() functions run completely unmodified against historical
cross-sections.

FMP's Starter plan 402s the pre-computed historical ratio/key-metrics
endpoints, so every ratio here is derived by hand from raw statement line
items (seekingalpha_quant.backtest.statements) + historical market cap
(seekingalpha_quant.backtest.market_cap). Growth is self-computed from the
TTM series too, rather than trusting FMP's `financial-growth` endpoint --
confirmed live that its `period=quarter` growth fields are
quarter-over-quarter, not year-over-year, so they're not usable here.

All of this is a documented approximation, same status as the project's
existing documented approximations (EPS Revisions proxy, coarse FMP sector
buckets) -- most notably ROIC, which has no public FMP formula to match.
"""


def latest_known_index(ttm_series, as_of):
    """Index of the most recent TTM row whose accepted_date <= as_of (the
    quarter's numbers were actually public knowledge by that date), or
    None if nothing was known yet."""
    candidates = [i for i, row in enumerate(ttm_series) if row["accepted_date"] <= as_of]
    return max(candidates) if candidates else None


def _safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def _growth(current, prior, field):
    if prior is None:
        return None
    cur_v = current.get(field)
    prior_v = prior.get(field)
    if cur_v is None or prior_v in (None, 0):
        return None
    return cur_v / prior_v - 1


def compute_point_in_time_row(ttm_series, index, market_cap):
    """ttm_series: ascending (oldest first) list of dicts from
    statements.build_ttm_series(). index: position of the "current"
    quarter. market_cap: market cap as of that quarter's accepted_date.
    Returns a dict with exactly the keys VALUATION_METRICS |
    GROWTH_METRICS | PROFITABILITY_METRICS expect in config.py."""
    row = ttm_series[index]

    def lookback(n):
        j = index - n
        return ttm_series[j] if j >= 0 else None

    prior_yoy = lookback(4)   # 4 quarters = 1 year
    prior_3y = lookback(12)   # 12 quarters = 3 years
    prior_5y = lookback(20)   # 20 quarters = 5 years

    enterprise_value = None
    if None not in (market_cap, row.get("total_debt"), row.get("cash")):
        enterprise_value = market_cap + row["total_debt"] - row["cash"]

    eps_growth_yoy = _growth(row, prior_yoy, "ttm_eps")
    pe_ratio = _safe_div(market_cap, row.get("ttm_net_income"))
    peg_ratio = (
        pe_ratio / (eps_growth_yoy * 100)
        if pe_ratio is not None and eps_growth_yoy is not None and eps_growth_yoy > 0
        else None
    )

    roic = None
    if None not in (row.get("ttm_operating_income"), row.get("ttm_income_tax_expense")) \
            and row.get("ttm_pretax_income"):
        effective_tax_rate = min(max(row["ttm_income_tax_expense"] / row["ttm_pretax_income"], 0), 0.5)
        nopat = row["ttm_operating_income"] * (1 - effective_tax_rate)
        invested_capital = None
        if None not in (row.get("total_debt"), row.get("total_equity"), row.get("cash")):
            invested_capital = row["total_debt"] + row["total_equity"] - row["cash"]
        roic = _safe_div(nopat, invested_capital)

    return {
        # Valuation
        "pe_ratio": pe_ratio,
        "pb_ratio": _safe_div(market_cap, row.get("total_equity")),
        "ps_ratio": _safe_div(market_cap, row.get("ttm_revenue")),
        "pcf_ratio": _safe_div(market_cap, row.get("ttm_operating_cash_flow")),
        "peg_ratio": peg_ratio,
        "ev_to_sales": _safe_div(enterprise_value, row.get("ttm_revenue")),
        "ev_to_ebitda": _safe_div(enterprise_value, row.get("ttm_ebitda")),
        # Growth (self-computed rolling TTM growth, not FMP's financial-growth field)
        "revenue_growth_yoy": _growth(row, prior_yoy, "ttm_revenue"),
        "revenue_growth_3y": _growth(row, prior_3y, "ttm_revenue"),
        "revenue_growth_5y": _growth(row, prior_5y, "ttm_revenue"),
        "eps_growth_yoy": eps_growth_yoy,
        "eps_growth_3y": _growth(row, prior_3y, "ttm_eps"),
        "eps_growth_5y": _growth(row, prior_5y, "ttm_eps"),
        "ebitda_growth_yoy": _growth(row, prior_yoy, "ttm_ebitda"),
        # Profitability
        "gross_margin": _safe_div(row.get("ttm_gross_profit"), row.get("ttm_revenue")),
        "operating_margin": _safe_div(row.get("ttm_operating_income"), row.get("ttm_revenue")),
        "net_margin": _safe_div(row.get("ttm_net_income"), row.get("ttm_revenue")),
        "ebitda_margin": _safe_div(row.get("ttm_ebitda"), row.get("ttm_revenue")),
        "roe": _safe_div(row.get("ttm_net_income"), row.get("total_equity")),
        "roa": _safe_div(row.get("ttm_net_income"), row.get("total_assets")),
        "roic": roic,
    }
