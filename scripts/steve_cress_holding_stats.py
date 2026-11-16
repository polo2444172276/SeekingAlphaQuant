"""1-year (long-term-capital-gain) and 2-year holding-period stats for every
Steven Cress / SA Quant pick.

Entry  = first close readers could actually trade at: the close of the
         publication session (pre-market / intraday / non-trading-day
         publications) or of the next session (after-16:00 publications).
         Alpha Picks have dates only -> close of the pick date (or next session).
Exit   = 1Y: first close strictly after entry_date + 1 calendar year
             (held > 1 year, i.e. long-term capital gain);
         2Y: first close on/after entry_date + 2 calendar years.
         Only picks whose full window has elapsed are included.
Prices = dividend-adjusted closes (total return). Delisted names: Yahoo, else
         FMP; after the last traded day the position is treated as cash at
         the last price (0 return) for the remainder of the window.

Per pick and per window (also for SPY over the identical window):
  total return, CAGR, annualised vol, Sharpe (daily excess over 13-week
  T-bill ^IRX, x sqrt(252)), beta to SPY (daily), max drawdown, Calmar
  (CAGR / |MDD|).

Writes data/steve_cress/holding_stats.csv (per pick) and
data/steve_cress/holding_summary.csv (aggregates).
"""
import csv
import math
import os
import statistics as st
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import steve_cress_prices as prices  # noqa: E402
from steve_cress_event_study import load_events, D  # noqa: E402

TODAY_DATA = None


def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def path_stats(series, rf, spy_ret):
    """series: [(date, adj)] covering the window incl. entry."""
    p = [x[1] for x in series]
    rets = [p[i] / p[i - 1] - 1 for i in range(1, len(p))]
    days = [x[0] for x in series[1:]]
    total = p[-1] / p[0] - 1
    yrs = (series[-1][0] - series[0][0]).days / 365.25
    cagr = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1.0
    vol = st.pstdev(rets) * math.sqrt(252)
    ex = [r - rf.get(d, 0.0) for r, d in zip(rets, days)]
    sharpe = st.mean(ex) / st.pstdev(rets) * math.sqrt(252) if st.pstdev(rets) > 0 else float("nan")
    peak, mdd = p[0], 0.0
    for v in p:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    beta = float("nan")
    if spy_ret is not None:
        pairs = [(r, spy_ret[d]) for r, d in zip(rets, days) if d in spy_ret]
        if len(pairs) > 20:
            xs, ys = [b for _, b in pairs], [a for a, _ in pairs]
            mx, my = st.mean(xs), st.mean(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            var = sum((x - mx) ** 2 for x in xs)
            beta = cov / var if var else float("nan")
    return dict(total=total, cagr=cagr, vol=vol, sharpe=sharpe, beta=beta, mdd=mdd, calmar=calmar)


def main():
    events = load_events()
    spy = [(r[0], r[5]) for r in prices.get("SPY")]
    spy_ret = {spy[i][0]: spy[i][1] / spy[i - 1][1] - 1 for i in range(1, len(spy))}
    irx = prices.get("^IRX")
    rf = {r[0]: r[4] / 100 / 252 for r in irx}
    last_day = spy[-1][0]
    cal = [d for d, _ in spy]  # trading calendar

    per, skipped = [], []
    for (src, d, t), hm in sorted(events.items()):
        s = [(r[0], r[5]) for r in prices.get(t)]
        if not s:
            skipped.append((src, d, t, "no data"))
            continue
        pub = date.fromisoformat(d)
        after = hm is not None and hm >= "16:00"
        ent_day = next((c for c in cal if (c > pub if after else c >= pub)), None)
        px = dict(s)
        if ent_day not in px:
            skipped.append((src, d, t, "no entry price"))
            continue
        for label, yrs, strict in (("1Y", 1, True), ("2Y", 2, False)):
            tgt = add_years(ent_day, yrs)
            exit_day = next((c for c in cal if (c > tgt if strict else c >= tgt)), None)
            if exit_day is None or exit_day > last_day:
                continue
            # stock path on SPY calendar, flat after last traded day
            path, last = [], None
            for c in cal:
                if c < ent_day or c > exit_day:
                    continue
                if c in px:
                    last = px[c]
                if last is not None:
                    path.append((c, last))
            spath = [(c, v) for c, v in spy if ent_day <= c <= exit_day]
            m = path_stats(path, rf, spy_ret)
            b = path_stats(spath, rf, None)
            delisted = s[-1][0] < exit_day
            per.append([src, d, t, label, ent_day, exit_day, "Y" if delisted else ""] +
                       [round(m[k], 5) for k in ("total", "cagr", "vol", "sharpe", "beta", "mdd", "calmar")] +
                       [round(b[k], 5) for k in ("total", "cagr", "vol", "sharpe", "mdd", "calmar")])

    hdr = ["source", "published", "ticker", "horizon", "entry_date", "exit_date", "delisted_in_window",
           "total_return", "cagr", "ann_vol", "sharpe", "beta", "max_drawdown", "calmar",
           "spy_total_return", "spy_cagr", "spy_ann_vol", "spy_sharpe", "spy_max_drawdown", "spy_calmar"]
    with open(os.path.join(D, "holding_stats.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(per)

    def agg(rows):
        g = lambda k: [r[hdr.index(k)] for r in rows if not math.isnan(r[hdr.index(k)])]  # noqa: E731
        tr, sp = g("total_return"), g("spy_total_return")
        return dict(
            n=len(rows),
            mean=st.mean(tr), median=st.median(tr), std=st.stdev(tr),
            beat_spy=sum(r[hdr.index("total_return")] > r[hdr.index("spy_total_return")] for r in rows) / len(rows),
            sharpe_mean=st.mean(g("sharpe")), sharpe_median=st.median(g("sharpe")),
            beta_mean=st.mean(g("beta")), beta_median=st.median(g("beta")),
            mdd_mean=st.mean(g("max_drawdown")), mdd_median=st.median(g("max_drawdown")), mdd_worst=min(g("max_drawdown")),
            calmar_mean=st.mean(g("calmar")), calmar_median=st.median(g("calmar")),
            spy_mean=st.mean(sp), spy_median=st.median(sp), spy_sharpe_median=st.median(g("spy_sharpe")),
            spy_mdd_median=st.median(g("spy_max_drawdown")), spy_calmar_median=st.median(g("spy_calmar")),
        )

    out = []
    for label in ("1Y", "2Y"):
        for src in ("ALL", "Annual Top 10", "H2 Top 10", "Alpha Picks"):
            rows = [r for r in per if r[3] == label and (src == "ALL" or r[0] == src)]
            if len(rows) > 2:
                a = agg(rows)
                out.append(dict(horizon=label, source=src, **{k: round(v, 4) for k, v in a.items()}))
    with open(os.path.join(D, "holding_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for o in out:
        print(o)
    print("skipped:", skipped)
    print("delisted-in-window rows:", [(r[2], r[3]) for r in per if r[6]])


if __name__ == "__main__":
    main()
