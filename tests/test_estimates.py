import datetime as dt

from seekingalpha_quant.data.estimates import _net_upgrades, compute_eps_revisions_row
from seekingalpha_quant.data.fmp_client import SymbolNotEntitled


class _GatedClient:
    """Stub client that 402s every call, like a symbol FMP restricts."""

    def get(self, path, params=None, **kwargs):
        raise SymbolNotEntitled(f"{path} symbol={params.get('symbol')}: not available")


def test_net_upgrades_none_when_grades_unavailable():
    # Gated/failed fetch must be None (missing), not 0 (a real "no changes" reading).
    assert _net_upgrades(None, days=30) is None


def test_net_upgrades_zero_when_genuinely_no_recent_changes():
    old_date = (dt.date.today() - dt.timedelta(days=500)).isoformat()
    grades = [{"date": old_date, "action": "upgrade"}]
    assert _net_upgrades(grades, days=30) == 0


def test_net_upgrades_counts_upgrades_and_downgrades():
    recent = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    grades = [
        {"date": recent, "action": "upgrade"},
        {"date": recent, "action": "upgrade"},
        {"date": recent, "action": "downgrade"},
    ]
    assert _net_upgrades(grades, days=30) == 1


def test_compute_eps_revisions_row_is_none_not_zero_for_gated_symbol():
    row = compute_eps_revisions_row(_GatedClient(), "GATED")
    assert row["net_upgrades_1m"] is None
    assert row["net_upgrades_3m"] is None
