from seekingalpha_quant.data.sector_specific import fetch_ticker_row


class _StubClient:
    """Dispatches by endpoint path, like FMPClient but with no network."""

    def __init__(self, income=None, balance=None):
        self._income = income or {}
        self._balance = balance or {}

    def get(self, path, params=None, **kwargs):
        if path == "/stable/income-statement":
            return [self._income]
        if path == "/stable/balance-sheet-statement":
            return [self._balance]
        raise AssertionError(f"unexpected path {path}")


class _FailingClient:
    def get(self, path, params=None, **kwargs):
        raise AssertionError("should not be called for an uncovered sector")


def test_uncovered_sector_skips_fetch_entirely():
    # Energy/Industrials/Basic Materials/Utilities have no defined metric --
    # fetch_ticker_row should bail out before making any API call at all.
    row = fetch_ticker_row(_FailingClient(), "XOM", "Energy")
    assert row == {
        "ticker": "XOM", "rule_of_40": None, "nim_proxy": None,
        "ffo_margin": None, "rd_intensity": None, "inventory_turnover": None,
    }


def test_real_estate_ffo_margin():
    client = _StubClient(income={"revenue": 1000, "netIncome": 200, "depreciationAndAmortization": 400})
    row = fetch_ticker_row(client, "O", "Real Estate")
    assert row["ffo_margin"] == (200 + 400) / 1000
    assert row["nim_proxy"] is None


def test_financial_services_nim_proxy():
    client = _StubClient(income={"netInterestIncome": 50}, balance={"totalAssets": 2000})
    row = fetch_ticker_row(client, "JPM", "Financial Services")
    assert row["nim_proxy"] == 50 / 2000
    assert row["ffo_margin"] is None


def test_healthcare_rd_intensity():
    client = _StubClient(income={"revenue": 500, "researchAndDevelopmentExpenses": 100})
    row = fetch_ticker_row(client, "PFE", "Healthcare")
    assert row["rd_intensity"] == 100 / 500


def test_consumer_inventory_turnover():
    client = _StubClient(income={"costOfRevenue": 900}, balance={"inventory": 100})
    row = fetch_ticker_row(client, "WMT", "Consumer Defensive")
    assert row["inventory_turnover"] == 900 / 100


def test_technology_rule_of_40_left_for_caller():
    # rule_of_40 needs revenue_growth_yoy/net_margin from the fundamentals
    # panel the caller already has -- fetch_ticker_row deliberately leaves
    # it None; scripts/run_snapshot.py fills it in after the merge.
    client = _StubClient(income={"revenue": 1000}, balance={})
    row = fetch_ticker_row(client, "MSFT", "Technology")
    assert row["rule_of_40"] is None


def test_missing_line_items_stay_none_not_crash():
    client = _StubClient(income={}, balance={})
    row = fetch_ticker_row(client, "O", "Real Estate")
    assert row["ffo_margin"] is None
