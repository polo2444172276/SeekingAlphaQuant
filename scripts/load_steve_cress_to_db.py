"""Load the Steven Cress picks, Alpha Picks positions and the daily prices
of every pick (plus SPY and ^IRX) into the shared Supabase database.

Idempotent: securities/picks/prices are upserted on their natural keys;
alpha_picks_positions rows for the same snapshot_date are replaced.

Usage: python scripts/load_steve_cress_to_db.py [--snapshot 2026-11-16]
"""
import argparse
import csv
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from seekingalpha_quant.data import supabase_db as db  # noqa: E402
import steve_cress_prices as prices  # noqa: E402

D = os.path.join(ROOT, "data", "steve_cress")
DELISTED = {"ARCH", "TA", "LTHM", "VRNA", "SILV", "NGD"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="2026-11-16", help="date the Alpha Picks screenshots were taken")
    args = ap.parse_args()

    top = list(csv.DictReader(open(os.path.join(D, "top_stocks_picks.csv"))))
    cur = list(csv.DictReader(open(os.path.join(D, "alpha_picks_current.csv"))))
    clo = list(csv.DictReader(open(os.path.join(D, "alpha_picks_closed.csv"))))

    names, sectors = {}, {}
    for r in cur + clo:
        names[r["ticker"]] = r["company"]
        if r["sector"]:
            sectors[r["ticker"]] = r["sector"]
    tickers = sorted({r["ticker"] for r in top + cur + clo} | {"SPY", "^IRX"})

    t0 = time.time()
    db.upsert("securities", [{"market": "US", "symbol": t, "name": names.get(t), "sector": sectors.get(t)}
                             for t in tickers], on_conflict="market,symbol")
    ids = db.security_ids("US")
    print(f"securities: {len(tickers)} upserted ({time.time() - t0:.1f}s)")

    picks = []
    for r in top:
        d, hm = r["published_et"].split()
        picks.append({"source": "H2 Top 10" if "H2" in r["list"] else "Annual Top 10", "list_id": r["list"],
                      "article_title": r["article_title"], "published_date": d, "published_time": hm,
                      "symbol": r["ticker"], "security_id": ids.get(r["ticker"]), "note": r["note"] or None})
    seen = set()
    for r in cur + clo:
        k = (r["picked"], r["ticker"])
        if k in seen:
            continue
        seen.add(k)
        picks.append({"source": "Alpha Picks", "list_id": None, "article_title": None,
                      "published_date": r["picked"], "published_time": None, "symbol": r["ticker"],
                      "security_id": ids.get(r["ticker"]), "note": None})
    t0 = time.time()
    db.upsert("picks", picks, on_conflict="source,published_date,symbol")
    print(f"picks: {len(picks)} upserted ({time.time() - t0:.1f}s)")

    pos = []
    for r in cur:
        pos.append({"symbol": r["ticker"], "company": r["company"], "picked_date": r["picked"], "closed_date": None,
                    "reported_return_pct": float(r["return_pct"]), "sector": r["sector"] or None,
                    "rating": r["rating"], "holding_pct": float(r["holding_pct"]), "winner": r["winner"] == "Y",
                    "snapshot_date": args.snapshot, "note": None})
    for r in clo:
        pos.append({"symbol": r["ticker"], "company": r["company"], "picked_date": r["picked"],
                    "closed_date": r["closed"], "reported_return_pct": float(r["return_pct"]),
                    "sector": r["sector"] or None, "rating": r["rating"], "holding_pct": None,
                    "winner": r["winner"] == "Y", "snapshot_date": args.snapshot, "note": None})
    db.delete("alpha_picks_positions", {"snapshot_date": f"eq.{args.snapshot}"})
    db.insert("alpha_picks_positions", pos)
    print(f"alpha_picks_positions: {len(pos)} rows for snapshot {args.snapshot}")

    total, t_fetch, t_write = 0, 0.0, 0.0
    for t in tickers:
        a = time.time()
        rows = prices.get(t)
        t_fetch += time.time() - a
        src = "fmp" if t in DELISTED else "yahoo"
        recs = [{"security_id": ids[t], "date": r[0].isoformat(), "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "adj_close": r[5], "source": src} for r in rows]
        a = time.time()
        db.upsert("prices_daily", recs, on_conflict="security_id,date", batch=5000)
        t_write += time.time() - a
        total += len(recs)
    print(f"prices_daily: {total} rows for {len(tickers)} tickers; "
          f"fetch {t_fetch:.0f}s, write {t_write:.0f}s ({total / max(t_write, 1e-9):,.0f} rows/s)")


if __name__ == "__main__":
    main()
