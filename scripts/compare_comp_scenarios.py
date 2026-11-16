"""Deterministic cash accounting 2022-2031 for the two career scenarios:
baseline (scripts/personal_finance_projection.py) vs job change
(scripts/scenario_jump_700k.py). Market-independent: comp, wage taxes,
deferrals, spending and net cash that reaches the taxable account.

Writes data/steve_cress/comp_scenarios_compare.csv.
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import personal_finance_sim as pf  # noqa: E402
import personal_finance_projection as proj  # noqa: E402

YEARS = range(2022, 2032)
SPEND = 12 * 7_100.0


def ledger():
    rows = []
    for y in YEARS:
        base, cash_b, wages, wtax = proj.year_wages(y)
        deferred = proj.bonus_paid(y)[1]
        net = base - pf.K401 - wtax - SPEND + cash_b
        rows.append(dict(year=y, base=base, bonus_paid=cash_b + deferred, gross=base + cash_b + deferred,
                         wage_tax=wtax, deferred=deferred, net_to_taxable=net))
    return rows


def main():
    base_rows = ledger()
    base_unpaid = proj.total_comp(2031) - proj.base_y(2031)
    import scenario_jump_700k as sc
    pf.base_for = sc.base
    pf.bonus_paid_in = sc.bonus_paid_in
    proj.NONCOMPETE = sc.NONCOMPETE
    proj.base_y = sc.base
    proj.bonus_paid = sc.proj_bonus_paid
    sc_rows = ledger()
    sc_unpaid = sc.total_comp(2031) - sc.base(2031)

    with open(os.path.join(pf.OUT, "comp_scenarios_compare.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "base_gross", "jump_gross", "base_wage_tax", "jump_wage_tax", "base_deferred",
                    "jump_deferred", "base_net_to_taxable", "jump_net_to_taxable"])
        for a, b in zip(base_rows, sc_rows):
            w.writerow([a["year"]] + [round(v) for v in (a["gross"], b["gross"], a["wage_tax"], b["wage_tax"],
                                                         a["deferred"], b["deferred"], a["net_to_taxable"],
                                                         b["net_to_taxable"])])
    print(f"{'year':5}{'gross base':>12}{'gross jump':>12}{'tax base':>11}{'tax jump':>11}"
          f"{'net base':>11}{'net jump':>11}{'defer b':>10}{'defer j':>10}")
    tot = {k: [0.0, 0.0] for k in ("gross", "wage_tax", "net_to_taxable", "deferred")}
    for a, b in zip(base_rows, sc_rows):
        print(f"{a['year']:<5}{a['gross']:>12,.0f}{b['gross']:>12,.0f}{a['wage_tax']:>11,.0f}{b['wage_tax']:>11,.0f}"
              f"{a['net_to_taxable']:>11,.0f}{b['net_to_taxable']:>11,.0f}{a['deferred']:>10,.0f}{b['deferred']:>10,.0f}")
        for k in tot:
            tot[k][0] += a[k]
            tot[k][1] += b[k]
    print("TOTAL", {k: [round(v[0]), round(v[1]), round(v[1] - v[0])] for k, v in tot.items()})
    print(f"bonus earned for 2031 but paid in 2032 (outside horizon): base ${base_unpaid:,.0f}, jump ${sc_unpaid:,.0f}")


if __name__ == "__main__":
    main()
