"""Semi-monthly DCA into SA picks with a cap of 5 BUY trades per calendar month.

Same cash rules as scripts/steve_cress_dca_backtest.py (defaults):
- $50 on the 1st and 15th; the whole H1-2022 allowance ($600) arrives 2022-01-01.
- Each half-month window's budget = contribution + carried cash + unlocked
  sale proceeds, split equally across the picks bought in that window.
- Buy at the first tradable close after publication; sell at the first close
  more than one year later; proceeds unlocked in 12 equal parts over the next
  12 windows (half a year). Sells do not count toward the cap.
- Dividend-adjusted prices; delisted names held flat after their last price.
- SPY benchmark: identical dollars on identical entry days, same rules.

Cap rule (max 5 buys per month), decided causally window by window:
- Alpha Picks first; a slot is reserved for the month's second Alpha Pick
  when one is still to come later in the month.
- Remaining slots are filled from the annual / H2 Top-10 list picks using a
  selector:
    random    - uniform random sample (Monte Carlo, N runs)
    momentum  - highest 6-month (126 trading days) return before publication
- If Alpha Picks alone exceed the slots (July 2022), the same selector picks
  among them.
Reference run "uncapped" buys every pick (identical to the original backtest).

Writes data/steve_cress/dca_capped_summary.csv, dca_capped_random_runs.csv,
dca_capped_daily.csv (median-random, momentum, uncapped PnL paths).
Usage: python scripts/steve_cress_dca_capped.py [--runs 1000] [--seed 7]
"""
import csv
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seekingalpha_quant.data import supabase_db as db  # noqa: E402
from seekingalpha_quant.data.market_data import load_daily  # noqa: E402

OUT = os.path.join(ROOT, "data", "steve_cress")
AMOUNT, CAP, SPREAD, MOM_DAYS = 50.0, 5, 12, 126
START = date(2022, 1, 1)
RUNS = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 1000
SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 7


def add_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def contribution_dates(end):
    d = START
    while d <= end:
        yield d
        d = date(d.year, d.month, 15) if d.day == 1 else date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def contrib_amount(c):
    if c < date(2022, 7, 1):
        return AMOUNT * 12 if c == START else 0.0
    return AMOUNT


def xirr(flows):
    t0 = flows[0][0]
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        npv = sum(v / (1 + mid) ** ((d - t0).days / 365.25) for d, v in flows)
        lo, hi = (mid, hi) if npv > 0 else (lo, mid)
    return mid


class Market:
    def __init__(self):
        picks = db.select("picks", {"select": "source,published_date,published_time,symbol"})
        px = load_daily(sorted({p["symbol"] for p in picks} | {"SPY"}), start="2021-06-01", verbose=False)
        self.cal = [r["date"] for r in px["SPY"]]
        self.idx = {d: i for i, d in enumerate(self.cal)}
        n = len(self.cal)
        self.P = {}
        for t, rows in px.items():
            a = np.full(n, np.nan)
            for r in rows:
                if r["date"] in self.idx:
                    a[self.idx[r["date"]]] = r["adj_close"]
            for i in range(1, n):  # forward fill (flat after delisting)
                if np.isnan(a[i]) and not np.isnan(a[i - 1]):
                    a[i] = a[i - 1]
            self.P[t] = a
        self.last = self.cal[-1]
        self.cdates = list(contribution_dates(self.last))
        self.start_i = self.idx[next(d for d in self.cal if d >= date(2022, 1, 3))]

        # per window: {ticker: (entry_idx, source, momentum)}
        self.windows = []
        for wi, c in enumerate(self.cdates):
            nxt = self.cdates[wi + 1] if wi + 1 < len(self.cdates) else date(9999, 1, 1)
            win = {}
            for p in picks:
                d = date.fromisoformat(p["published_date"])
                if not (c <= d < nxt):
                    continue
                after = p["published_time"] and p["published_time"] >= "16:00"
                e = next((k for k, x in enumerate(self.cal) if (x > d if after else x >= d)), None)
                t = p["symbol"]
                if e is None or t not in self.P or np.isnan(self.P[t][e]):
                    continue
                ref = e - 1 if not after else e - 1
                base = self.P[t][ref - MOM_DAYS] if ref - MOM_DAYS >= 0 else np.nan
                mom = self.P[t][ref] / base - 1 if base and not np.isnan(base) else -np.inf
                if t not in win or e < win[t][0]:
                    ap = p["source"] == "Alpha Picks" or (t in win and win[t][1])
                    win[t] = (e, ap, mom)
            self.windows.append(win)
        self.exit_idx = {}
        for win in self.windows:
            for t, (e, _, _) in win.items():
                tgt = add_year(self.cal[e])
                x = next((k for k in range(e, n) if self.cal[k] > tgt), None)
                self.exit_idx[e] = x


def simulate(m, selector, rng=None):
    n = len(m.cal)
    cdates = m.cdates
    unlock = np.zeros(len(cdates) + SPREAD)
    unlock_s = np.zeros(len(cdates) + SPREAD)
    carry = carry_s = 0.0
    flow = np.zeros(n)      # cash flow from trades (negative = buy, positive = sell)
    flow_s = np.zeros(n)
    mv = np.zeros(n)
    mv_s = np.zeros(n)
    lots = []
    slots = {}
    pending_exits = []      # (exit_idx, proceeds, proceeds_spy)
    for wi, c in enumerate(cdates):
        # schedule proceeds of lots sold before this contribution date
        keep = []
        for x, pr, prs in pending_exits:
            if m.cal[x] < c:
                unlock[wi:wi + SPREAD] += pr / SPREAD
                unlock_s[wi:wi + SPREAD] += prs / SPREAD
            else:
                keep.append((x, pr, prs))
        pending_exits = keep

        win = m.windows[wi]
        mkey = (c.year, c.month)
        left = slots.setdefault(mkey, CAP)
        chosen = list(win)
        if selector != "uncapped":
            later_ap = c.day == 1 and wi + 1 < len(cdates) and any(v[1] for v in m.windows[wi + 1].values())
            avail = max(0, left - (1 if later_ap else 0))
            aps = [t for t, v in win.items() if v[1]]
            lst = [t for t, v in win.items() if not v[1]]

            def pick(cands, k):
                if k <= 0:
                    return []
                if len(cands) <= k:
                    return list(cands)
                if selector == "random":
                    return list(rng.choice(sorted(cands), size=k, replace=False))
                return sorted(cands, key=lambda t: -win[t][2])[:k]

            ch_ap = pick(aps, avail)
            chosen = ch_ap + pick(lst, avail - len(ch_ap))
            slots[mkey] = left - len(chosen)

        budget = contrib_amount(c) + carry + unlock[wi]
        budget_s = contrib_amount(c) + carry_s + unlock_s[wi]
        if not chosen:
            carry, carry_s = budget, budget_s
            continue
        carry = carry_s = 0.0
        each, each_s = budget / len(chosen), budget_s / len(chosen)
        for t in chosen:
            e = win[t][0]
            x = m.exit_idx[e]
            sh, sh_s = each / m.P[t][e], each_s / m.P["SPY"][e]
            end = x if x is not None else n
            flow[e] -= each
            flow_s[e] -= each_s
            mv[e:end] += sh * m.P[t][e:end]
            mv_s[e:end] += sh_s * m.P["SPY"][e:end]
            if x is not None:
                pr, prs = sh * m.P[t][x], sh_s * m.P["SPY"][x]
                flow[x] += pr
                flow_s[x] += prs
                pending_exits.append((x, pr, prs))
            lots.append((t, e, x, each))

    contrib = np.zeros(n)
    for c in cdates:
        k = next(i for i, d in enumerate(m.cal) if d >= c)
        contrib[k] += contrib_amount(c)
    cum_c = np.cumsum(contrib)
    cash = cum_c + np.cumsum(flow)
    cash_s = cum_c + np.cumsum(flow_s)
    pnl = (cash + mv - cum_c)[m.start_i:]
    pnl_s = (cash_s + mv_s - cum_c)[m.start_i:]

    def stats(p, cashv, mvv):
        tv = cashv[-1] + mvv[-1]
        flows = [(c, -contrib_amount(c)) for c in cdates if contrib_amount(c)] + [(m.last, tv)]
        dd = p - np.maximum.accumulate(p)
        return dict(pnl=p[-1], irr=xirr(flows), max_dd=dd.min(), peak=p.max())

    return dict(lots=lots, path=pnl, path_spy=pnl_s, **stats(pnl, cash, mv),
                spy=stats(pnl_s, cash_s, mv_s))


def main():
    m = Market()
    rng = np.random.default_rng(SEED)
    res = {"uncapped": simulate(m, "uncapped"), "momentum": simulate(m, "momentum")}
    runs = [simulate(m, "random", rng) for _ in range(RUNS)]

    def row(name, r):
        return dict(variant=name, pnl=round(r["pnl"], 2), irr=round(r["irr"], 4), max_dd=round(r["max_dd"], 2),
                    peak_pnl=round(r["peak"], 2), spy_pnl=round(r["spy"]["pnl"], 2),
                    spy_irr=round(r["spy"]["irr"], 4), spy_max_dd=round(r["spy"]["max_dd"], 2),
                    lots=len(r["lots"]), max_buys_in_a_month=None)

    with open(os.path.join(OUT, "dca_capped_random_runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row("x", runs[0])))
        w.writeheader()
        for k, r in enumerate(runs):
            w.writerow(row(f"random_{k}", r))

    pn = np.array([r["pnl"] for r in runs])
    q = lambda a, p: float(np.percentile(a, p))  # noqa: E731
    summary = [row("uncapped", res["uncapped"]), row("momentum", res["momentum"])]
    for p in (5, 25, 50, 75, 95):
        k = int(np.argmin(np.abs(pn - q(pn, p))))
        summary.append(row(f"random_p{p}", runs[k]))
    with open(os.path.join(OUT, "dca_capped_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    med = runs[int(np.argmin(np.abs(pn - q(pn, 50))))]
    days = m.cal[m.start_i:]
    with open(os.path.join(OUT, "dca_capped_daily.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "uncapped_pnl", "momentum_pnl", "random_median_pnl", "random_p5_pnl", "random_p95_pnl",
                    "spy_pnl_momentum"])
        allp = np.array([r["pnl"] for r in runs])  # final values only
        P = np.vstack([r["pnl"] for r in runs]) if False else None  # noqa: F841
        band = np.vstack([r["path"] for r in runs])
        lo, hi = np.percentile(band, 5, axis=0), np.percentile(band, 95, axis=0)
        for k, d in enumerate(days):
            w.writerow([d, round(res["uncapped"]["path"][k], 2), round(res["momentum"]["path"][k], 2),
                        round(med["path"][k], 2), round(lo[k], 2), round(hi[k], 2),
                        round(res["momentum"]["path_spy"][k], 2)])

    def show(name, r):
        print(f"{name:10} PnL ${r['pnl']:>7,.0f}  IRR {r['irr']:6.1%}  maxDD ${r['max_dd']:>7,.0f}  "
              f"peak ${r['peak']:>7,.0f}  lots {len(r['lots']):3d} | SPY PnL ${r['spy']['pnl']:>6,.0f} "
              f"IRR {r['spy']['irr']:5.1%}")
    show("uncapped", res["uncapped"])
    show("momentum", res["momentum"])
    irr = np.array([r["irr"] for r in runs])
    dd = np.array([r["max_dd"] for r in runs])
    sp = np.array([r["spy"]["pnl"] for r in runs])
    print(f"random x{RUNS}: PnL p5 ${q(pn,5):,.0f}  p25 ${q(pn,25):,.0f}  median ${q(pn,50):,.0f}  "
          f"p75 ${q(pn,75):,.0f}  p95 ${q(pn,95):,.0f}  mean ${pn.mean():,.0f}")
    print(f"  IRR median {np.median(irr):.1%} (p5 {q(irr,5):.1%}, p95 {q(irr,95):.1%}); "
          f"maxDD median ${np.median(dd):,.0f}; SPY PnL median ${np.median(sp):,.0f}; "
          f"beat-SPY share {np.mean(pn > sp):.0%}")
    mom_rank = np.mean(pn < res["momentum"]["pnl"])
    print(f"  momentum PnL is at the {mom_rank:.0%} percentile of random runs")
    by_month = {}
    for t, e, x, d in res["momentum"]["lots"]:
        k = (m.cal[e].year, m.cal[e].month)
        by_month[k] = by_month.get(k, 0) + 1
    print("  max buys in a calendar month (momentum run, by entry date):", max(by_month.values()))


if __name__ == "__main__":
    main()
