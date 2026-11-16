"""Scenario: job change after 3 years to $700k total comp.

Timeline (2022 .. end of 2031), everything else as personal_finance_sim.py /
personal_finance_projection.py:
- 2022-2024: original job, total comp $300k x 1.12^n (base 7/12, bonus 5/12,
  bonus paid the following March, 20% of each bonus deferred pre-tax into the
  internal fund at 20%/yr).
- 2025: one-year non-compete. Base continues at the original trajectory
  ($245,862), 401k + match continue, no bonus for 2025 work (nothing paid in
  March 2026). The old internal fund is paid out on 2025-12-31, taxed at the
  2025 average income-tax rate of wages, and goes to the taxable account.
- 2026+: new job, total comp $700k in 2026, +5%/yr, capped at $1M; base capped
  at $300k, the rest is bonus (paid the following March). The new employer
  has the same 20% pre-tax deferral into an internal fund at 20%/yr, not
  withdrawn within the horizon.

Writes to data/steve_cress/scenario_jump_700k/ (projection_summary.csv,
projection_monthly.csv, projection.html).
"""
import csv
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import personal_finance_sim as pf  # noqa: E402
import personal_finance_projection as proj  # noqa: E402
import personal_finance_projection_chart as chart  # noqa: E402

OUT = os.path.join(pf.OUT, "scenario_jump_700k")
NONCOMPETE = 2025
NEW_START, NEW_TOTAL, NEW_RAISE, NEW_CAP, BASE_CAP = 2026, 700_000.0, 0.05, 1_000_000.0, 300_000.0


def total_comp(y):
    if y < NONCOMPETE:
        return (pf.BASE0 + pf.BONUS0) * (1 + pf.RAISE) ** (y - 2022)
    if y == NONCOMPETE:
        return None
    return min(NEW_CAP, NEW_TOTAL * (1 + NEW_RAISE) ** (y - NEW_START))


def base(y):
    if y <= NONCOMPETE:
        return pf.BASE0 * (1 + pf.RAISE) ** (y - 2022)
    return min(BASE_CAP, total_comp(y))


def bonus_paid_in(y):
    """Gross bonus paid in March of year y (for work in y-1)."""
    if y <= 2022 or y - 1 == NONCOMPETE:
        return 0.0
    return total_comp(y - 1) - base(y - 1)


def proj_bonus_paid(y):
    b = bonus_paid_in(y)
    return b * (1 - pf.DEFER), b * pf.DEFER


def main():
    os.makedirs(OUT, exist_ok=True)
    pf.base_for = base
    pf.bonus_paid_in = bonus_paid_in
    w25 = base(2025) + (1 - pf.DEFER) * bonus_paid_in(2025) - pf.K401
    rate25 = pf.income_tax(2025, w25)[0] / w25
    pf.FUND_PAYOUT = (date(2025, 12, 31), rate25)
    proj.NONCOMPETE = NONCOMPETE
    proj.base_y = base
    proj.bonus_paid = proj_bonus_paid
    proj.OUT = OUT
    print(f"old fund paid out 2025-12-31 at {rate25:.1%} (2025 wages ${w25:,.0f})")
    for y in range(2022, 2032):
        print(f"  {y}: total {('$%s' % format(round(total_comp(y)), ',')) if total_comp(y) else 'non-compete':>12}  "
              f"base ${base(y):,.0f}  bonus paid in March ${bonus_paid_in(y):,.0f}")
    proj.main()

    chart.D_DIR = OUT
    chart.TEMPLATE = chart.TEMPLATE.replace(
        "<h1>到 2031 年底的总资产：SA 推荐股 vs 大盘</h1>",
        "<h1>情景：2025 年竞业限制后跳槽到 $70 万：到 2031 年底的总资产</h1>").replace(
        chart.TEMPLATE[chart.TEMPLATE.index('<p class="note">'):chart.TEMPLATE.index("</p>\n</div><script>")],
        '<p class="note">情景假设：2022–2024 年原工作（总包 $30 万起每年 +12%）；2025 年竞业限制，只发 base '
        '（$245,862），当年工作没有 bonus，老公司内部基金 2025-12-31 按当年工资平均所得税率 '
        f'（{rate25:.1%}）扣税后转入应税账户；2026 年起新工作总包 $70 万、每年 +5%、封顶 $100 万，base 封顶 $30 万，'
        '其余为 bonus（次年 3 月发），20% 税前递延进新公司内部基金（年化 20%，不取出）。生活开支每月 $7,100，'
        '401k $1 万 + 配比 $1 万。未来收益：2022-02 至 2026-10 真实月度收益成对随机抽样 1000 次；'
        '推荐股每笔持有满 12 个月卖出再买入并交资本利得税，SPY 一直不卖。抽样期是推荐股表现特别好的一段时期，未来未必重现。')
    chart.main()

    base_s = {(r["strategy"], r["metric"]): r for r in csv.DictReader(open(os.path.join(pf.OUT, "projection_summary.csv")))}
    new_s = {(r["strategy"], r["metric"]): r for r in csv.DictReader(open(os.path.join(OUT, "projection_summary.csv")))}
    print("\nmedian at end-2031: scenario vs previous projection")
    for k in sorted(new_s):
        print(f"  {k[0]:5} {k[1]:10} ${float(new_s[k]['median']):>12,.0f}   prev ${float(base_s[k]['median']):>12,.0f}")


if __name__ == "__main__":
    main()
