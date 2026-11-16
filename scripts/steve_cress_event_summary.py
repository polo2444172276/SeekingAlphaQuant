"""Summarise event_study.csv against a placebo baseline.

Placebo: for every ticker in the event set, every trading day that is NOT
within 30 trading days of one of its pick events is used as a pseudo
reference close, and the same day-1..6 Open/High/Low/Close/max-High metrics
(minus SPY) are computed. The gap between event and placebo medians is the
part of the move attributable to the recommendation rather than to the
stock's normal volatility/drift.

Writes data/steve_cress/event_summary.csv.
"""
import csv
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from steve_cress_event_study import fetch_ohlc, load_events, D  # noqa: E402

FIELDS = ["open", "high", "low", "close", "max_high_to_date"]


def q(v, p):
    v = sorted(v)
    i = (len(v) - 1) * p
    lo = int(i)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (i - lo)


def metrics(s, i_ref, spy):
    ref = s[i_ref]
    sref = spy.get(ref[0])
    if not sref:
        return None
    out, hi, shi = {}, -1e9, None
    for k in range(1, 7):
        day = s[i_ref + k]
        sd = spy.get(day[0])
        if not sd:
            return None
        hi = max(hi, day[2])
        for f, v, sv in (("open", day[1], sd[1]), ("high", day[2], sd[2]), ("low", day[3], sd[3]),
                         ("close", day[4], sd[4]), ("max_high_to_date", hi, sd[4])):
            out[(f, k)] = (v / ref[4] - 1) - (sv / sref[4] - 1)
    return out


def main():
    events = load_events()
    spy = {r[0]: r for r in fetch_ohlc("SPY")}
    ev_rows = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(D, "event_study.csv"))):
        if r["abnormal_vs_spy"]:
            ev_rows[(r["field"], int(r["day"]))].append(float(r["abnormal_vs_spy"]))

    by_t = defaultdict(list)
    for (_, d, t) in events:
        by_t[t].append(date.fromisoformat(d))
    plc = defaultdict(list)
    for t, dates in by_t.items():
        s = fetch_ohlc(t)
        if not s:
            continue
        idx = {x[0]: i for i, x in enumerate(s)}
        blocked = set()
        for d in dates:
            i0 = next((i for i, x in enumerate(s) if x[0] >= d), None)
            if i0 is not None:
                blocked.update(range(i0 - 30, i0 + 31))
        for i in range(0, len(s) - 7, 3):  # every 3rd day keeps it fast
            if i in blocked:
                continue
            m = metrics(s, i, spy)
            if m:
                for k, v in m.items():
                    plc[k].append(v)

    rows = []
    for f in FIELDS:
        for k in range(1, 7):
            e, p = ev_rows[(f, k)], plc[(f, k)]
            rows.append([f, k, len(e), round(st.mean(e), 5), round(q(e, .1), 5), round(q(e, .25), 5),
                         round(q(e, .5), 5), round(q(e, .75), 5), round(q(e, .9), 5),
                         round(sum(x > 0 for x in e) / len(e), 3),
                         len(p), round(st.mean(p), 5), round(q(p, .5), 5),
                         round(sum(x > 0 for x in p) / len(p), 3),
                         round(q(e, .5) - q(p, .5), 5)])
    with open(os.path.join(D, "event_summary.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "day", "n_event", "mean", "p10", "p25", "median", "p75", "p90", "share_pos",
                    "n_placebo", "placebo_mean", "placebo_median", "placebo_share_pos", "median_minus_placebo"])
        w.writerows(rows)
    print("field              d   ev_med  plc_med   diff   ev_mean plc_mean  ev%>0 plc%>0")
    for r in rows:
        print(f"{r[0]:17} {r[1]}  {r[6]:7.2%} {r[12]:7.2%} {r[14]:7.2%}  {r[3]:7.2%} {r[11]:7.2%}  {r[9]:5.0%} {r[13]:5.0%}")


if __name__ == "__main__":
    main()
