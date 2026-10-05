"""Point-in-time S&P 500 membership reconstruction.

FMP has no point-in-time constituents endpoint at any tier tried so far.
Instead we start from today's known membership (data/sp500_constituents.csv)
and walk data/sp500_membership_changes.csv (see
scripts/update_membership_history.py) backward in time, undoing each
add/remove event -- this avoids survivorship bias in the historical
backfill (tickers that were in the index once but aren't today still get
their own history).
"""

import csv
import datetime as dt
import os

_CHANGES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "sp500_membership_changes.csv",
)


def load_changes(path=None):
    """Return every membership-change event as
    [{"date": date, "action": "add"|"remove", "ticker": str}, ...]."""
    path = path or _CHANGES_PATH
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "date": dt.date.fromisoformat(row["date"]),
            "action": row["action"],
            "ticker": row["ticker"],
        }
        for row in rows
    ]


def reconstruct_membership(as_of, current_members, changes):
    """Reconstruct the exact S&P 500 membership set as of `as_of` (a date).

    Walks every change event strictly after `as_of` in reverse-chronological
    order and undoes it: an "add" on date D means the ticker was NOT a
    member before D (so it's removed from the reconstructed set); a
    "remove" on date D means the ticker WAS a member right up until D (so
    it's added back).
    """
    members = set(current_members)
    for event in sorted(changes, key=lambda e: e["date"], reverse=True):
        if event["date"] <= as_of:
            break
        if event["action"] == "add":
            members.discard(event["ticker"])
        else:
            members.add(event["ticker"])
    return members


def ever_members(current_members, changes):
    """Union of today's members and every ticker that ever appeared in the
    changes log -- the full fetch universe for a historical backfill, since
    some tickers were removed from the index before today and won't be in
    data/sp500_constituents.csv at all."""
    result = set(current_members)
    for event in changes:
        result.add(event["ticker"])
    return result
