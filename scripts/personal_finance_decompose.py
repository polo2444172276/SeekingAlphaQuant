"""Why the picks account beats SPY by less than per-pick returns suggest:
re-run scripts/personal_finance_sim.py under variants that switch off one
friction at a time (median of N random runs each), plus time-weighted CAGR.

Usage: python scripts/personal_finance_decompose.py [--runs 40]
"""
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.argv = [a for a in sys.argv]  # keep flags for personal_finance_sim
import personal_finance_sim as pf  # noqa: E402

RUNS = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 40
_real_tax = pf.income_tax


def no_inv_tax(year, wages, interest=0.0, st=0.0, lt=0.0, carry_loss=0.0):
    return _real_tax(year, wages)


def variant(env, name, spread=12, inv_tax=True):
    pf.SPREAD = spread
    pf.income_tax = _real_tax if inv_tax else no_inv_tax
    spy = pf.run(env, "spy")
    picks = [pf.run(env, "picks", np.random.default_rng(pf.SEED + k)) for k in range(RUNS)]
    tv = np.median([r["taxable_mtm"] for r in picks])
    cash = np.median([r["cash"] for r in picks])
    tax = np.median([r["taxes_inv"] for r in picks])
    pf.income_tax = _real_tax
    return dict(variant=name, picks_taxable=round(tv), spy_taxable=round(spy["taxable_mtm"]),
                gap=round(tv - spy["taxable_mtm"]), picks_cash_end=round(cash), picks_inv_tax=round(tax),
                spy_inv_tax=round(spy["taxes_inv"]))


def twr_cagr():
    rows = list(csv.DictReader(open(os.path.join(pf.OUT, "personal_finance_nav.csv"))))
    d0, d1 = rows[0]["date"], rows[-1]["date"]
    yrs = (np.datetime64(d1) - np.datetime64(d0)).astype(int) / 365.25
    out = {}
    for k in list(rows[0])[1:]:
        out[k] = float(rows[-1][k]) / float(rows[0][k])
        out[k] = (out[k], out[k] ** (1 / yrs) - 1)
    return d0, d1, out


def main():
    env = pf.Env()
    res = [variant(env, "baseline (taxes, 12-tranche proceeds & bonus)"),
           variant(env, "no tax on investment income", inv_tax=False),
           variant(env, "proceeds & bonus invested immediately", spread=1),
           variant(env, "no investment tax + immediate", spread=1, inv_tax=False)]
    with open(os.path.join(pf.OUT, "personal_finance_decompose.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(res)
    for r in res:
        print(r)
    d0, d1, tw = twr_cagr()
    print(f"time-weighted growth {d0}..{d1}:", {k: (round(v[0], 3), f"{v[1]:.1%}") for k, v in tw.items()})


if __name__ == "__main__":
    main()
