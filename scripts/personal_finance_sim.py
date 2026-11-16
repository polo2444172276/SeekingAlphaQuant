"""Personal-finance simulation 2022-01 .. latest close: salary, taxes, 401k,
deferred bonus fund, and a taxable account invested either in the Seeking
Alpha picks strategy or in SPY (buy and hold).

Assumptions (all editable at the top):
- Comp 2022: base $175k, bonus $125k; both +12% per year. Base paid in 24
  equal half-monthly paychecks (1st and 15th). Bonus for year Y paid on
  March 31 of Y+1 (so bonuses for 2022..2025 are paid in 2023..2026).
- 401k: $10k/yr employee pre-tax + $10k employer match, per paycheck, into
  SPY (dividends reinvested). Reported pre-tax.
- 20% of each bonus deferred pre-tax into the company internal fund, which
  compounds at 20%/yr and is never withdrawn. Reported pre-tax.
- Spending: $7,100 per month ($3,550 per paycheck), fixed.
- Taxes, single filer, New Jersey resident:
  federal brackets/standard deduction/LTCG thresholds by year; NIIT 3.8%;
  FICA (Social Security wage base by year, Medicare 1.45% + 0.9% over $200k;
  FICA applies to 401k and bonus deferrals); NJ brackets, $1,000 exemption,
  NJ excludes 401(k) deferrals; the NQDC deferral is assumed excluded too.
  NJ disability/family-leave/UI payroll withholdings and dividend taxes are
  ignored (small). Federal capital losses offset ordinary income up to $3k
  with carryforward; NJ losses only net within the year.
- Wage taxes are withheld from pay (annual wage tax spread over cash pay).
  Tax on investment income (interest + realized gains) for year Y is paid on
  April 15 of Y+1 out of the taxable account's cash.
- Uninvested cash earns the 13-week T-bill yield (^IRX); interest is taxed
  as ordinary income.
- Taxable account, picks strategy: each half-month window invests the cash
  available (paycheck surplus, released bonus/proceeds tranches, interest,
  minus taxes) equally across that window's SA picks, max 5 buys per month
  (Alpha Picks first, Top-10 list picks chosen at random -> Monte Carlo),
  buy at the first tradable close after publication, sell at the first close
  more than one year later. Net bonus cash and sale proceeds are released in
  12 half-monthly tranches.
- Taxable account, SPY: the same cash flows buy SPY on each paycheck date
  (bonus released in the same 12 tranches) and are never sold.

Outputs: data/steve_cress/personal_finance_summary.csv,
personal_finance_monthly.csv (median picks run + SPY), personal_finance.html.
Usage: python scripts/personal_finance_sim.py [--runs 200] [--seed 11]
"""
import csv
import json
import os
import sys
from datetime import date, timedelta

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from seekingalpha_quant.data.market_data import load_daily  # noqa: E402
import steve_cress_dca_capped as cap  # noqa: E402

OUT = os.path.join(ROOT, "data", "steve_cress")
RUNS = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 200
SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 11

BASE0, BONUS0, RAISE = 175_000.0, 125_000.0, 0.12
K401, MATCH = 10_000.0, 10_000.0
DEFER, FUND_RET = 0.20, 0.20
SPEND_PER_CHECK = 7_100.0 / 2
SPREAD = 12
CAP = 5

# ---- tax tables (single filer) ---------------------------------------------
FED = {  # standard deduction, bracket tops for 10/12/22/24/32/35%, LTCG 0% and 15% tops, SS wage base
    2022: (12_950, [10_275, 41_775, 89_075, 170_050, 215_950, 539_900], (41_675, 459_750), 147_000),
    2023: (13_850, [11_000, 44_725, 95_375, 182_100, 231_250, 578_125], (44_625, 492_300), 160_200),
    2024: (14_600, [11_600, 47_150, 100_525, 191_950, 243_725, 609_350], (47_025, 518_900), 168_600),
    2025: (15_750, [11_925, 48_475, 103_350, 197_300, 250_525, 626_350], (48_350, 533_400), 176_100),
    2026: (16_100, [12_400, 50_400, 105_700, 201_775, 256_225, 640_600], (49_450, 545_500), 184_500),
}
FED_RATES = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]
NJ_TOPS = [20_000, 35_000, 40_000, 75_000, 500_000, 1_000_000]
NJ_RATES = [0.014, 0.0175, 0.035, 0.05525, 0.0637, 0.0897, 0.1075]


def bracket_tax(x, tops, rates):
    tax, lo = 0.0, 0.0
    for top, r in zip(tops + [float("inf")], rates):
        if x > lo:
            tax += (min(x, top) - lo) * r
        lo = top
    return tax


def income_tax(year, wages, interest=0.0, st=0.0, lt=0.0, carry_loss=0.0):
    """Federal + NJ income tax (no FICA). Returns (tax, new federal loss carryforward)."""
    std, tops, (lt0, lt15), _ = FED[min(year, 2026)]
    lt -= carry_loss  # federal carryforward treated as long-term loss
    # federal netting
    if st >= 0 and lt >= 0:
        ord_cg, pref, loss_ded, new_carry = st, lt, 0.0, 0.0
    else:
        net = st + lt
        if net >= 0:
            ord_cg, pref = (net, 0.0) if lt < 0 else (0.0, net)
            loss_ded, new_carry = 0.0, 0.0
        else:
            ord_cg = pref = 0.0
            loss_ded = min(3_000.0, -net)
            new_carry = -net - loss_ded
    ordinary = max(0.0, wages + interest + ord_cg - loss_ded - std)
    fed = bracket_tax(ordinary, tops, FED_RATES)
    # preferential rates stacked on top of ordinary income
    p0 = max(0.0, min(pref, lt0 - ordinary))
    p15 = max(0.0, min(pref - p0, lt15 - max(ordinary, lt0)))
    fed += 0.15 * p15 + 0.20 * (pref - p0 - p15)
    magi = wages + interest + max(0.0, st + lt + carry_loss) - loss_ded
    nii = interest + max(0.0, ord_cg + pref)
    fed += 0.038 * max(0.0, min(nii, magi - 200_000))
    nj_cg = max(0.0, st + lt + carry_loss)  # NJ: no carryforward, losses net within year only
    nj = bracket_tax(max(0.0, wages + interest + nj_cg - 1_000), NJ_TOPS, NJ_RATES)
    return fed + nj, new_carry


def fica(year, fica_wages):
    wb = FED[min(year, 2026)][3]
    return 0.062 * min(fica_wages, wb) + 0.0145 * fica_wages + 0.009 * max(0.0, fica_wages - 200_000)


# ---- compensation schedule ----------------------------------------------------
def base_for(y):
    return BASE0 * (1 + RAISE) ** (y - 2022)


def bonus_paid_in(y):  # bonus for year y-1
    return BONUS0 * (1 + RAISE) ** (y - 1 - 2022) if y >= 2023 else 0.0


def wage_tax(y):
    base, bonus = base_for(y), bonus_paid_in(y)
    wages = base + bonus - K401 - DEFER * bonus
    tax, _ = income_tax(y, wages)
    return tax + fica(y, base + bonus), wages


class Env:
    def __init__(self):
        self.m = cap.Market()
        m = self.m
        irx = load_daily(["^IRX"], start="2021-12-01", verbose=False)["^IRX"]
        ir = {r["date"]: r["close"] / 100 for r in irx}
        last = 0.04
        self.rate = []
        for d in m.cal:
            last = ir.get(d, last)
            self.rate.append(last)
        self.n = len(m.cal)
        self.first_on_or_after = lambda d: next(i for i, x in enumerate(m.cal) if x >= d)
        self.win_day = [self.first_on_or_after(c) for c in m.cdates]
        self.win_of_day = {}
        for w, i in enumerate(self.win_day):
            self.win_of_day.setdefault(i, []).append(w)
        years = range(2022, m.last.year + 1)
        self.bonus_day = {self.first_on_or_after(date(y, 3, 31)): y for y in years if bonus_paid_in(y) > 0
                          and date(y, 3, 31) <= m.last}
        self.tax_day = {self.first_on_or_after(date(y, 4, 15)): y - 1 for y in years
                        if y >= 2023 and date(y, 4, 15) <= m.last}
        self.wt = {y: wage_tax(y) for y in years}


def run(env, mode, rng=None):
    """mode: 'picks' or 'spy'. Returns dict with monthly series and end stats."""
    m = env.m
    n = env.n
    P = m.P
    cash = 0.0
    release = np.zeros(len(m.cdates) + SPREAD + 1)
    scheduled = 0.0          # cash set aside for future tranches
    committed = {}           # entry_idx -> list of (ticker, dollars)
    lots = []                # open lots: [ticker, shares, cost, entry_idx, exit_idx]
    spy_shares = 0.0
    spy_cost = 0.0
    k401_shares = 0.0
    fund = 0.0
    realized = {}            # year -> [st, lt]
    interest = {}            # year -> interest
    carry_loss = 0.0
    taxes_paid = {"wage": 0.0, "investment": 0.0}
    tax_due = {}
    slots = {}
    spent = 0.0
    gross = 0.0
    monthly = []
    win_ptr = 0
    for i, d in enumerate(m.cal):
        if i > 0:  # interest on uninvested cash (incl. scheduled + committed)
            days = (d - m.cal[i - 1]).days
            it = cash * env.rate[i - 1] * days / 365
            cash += it
            interest[d.year] = interest.get(d.year, 0.0) + it
            fund *= (1 + FUND_RET) ** (days / 365)
        y = d.year
        # sales (picks)
        for L in [L for L in lots if L[4] == i]:
            proceeds = L[1] * P[L[0]][i]
            g = proceeds - L[2]
            held_long = (m.cal[i] - m.cal[L[3]]).days > 365
            realized.setdefault(y, [0.0, 0.0])[1 if held_long else 0] += g
            cash += proceeds
            w0 = next((w for w in range(win_ptr, len(m.cdates)) if m.cdates[w] > d), len(m.cdates))
            release[w0:w0 + SPREAD] += proceeds / SPREAD
            scheduled += proceeds
            lots.remove(L)
        # bonus
        if i in env.bonus_day:
            by = env.bonus_day[i]
            b = bonus_paid_in(by)
            wtax, _ = env.wt[by]
            cash_pay = base_for(by) + (1 - DEFER) * b
            net = (1 - DEFER) * b - wtax * (1 - DEFER) * b / cash_pay
            taxes_paid["wage"] += wtax * (1 - DEFER) * b / cash_pay
            gross += b
            fund += DEFER * b
            cash += net
            w0 = next((w for w in range(win_ptr, len(m.cdates)) if m.cdates[w] > d), len(m.cdates))
            release[w0:w0 + SPREAD] += net / SPREAD
            scheduled += net
        # taxes on investment income for the previous year
        if i in env.tax_day:
            ty = env.tax_day[i]
            st, lt = realized.get(ty, [0.0, 0.0])
            wages = env.wt[ty][1]
            with_inv, carry_loss_new = income_tax(ty, wages, interest.get(ty, 0.0), st, lt, carry_loss)
            base_tax, _ = income_tax(ty, wages)
            due = with_inv - base_tax
            carry_loss = carry_loss_new
            tax_due[ty] = due
            taxes_paid["investment"] += due
            cash -= due
        # paycheck + window decisions
        for w in env.win_of_day.get(i, []):
            c = m.cdates[w]
            base = base_for(c.year)
            wtax, _ = env.wt[c.year]
            cash_pay = base + (1 - DEFER) * bonus_paid_in(c.year)
            gross_check = base / 24
            net = gross_check - K401 / 24 - wtax * gross_check / cash_pay
            taxes_paid["wage"] += wtax * gross_check / cash_pay
            gross += gross_check
            cash += net - SPEND_PER_CHECK
            spent += SPEND_PER_CHECK
            k401_shares += (K401 + MATCH) / 24 / P["SPY"][i]
            # release tranche
            scheduled -= release[w]
            win_ptr = w + 1
            budget = cash - scheduled - sum(x for v in committed.values() for _, x in v)
            if budget <= 0:
                continue
            if mode == "spy":
                spy_shares += budget / P["SPY"][i]
                spy_cost += budget
                cash -= budget
                continue
            win = m.windows[w]
            mkey = (c.year, c.month)
            left = slots.setdefault(mkey, CAP)
            later_ap = c.day == 1 and w + 1 < len(m.cdates) and any(v[1] for v in m.windows[w + 1].values())
            avail = max(0, left - (1 if later_ap else 0))
            aps = sorted(t for t, v in win.items() if v[1])
            lst = sorted(t for t, v in win.items() if not v[1])

            def pick(cands, k):
                if k <= 0:
                    return []
                return list(cands) if len(cands) <= k else list(rng.choice(cands, size=k, replace=False))
            ch = pick(aps, avail)
            ch += pick(lst, avail - len(ch))
            slots[mkey] = left - len(ch)
            if not ch:
                continue
            each = budget / len(ch)
            for t in ch:
                committed.setdefault(win[t][0], []).append((t, each))
        # execute committed buys at today's close
        for t, x in committed.pop(i, []):
            sh = x / P[t][i]
            ex = m.exit_idx[i] if i in m.exit_idx else None
            lots.append([t, sh, x, i, ex])
            cash -= x
        # month-end snapshot
        if i == n - 1 or m.cal[i + 1].month != d.month:
            mv = sum(L[1] * P[L[0]][i] for L in lots) + spy_shares * P["SPY"][i]
            monthly.append(dict(date=d, taxable=cash + mv, cash=cash, k401=k401_shares * P["SPY"][i], fund=fund))

    # end: accrued tax for the current (unfinished) year, and liquidation tax
    ly = m.last.year
    wages = env.wt[ly][1] if ly in env.wt else 0.0
    st, lt = realized.get(ly, [0.0, 0.0])
    t_real, _ = income_tax(ly, wages, interest.get(ly, 0.0), st, lt, carry_loss)
    t_base, _ = income_tax(ly, wages)
    accrued = t_real - t_base
    unreal_st = sum(L[1] * P[L[0]][-1] - L[2] for L in lots if (m.last - m.cal[L[3]]).days <= 365)
    unreal_lt = sum(L[1] * P[L[0]][-1] - L[2] for L in lots if (m.last - m.cal[L[3]]).days > 365)
    unreal_lt += spy_shares * P["SPY"][-1] - spy_cost
    t_liq, _ = income_tax(ly, wages, interest.get(ly, 0.0), st + unreal_st, lt + unreal_lt, carry_loss)
    liq_tax = t_liq - t_real
    end = monthly[-1]
    taxable_mtm = end["taxable"] - accrued
    return dict(monthly=monthly, taxable_mtm=taxable_mtm, taxable_after_liq=taxable_mtm - liq_tax,
                k401=end["k401"], fund=end["fund"], cash=end["cash"], accrued_tax=accrued, liq_tax=liq_tax,
                taxes_wage=taxes_paid["wage"], taxes_inv=taxes_paid["investment"] + accrued, spent=spent,
                gross=gross, realized=realized, interest=interest,
                net_worth=taxable_mtm + end["k401"] + end["fund"])


def main():
    env = Env()
    rng = np.random.default_rng(SEED)
    spy = run(env, "spy")
    picks = [run(env, "picks", rng) for _ in range(RUNS)]
    tv = np.array([r["taxable_mtm"] for r in picks])
    med = picks[int(np.argmin(np.abs(tv - np.median(tv))))]
    q = lambda a, p: float(np.percentile(a, p))  # noqa: E731

    rows = []
    for name, r in (("picks_median", med), ("spy", spy)):
        rows.append(dict(strategy=name, net_worth=round(r["net_worth"]), taxable_mtm=round(r["taxable_mtm"]),
                         taxable_after_liquidation=round(r["taxable_after_liq"]), k401=round(r["k401"]),
                         internal_fund=round(r["fund"]), cash_in_taxable=round(r["cash"]),
                         wage_taxes=round(r["taxes_wage"]), investment_taxes=round(r["taxes_inv"]),
                         liquidation_tax=round(r["liq_tax"]), spent=round(r["spent"]), gross_comp=round(r["gross"])))
    with open(os.path.join(OUT, "personal_finance_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    band = np.vstack([[x["taxable"] for x in r["monthly"]] for r in picks])
    with open(os.path.join(OUT, "personal_finance_monthly.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month_end", "picks_taxable_median", "picks_taxable_p5", "picks_taxable_p95", "spy_taxable",
                    "k401", "internal_fund"])
        for k, (a, b) in enumerate(zip(med["monthly"], spy["monthly"])):
            w.writerow([a["date"], round(a["taxable"]), round(np.percentile(band[:, k], 5)),
                        round(np.percentile(band[:, k], 95)), round(b["taxable"]), round(b["k401"]), round(b["fund"])])

    print(f"as of {env.m.last}; picks runs {RUNS}")
    for name, r in (("PICKS(median)", med), ("SPY", spy)):
        print(f"{name:14} net worth ${r['net_worth']:,.0f} = taxable ${r['taxable_mtm']:,.0f} "
              f"(after liquidation ${r['taxable_after_liq']:,.0f}) + 401k ${r['k401']:,.0f} + fund ${r['fund']:,.0f}")
        print(f"{'':14} cash in taxable ${r['cash']:,.0f}; investment taxes ${r['taxes_inv']:,.0f} "
              f"(incl. accrued {r['accrued_tax']:,.0f}); liquidation tax ${r['liq_tax']:,.0f}; "
              f"wage taxes ${r['taxes_wage']:,.0f}; spent ${r['spent']:,.0f}; gross comp ${r['gross']:,.0f}")
    print(f"picks taxable (mark-to-market) p5 ${q(tv,5):,.0f}  median ${q(tv,50):,.0f}  p95 ${q(tv,95):,.0f}")
    al = np.array([r["taxable_after_liq"] for r in picks])
    print(f"picks taxable after liquidation p5 ${q(al,5):,.0f}  median ${q(al,50):,.0f}  p95 ${q(al,95):,.0f}")
    print("median run realized gains by year (st, lt):", {k: [round(v[0]), round(v[1])] for k, v in med["realized"].items()})
    print("median run interest by year:", {k: round(v) for k, v in med["interest"].items()})
    print("SPY interest by year:", {k: round(v) for k, v in spy["interest"].items()})
    for y in sorted(env.wt):
        print(f"  {y}: base ${base_for(y):,.0f} bonus paid ${bonus_paid_in(y):,.0f} wage tax ${env.wt[y][0]:,.0f}")


if __name__ == "__main__":
    main()
