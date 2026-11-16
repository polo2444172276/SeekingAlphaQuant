"""10-year view (2022 .. end of 2031): actual 2022-01 .. latest close from
scripts/personal_finance_sim.py, then a Monte Carlo projection to 2031-12-31.

Career assumptions on top of personal_finance_sim.py:
- 2026 is the non-compete year: base is paid as usual (401k + match continue)
  but there is no bonus for 2026 work (nothing paid in March 2027).
- The company internal fund (20%/yr) is paid out at the end of the
  non-compete (2026-12-31), taxed at the 2026 average income-tax rate of
  wages (federal + NJ income tax / taxable wages; FICA was paid at deferral),
  and the net cash goes to the taxable account.
- From 2027 a new job continues the original trajectory: total comp
  = $300k x 1.12^(year-2022), capped at $700k, split 7/12 base and 5/12
  bonus; bonus for year Y paid in March Y+1 (so the 2031 bonus is outside
  the horizon). The new employer has no internal fund (bonus fully in cash).
  401k $10k + $10k match continue in SPY. Spending stays $7,100/month.
- Tax: federal brackets / standard deduction / LTCG thresholds indexed 2.5%
  per year after 2026, Social Security wage base +4% per year; NJ brackets
  unchanged. Investment-income tax paid each April for the prior year.

Returns: paired monthly bootstrap from the realised history (Feb 2022 ..
Oct 2026) of the picks account's time-weighted NAV (already includes its
cash drag and stock selection) and SPY. Picks account: every dollar is
sold and rebought after 12+ months (realising gains); SPY account and 401k
never sell.

Outputs data/steve_cress/projection_summary.csv, projection_monthly.csv,
projection.html.  Usage: python scripts/personal_finance_projection.py [--paths 1000]
"""
import csv
import json
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import personal_finance_sim as pf  # noqa: E402

OUT = pf.OUT
PATHS = int(sys.argv[sys.argv.index("--paths") + 1]) if "--paths" in sys.argv else 1000
END_YEAR = 2031
NONCOMPETE = 2026
COMP_CAP = 700_000.0
INFL, SSW = 0.025, 0.04

# extend federal tables beyond 2026
std, tops, (l0, l15), wb = pf.FED[2026]
for y in range(2027, END_YEAR + 2):
    f = (1 + INFL) ** (y - 2026)
    pf.FED[y] = (std * f, [t * f for t in tops], (l0 * f, l15 * f), wb * (1 + SSW) ** (y - 2026))
_orig_income_tax = pf.income_tax


def income_tax(year, *a, **k):  # use the year's own table (pf.income_tax caps at 2026)
    fed = pf.FED
    saved = fed[2026]
    fed[2026] = fed[year]
    try:
        return _orig_income_tax(2026, *a, **k)
    finally:
        fed[2026] = saved


def fica(year, w):
    wb_y = pf.FED[year][3]
    return 0.062 * min(w, wb_y) + 0.0145 * w + 0.009 * max(0.0, w - 200_000)


def total_comp(y):
    return min(COMP_CAP, (pf.BASE0 + pf.BONUS0) * (1 + pf.RAISE) ** (y - 2022))


def base_y(y):
    return pf.base_for(y) if y <= NONCOMPETE else total_comp(y) * 7 / 12


def bonus_paid(y):
    """Cash bonus paid in March of year y (for work in y-1) and the deferred part."""
    if y <= NONCOMPETE:
        b = pf.bonus_paid_in(y)
        return b * (1 - pf.DEFER), b * pf.DEFER
    if y - 1 == NONCOMPETE:
        return 0.0, 0.0
    b = total_comp(y - 1) * 5 / 12  # new employer: same 20% pre-tax deferral into its internal fund
    return b * (1 - pf.DEFER), b * pf.DEFER


def year_wages(y):
    cash_b, deferred = bonus_paid(y)
    base = base_y(y)
    wages = base + cash_b - pf.K401
    wtax = income_tax(y, wages)[0] + fica(y, base + cash_b + deferred)
    return base, cash_b, wages, wtax


def main():
    env = pf.Env()
    spy = pf.run(env, "spy", track=True)
    runs = [pf.run(env, "picks", np.random.default_rng(pf.SEED + k)) for k in range(200)]
    tv = np.array([r["taxable_mtm"] for r in runs])
    mk = int(np.argmin(np.abs(tv - np.median(tv))))
    picks = pf.run(env, "picks", np.random.default_rng(pf.SEED + mk), track=True)

    # monthly returns from time-weighted NAVs
    def month_end_returns(dates, nav):
        me = {}
        for d, v in zip(dates, nav):
            me[(d.year, d.month)] = v
        keys = sorted(me)
        return keys, np.array([me[keys[i]] / me[keys[i - 1]] - 1 for i in range(1, len(keys))])
    kp, rp = month_end_returns(picks["nav_dates"], picks["nav"])
    ks, rs = month_end_returns(spy["nav_dates"], spy["nav"])
    common = sorted(set(kp[1:]) & set(ks[1:]))
    common = [k for k in common if k < (env.m.last.year, env.m.last.month)]  # complete months only
    rp = np.array([rp[kp[1:].index(k)] for k in common])
    rs = np.array([rs[ks[1:].index(k)] for k in common])
    print(f"bootstrap pool: {len(common)} months {common[0]}..{common[-1]}; "
          f"picks mean {rp.mean():.2%}/mo, SPY {rs.mean():.2%}/mo")

    last = env.m.last
    P_spy = env.m.P["SPY"][-1]
    st0, sp0 = picks["state"], spy["state"]
    fund0 = st0["fund"]
    _, _, w26, _ = year_wages(2026)
    eff26 = income_tax(2026, w26)[0] / w26
    fund_net = None  # computed at payout (fund grows to year end)

    months = []
    y, mth = last.year, last.month
    while (y, mth) < (END_YEAR, 12):
        mth += 1
        if mth == 13:
            y, mth = y + 1, 1
        months.append((y, mth))

    rng = np.random.default_rng(2031)
    res = {"picks": [], "spy": []}
    paths_nw = {"picks": [], "spy": []}
    for path in range(PATHS):
        draw = rng.integers(0, len(rp), size=len(months))
        for strat, st in (("picks", st0), ("spy", sp0)):
            # taxable account state
            if strat == "picks":
                vint = [[sh * env.m.P[t][-1], cost, (last - d0).days / 30.44] for t, sh, cost, d0 in st["lots"]]
                vint.append([st["cash"], st["cash"], 0.0])
                rets = rp
            else:
                vint = [[st["spy_shares"] * P_spy + st["cash"], st["spy_cost"] + st["cash"], 0.0]]
                rets = rs
            k401 = st["k401_shares"] * P_spy
            fund = st["fund"]
            carry = st["carry_loss"]
            realized = {last.year: list(st["realized_ytd"])}
            interest = {last.year: st["interest_ytd"]}
            nw_path = []
            for j, (yy, mm) in enumerate(months):
                r, r_s = rets[draw[j]], rs[draw[j]]
                for v in vint:
                    v[0] *= 1 + r
                    v[2] += 1
                k401 = k401 * (1 + r_s) + (pf.K401 + pf.MATCH) / 12
                fund *= (1 + pf.FUND_RET) ** (1 / 12)
                if mm == 3 and yy > NONCOMPETE:  # new employer's internal fund deposit
                    fund += bonus_paid(yy)[1]
                # picks: sell vintages held > 12 months, rebuy (realise gain)
                if strat == "picks":
                    for v in vint:
                        if v[2] > 12:
                            realized.setdefault(yy, [0.0, 0.0])[1] += v[0] - v[1]
                            v[1], v[2] = v[0], 0.0
                # cash flows into the taxable account
                base, cash_b, wages, wtax = year_wages(yy)
                cash_pay = base + cash_b
                flow = base / 12 - pf.K401 / 12 - wtax * (base / 12) / cash_pay - 2 * pf.SPEND_PER_CHECK
                if mm == 3 and cash_b:
                    flow += cash_b - wtax * cash_b / cash_pay
                if (yy, mm) == (NONCOMPETE, 12):
                    flow += fund * (1 - eff26)
                    fund = 0.0
                if mm == 4:  # investment-income tax for the previous year
                    py = yy - 1
                    st_, lt_ = realized.get(py, [0.0, 0.0])
                    _, _, wpy, _ = year_wages(py)
                    extra = fund0 * 0  # fund payout taxed separately at eff26 above
                    t_inv, carry_new = income_tax(py, wpy, interest.get(py, 0.0), st_, lt_, carry)
                    t_base, _ = income_tax(py, wpy)
                    carry = carry_new
                    flow -= (t_inv - t_base) + extra
                if flow >= 0:
                    vint.append([flow, flow, 0.0])
                else:  # withdraw proportionally (no gain realisation, approximation)
                    tot = sum(v[0] for v in vint)
                    for v in vint:
                        sh = v[0] / tot
                        v[1] *= 1 + flow * sh / v[0] if v[0] else 1
                        v[0] += flow * sh
                if strat == "spy" and len(vint) > 1:  # merge SPY into one pool (never sold)
                    vint = [[sum(v[0] for v in vint), sum(v[1] for v in vint), 0.0]]
                taxable = sum(v[0] for v in vint)
                nw_path.append(taxable + k401 + fund)
            # end of horizon: accrued tax for END_YEAR and liquidation tax
            st_, lt_ = realized.get(END_YEAR, [0.0, 0.0])
            _, _, wend, _ = year_wages(END_YEAR)
            t_real, _ = income_tax(END_YEAR, wend, 0.0, st_, lt_, carry)
            t_base, _ = income_tax(END_YEAR, wend)
            accrued = t_real - t_base
            ust = sum(v[0] - v[1] for v in vint if v[2] <= 12)
            ult = sum(v[0] - v[1] for v in vint if v[2] > 12)
            t_liq, _ = income_tax(END_YEAR, wend, 0.0, st_ + ust, lt_ + ult, carry)
            taxable = sum(v[0] for v in vint) - accrued
            res[strat].append(dict(taxable=taxable, after_liq=taxable - (t_liq - t_real), k401=k401,
                                   fund=fund, net_worth=taxable + k401 + fund))
            paths_nw[strat].append(nw_path)

    q = lambda a, p: float(np.percentile(a, p))  # noqa: E731
    rows = []
    for strat in ("picks", "spy"):
        for key in ("net_worth", "taxable", "after_liq", "k401", "fund"):
            a = np.array([r[key] for r in res[strat]])
            rows.append(dict(strategy=strat, metric=key, p5=round(q(a, 5)), p25=round(q(a, 25)),
                             median=round(q(a, 50)), p75=round(q(a, 75)), p95=round(q(a, 95))))
    pn = np.array([r["net_worth"] for r in res["picks"]])
    sn = np.array([r["net_worth"] for r in res["spy"]])
    with open(os.path.join(OUT, "projection_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # monthly fan: history (actual) + projection percentiles
    hist = []
    for a, b in zip(picks["monthly"], spy["monthly"]):
        if a["date"] >= date(2022, 1, 1):
            hist.append([a["date"].isoformat()[:7], a["taxable"] + a["k401"] + a["fund"],
                         b["taxable"] + b["k401"] + b["fund"]])
    P = np.array(paths_nw["picks"])
    S = np.array(paths_nw["spy"])
    with open(os.path.join(OUT, "projection_monthly.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "kind", "picks_p10", "picks_median", "picks_p90", "spy_p10", "spy_median", "spy_p90"])
        for h in hist:
            w.writerow([h[0], "actual", round(h[1]), round(h[1]), round(h[1]), round(h[2]), round(h[2]), round(h[2])])
        for j, (yy, mm) in enumerate(months):
            w.writerow([f"{yy}-{mm:02d}", "projected"] +
                       [round(np.percentile(P[:, j], p)) for p in (10, 50, 90)] +
                       [round(np.percentile(S[:, j], p)) for p in (10, 50, 90)])

    print(f"fund at payout (2026-12) taxed at {eff26:.1%}; 2026 wages ${w26:,.0f}")
    for y_ in range(2026, END_YEAR + 1):
        b, cb, wg, wt = year_wages(y_)
        print(f"  {y_}: base ${b:,.0f}  cash bonus paid ${cb:,.0f}  wage tax ${wt:,.0f}")
    for r in rows:
        print(r)
    print(f"P(picks net worth > SPY net worth at end-{END_YEAR}) = {np.mean(pn > sn):.0%}; "
          f"median difference ${np.median(pn - sn):,.0f}")


if __name__ == "__main__":
    main()
