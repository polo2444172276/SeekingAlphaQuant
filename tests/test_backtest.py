import datetime as dt

from seekingalpha_quant.backtest.fundamentals_pit import compute_point_in_time_row, latest_known_index
from seekingalpha_quant.backtest.membership import ever_members, reconstruct_membership
from seekingalpha_quant.data.estimates import _net_upgrades


def test_reconstruct_membership_undoes_future_events():
    current = {"A", "B", "C"}
    changes = [
        {"date": dt.date(2020, 1, 1), "action": "add", "ticker": "C"},
        {"date": dt.date(2020, 1, 1), "action": "remove", "ticker": "D"},
    ]
    # Before the event: C wasn't a member yet, D still was.
    before = reconstruct_membership(dt.date(2019, 12, 31), current, changes)
    assert "C" not in before
    assert "D" in before
    assert "A" in before and "B" in before

    # On/after the event date: matches current membership.
    after = reconstruct_membership(dt.date(2020, 1, 1), current, changes)
    assert after == current


def test_reconstruct_membership_multiple_events_same_ticker():
    # A ticker added, then removed, then added again -- reconstruction at
    # each point must reflect only events strictly after it.
    current = {"X"}
    changes = [
        {"date": dt.date(2020, 1, 1), "action": "add", "ticker": "X"},
        {"date": dt.date(2021, 1, 1), "action": "remove", "ticker": "X"},
        {"date": dt.date(2022, 1, 1), "action": "add", "ticker": "X"},
    ]
    assert "X" not in reconstruct_membership(dt.date(2019, 6, 1), current, changes)
    assert "X" in reconstruct_membership(dt.date(2020, 6, 1), current, changes)
    assert "X" not in reconstruct_membership(dt.date(2021, 6, 1), current, changes)
    assert "X" in reconstruct_membership(dt.date(2022, 6, 1), current, changes)


def test_ever_members_includes_removed_tickers():
    current = {"A", "B"}
    changes = [{"date": dt.date(2020, 1, 1), "action": "remove", "ticker": "Z"}]
    assert ever_members(current, changes) == {"A", "B", "Z"}


def test_net_upgrades_as_of_excludes_future_grades():
    grades = [
        {"date": "2020-01-15", "action": "upgrade"},
        {"date": "2020-06-15", "action": "upgrade"},  # after the as_of anchor below
    ]
    # A 90-day window anchored at 2020-02-01 should see the Jan upgrade but
    # not the later June one, even though both are within the *full*
    # grades list fetched once for the whole history.
    net = _net_upgrades(grades, days=91, as_of=dt.date(2020, 2, 1))
    assert net == 1


def test_net_upgrades_default_as_of_is_today():
    # Backward-compat: omitting as_of behaves like the live daily snapshot
    # (anchored on today), unaffected by the historical-backfill addition.
    old = (dt.date.today() - dt.timedelta(days=500)).isoformat()
    grades = [{"date": old, "action": "upgrade"}]
    assert _net_upgrades(grades, days=30) == 0


def _ttm_row(period_end, accepted_date, **overrides):
    row = {
        "period_end": period_end,
        "accepted_date": accepted_date,
        "ttm_revenue": 1000.0,
        "ttm_net_income": 100.0,
        "ttm_eps": 1.0,
        "ttm_ebitda": 150.0,
        "ttm_gross_profit": 400.0,
        "ttm_operating_income": 120.0,
        "ttm_income_tax_expense": 20.0,
        "ttm_pretax_income": 120.0,
        "ttm_operating_cash_flow": 110.0,
        "total_equity": 500.0,
        "total_assets": 900.0,
        "total_debt": 200.0,
        "cash": 50.0,
    }
    row.update(overrides)
    return row


def test_latest_known_index_respects_accepted_date():
    ttm = [
        _ttm_row(dt.date(2019, 3, 31), dt.date(2019, 5, 1)),
        _ttm_row(dt.date(2019, 6, 30), dt.date(2019, 8, 1)),
    ]
    # Before the 2nd quarter was actually filed: only quarter 0 is known.
    assert latest_known_index(ttm, dt.date(2019, 7, 1)) == 0
    # On/after its filing date: quarter 1 becomes known.
    assert latest_known_index(ttm, dt.date(2019, 8, 1)) == 1
    # Before anything was filed: nothing known yet.
    assert latest_known_index(ttm, dt.date(2019, 1, 1)) is None


def test_compute_point_in_time_row_valuation_and_margins():
    ttm = [_ttm_row(dt.date(2019, 3, 31), dt.date(2019, 5, 1))]
    row = compute_point_in_time_row(ttm, 0, market_cap=2000.0)

    assert row["pe_ratio"] == 2000.0 / 100.0
    assert row["pb_ratio"] == 2000.0 / 500.0
    assert row["ps_ratio"] == 2000.0 / 1000.0
    # enterprise_value = 2000 + 200 - 50 = 2150
    assert row["ev_to_sales"] == 2150.0 / 1000.0
    assert row["gross_margin"] == 400.0 / 1000.0
    assert row["net_margin"] == 100.0 / 1000.0
    assert row["roe"] == 100.0 / 500.0
    # No prior-year quarter available -> growth is None, not a crash.
    assert row["revenue_growth_yoy"] is None


def test_compute_point_in_time_row_growth_uses_trailing_quarter():
    ttm = [
        _ttm_row(dt.date(2018, 3, 31), dt.date(2018, 5, 1), ttm_revenue=800.0, ttm_eps=0.8),
        _ttm_row(dt.date(2018, 6, 30), dt.date(2018, 8, 1), ttm_revenue=800.0, ttm_eps=0.8),
        _ttm_row(dt.date(2018, 9, 30), dt.date(2018, 11, 1), ttm_revenue=800.0, ttm_eps=0.8),
        _ttm_row(dt.date(2018, 12, 31), dt.date(2019, 2, 1), ttm_revenue=800.0, ttm_eps=0.8),
        _ttm_row(dt.date(2019, 3, 31), dt.date(2019, 5, 1), ttm_revenue=1000.0, ttm_eps=1.0),
    ]
    row = compute_point_in_time_row(ttm, 4, market_cap=2000.0)
    # 4 quarters back (index 0): revenue 800 -> 1000 is +25%.
    assert round(row["revenue_growth_yoy"], 4) == 0.25
    assert round(row["eps_growth_yoy"], 4) == 0.25


def test_compute_point_in_time_row_missing_market_cap_is_none_not_crash():
    ttm = [_ttm_row(dt.date(2019, 3, 31), dt.date(2019, 5, 1))]
    row = compute_point_in_time_row(ttm, 0, market_cap=None)
    assert row["pe_ratio"] is None
    assert row["pb_ratio"] is None
    # Margins don't depend on market cap and should still compute.
    assert row["gross_margin"] == 400.0 / 1000.0
