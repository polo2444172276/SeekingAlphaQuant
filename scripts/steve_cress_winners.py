"""Who are the biggest winners among the SA picks, where do they sit by sector,
and how did the other picks in those sectors do?

Per pick event (one per ticker per publication, all three sources): buy at
the first tradable close after publication, hold to the first close more
than one year later. Only completed 1-year holds are used (so the 1-year
return is also the annualised return). Excess = pick return - SPY return over
the identical window. Tickers are ranked by mean excess return across their
completed events; the top 10 are "the winners".

Sectors: SA's GICS sector from the Alpha Picks pages where we have it;
otherwise FMP's profile sector mapped to GICS names. FMP industry is stored
for every ticker. Both are written back to Supabase `securities` (DB first:
only tickers without an industry are fetched from FMP).

Writes data/steve_cress/winners_events.csv, winners_top10.csv,
winners_by_sector.csv and prints the top-10 list (comma-separated) for
scripts/steve_cress_alpha.py --exclude.
"""
import csv
import os
import statistics as st
import sys
from datetime import date

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seekingalpha_quant.data import supabase_db as db  # noqa: E402
from seekingalpha_quant.data.market_data import load_daily  # noqa: E402

OUT = os.path.join(ROOT, "data", "steve_cress")
FMP_TO_GICS = {"Technology": "Information Technology", "Consumer Cyclical": "Consumer Discretionary",
               "Consumer Defensive": "Consumer Staples", "Healthcare": "Health Care",
               "Financial Services": "Financials", "Basic Materials": "Materials"}


def add_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def fill_classification(tickers):
    """DB first; fetch FMP profile for tickers lacking an industry and write back."""
    rows = {r["symbol"]: r for r in db.select("securities", {"market": "eq.US",
                                                             "select": "symbol,name,sector,industry"})}
    todo = [t for t in tickers if not (rows.get(t) or {}).get("industry")]
    upd = []
    for t in todo:
        try:
            js = requests.get("https://financialmodelingprep.com/stable/profile", params={"symbol": t},
                              headers={"apikey": "proxy-injected"}, timeout=30).json()
        except Exception:  # noqa: BLE001
            js = []
        prof = js[0] if isinstance(js, list) and js else {}
        cur = rows.get(t, {})
        sector = cur.get("sector") or FMP_TO_GICS.get(prof.get("sector"), prof.get("sector"))
        upd.append({"market": "US", "symbol": t, "name": cur.get("name") or prof.get("companyName"),
                    "sector": sector or None, "industry": prof.get("industry") or None})
    if upd:
        db.upsert("securities", upd, on_conflict="market,symbol")
        print(f"classification: fetched {len(upd)} profiles from FMP and wrote them to the DB")
    rows = {r["symbol"]: r for r in db.select("securities", {"market": "eq.US",
                                                             "select": "symbol,name,sector,industry"})}
    return rows


def main():
    picks = db.select("picks", {"select": "source,published_date,published_time,symbol"})
    tick = sorted({p["symbol"] for p in picks})
    px = load_daily(tick + ["SPY"], start="2021-12-01", verbose=False)
    cal = [r["date"] for r in px["SPY"]]
    idx = {d: i for i, d in enumerate(cal)}
    adj = {}
    for t, rows in px.items():
        a = np.full(len(cal), np.nan)
        for r in rows:
            if r["date"] in idx:
                a[idx[r["date"]]] = r["adj_close"]
        for i in range(1, len(cal)):
            if np.isnan(a[i]) and not np.isnan(a[i - 1]):
                a[i] = a[i - 1]
        adj[t] = a
    cls = fill_classification(tick)

    events = {}
    for p in picks:
        d = date.fromisoformat(p["published_date"])
        after = p["published_time"] and p["published_time"] >= "16:00"
        e = next((i for i, x in enumerate(cal) if (x > d if after else x >= d)), None)
        t = p["symbol"]
        if e is None or t not in adj or np.isnan(adj[t][e]):
            continue
        tgt = add_year(cal[e])
        x = next((i for i in range(e, len(cal)) if cal[i] > tgt), None)
        if x is None:
            continue  # 1-year hold not completed yet
        r = adj[t][x] / adj[t][e] - 1
        rs = adj["SPY"][x] / adj["SPY"][e] - 1
        key = (t, e)
        src = "Alpha Picks" if p["source"] == "Alpha Picks" else p["source"]
        if key not in events or src == "Alpha Picks":
            c = cls.get(t, {})
            events[key] = dict(ticker=t, name=c.get("name") or "", sector=c.get("sector") or "Unknown",
                               industry=c.get("industry") or "", source=src, entry=cal[e], exit=cal[x],
                               ret=r, spy=rs, excess=r - rs)
    ev = list(events.values())

    by_t = {}
    for e in ev:
        by_t.setdefault(e["ticker"], []).append(e)
    tick_rows = []
    for t, es in by_t.items():
        tick_rows.append(dict(ticker=t, name=es[0]["name"], sector=es[0]["sector"], industry=es[0]["industry"],
                              events=len(es), mean_ret=st.mean(x["ret"] for x in es),
                              mean_excess=st.mean(x["excess"] for x in es),
                              entries=";".join(str(x["entry"]) for x in es)))
    tick_rows.sort(key=lambda r: -r["mean_excess"])
    top = tick_rows[:10]
    top_set = {r["ticker"] for r in top}

    with open(os.path.join(OUT, "winners_events.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "name", "sector", "industry", "source", "entry", "exit", "return_1y", "spy_1y",
                    "excess_1y", "top10"])
        for e in sorted(ev, key=lambda e: e["entry"]):
            w.writerow([e["ticker"], e["name"], e["sector"], e["industry"], e["source"], e["entry"], e["exit"],
                        round(e["ret"], 4), round(e["spy"], 4), round(e["excess"], 4),
                        "Y" if e["ticker"] in top_set else ""])
    with open(os.path.join(OUT, "winners_top10.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(top[0]))
        w.writeheader()
        for r in top:
            w.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()})

    def agg(es):
        if not es:
            return dict(n=0)
        r = [x["ret"] for x in es]
        xs = [x["excess"] for x in es]
        return dict(n=len(es), mean_ret=st.mean(r), median_ret=st.median(r), mean_excess=st.mean(xs),
                    median_excess=st.median(xs), beat_spy=sum(v > 0 for v in xs) / len(xs))

    sectors = sorted({e["sector"] for e in ev})
    sec_rows = []
    for s in sectors:
        es = [e for e in ev if e["sector"] == s]
        sec_rows.append(dict(sector=s, top10_tickers=",".join(sorted({e["ticker"] for e in es} & top_set)),
                             **{f"all_{k}": v for k, v in agg(es).items()},
                             **{f"ex_top10_{k}": v for k, v in agg([e for e in es if e["ticker"] not in top_set]).items()}))
    sec_rows.sort(key=lambda r: -r["all_n"])
    keys = sorted({k for r in sec_rows for k in r}, key=lambda k: (k != "sector", k != "top10_tickers", k))
    with open(os.path.join(OUT, "winners_by_sector.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in sec_rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    allx = agg(ev)
    print(f"completed 1-year pick events: {len(ev)}  (tickers {len(by_t)})")
    print(f"ALL events: mean 1Y {allx['mean_ret']:.1%}, median {allx['median_ret']:.1%}, "
          f"mean excess {allx['mean_excess']:.1%}, median excess {allx['median_excess']:.1%}, beat SPY {allx['beat_spy']:.0%}")
    tx = agg([e for e in ev if e["ticker"] in top_set])
    ox = agg([e for e in ev if e["ticker"] not in top_set])
    print(f"TOP10 events ({tx['n']}): mean 1Y {tx['mean_ret']:.1%}, median {tx['median_ret']:.1%}, "
          f"mean excess {tx['mean_excess']:.1%}")
    print(f"OTHERS ({ox['n']}): mean 1Y {ox['mean_ret']:.1%}, median {ox['median_ret']:.1%}, "
          f"mean excess {ox['mean_excess']:.1%}, median excess {ox['median_excess']:.1%}, beat SPY {ox['beat_spy']:.0%}")
    print("\nTOP 10 by mean 1-year excess return:")
    for r in top:
        print(f"  {r['ticker']:6} {r['name'][:28]:28} {r['sector'][:24]:24} {r['industry'][:34]:34} "
              f"events {r['events']}  ret {r['mean_ret']:7.1%}  excess {r['mean_excess']:7.1%}  [{r['entries']}]")
    print(f"  mean of the 10 tickers: ret {st.mean(r['mean_ret'] for r in top):.1%}, "
          f"excess {st.mean(r['mean_excess'] for r in top):.1%}")
    print("\nBy sector (all events | excluding top-10 tickers):")
    for r in sec_rows:
        ex = (f"n {r['ex_top10_n']:3}  mean {r['ex_top10_mean_ret']:7.1%}  med {r['ex_top10_median_ret']:7.1%}  "
              f"excess {r['ex_top10_mean_excess']:7.1%}  beat {r['ex_top10_beat_spy']:4.0%}") if r["ex_top10_n"] else "-"
        print(f"  {r['sector'][:24]:24} n {r['all_n']:3}  mean {r['all_mean_ret']:7.1%}  excess {r['all_mean_excess']:7.1%} | "
              f"{ex}  top10: {r['top10_tickers']}")
    print("\nEXCLUDE=" + ",".join(r["ticker"] for r in top))


if __name__ == "__main__":
    main()
