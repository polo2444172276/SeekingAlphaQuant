import pandas as pd

from seekingalpha_quant.data.market_data import apply_registry


def _raw():
    d = pd.to_datetime(["2021-11-30", "2021-12-01", "2021-12-02", "2021-12-03"])
    a = pd.DataFrame({"security_id": 1, "date": d, "adj_close": [100, 92, 93, 94], "source": "fmp"})
    b = pd.DataFrame({"security_id": 2, "date": d, "adj_close": [10, 11, 12, 13], "source": "yahoo"})
    return pd.concat([a, b], ignore_index=True)


def test_no_issues_returns_raw():
    out = apply_registry(_raw(), pd.DataFrame(), pd.DataFrame())
    assert len(out) == 8 and out.issue_id.isna().all()


def test_override_replaces_range_only_for_that_security():
    issues = pd.DataFrame([{"id": 7, "security_id": 1, "action": "override",
                            "date_from": "2021-12-01", "date_to": "2021-12-02"}])
    ovr = pd.DataFrame({"security_id": 1, "date": ["2021-12-01", "2021-12-02"],
                        "adj_close": [99.0, 100.0], "source": "yahoo", "issue_id": 7})
    out = apply_registry(_raw(), issues, ovr)
    a = out[out.security_id == 1].set_index("date")
    assert a.adj_close.tolist() == [100, 99.0, 100.0, 94]
    assert a.source.tolist() == ["fmp", "yahoo", "yahoo", "fmp"]
    assert a.issue_id.tolist()[1:3] == [7, 7]
    assert out[out.security_id == 2].adj_close.tolist() == [10, 11, 12, 13]


def test_override_range_without_replacement_row_drops_raw():
    issues = pd.DataFrame([{"id": 7, "security_id": 1, "action": "override",
                            "date_from": "2021-12-01", "date_to": "2021-12-03"}])
    ovr = pd.DataFrame({"security_id": 1, "date": ["2021-12-01"], "adj_close": [99.0],
                        "source": "yahoo", "issue_id": 7})
    a = apply_registry(_raw(), issues, ovr).query("security_id == 1")
    assert a.adj_close.tolist() == [100, 99.0]


def test_exclude_open_ended_and_flag_noop():
    issues = pd.DataFrame([
        {"id": 1, "security_id": 2, "action": "exclude", "date_from": "2021-12-02", "date_to": None},
        {"id": 2, "security_id": 1, "action": "flag", "date_from": None, "date_to": None},
    ])
    out = apply_registry(_raw(), issues, pd.DataFrame())
    assert out[out.security_id == 2].adj_close.tolist() == [10, 11]
    assert len(out[out.security_id == 1]) == 4
