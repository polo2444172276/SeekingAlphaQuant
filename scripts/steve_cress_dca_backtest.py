"""Semi-monthly DCA into Seeking Alpha / Steven Cress picks, 1-year hold.

Rules
- On the 1st and 15th of every month from 2022-01-01, $50 arrives.
- That money (plus any cash left over from windows with no picks) is split
  equally across every distinct ticker SA recommends in the next half-month
  window [this contribution date, next contribution date), from all three
  sources (annual Top 10, H2 Top 10, Alpha Picks). Windows with no picks
  carry the cash forward.
- Each lot is bought at the first close a reader could trade at after
  publication (same session for pre-market/intraday/date-only, next session
  for after-16:00) and sold at the first close strictly more than one year
  later (long-term capital gain). Sale proceeds stay in cash (not reinvested).
- Dividend-adjusted closes (dividends reinvested within each lot). Delisted
  names are held as cash at their last price after delisting.
- Lots still open are marked to the latest close.
- Benchmark: the same dollars on the same entry days buy SPY, same exit rule.

PnL = cash + market value - contributions (principal excluded).
Data: Supabase first (picks, prices_daily); missing prices fetched from FMP
and cached back into the DB.

Writes data/steve_cress/dca_backtest_daily.csv and dca_backtest_lots.csv.
"""
import csv
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seekingalpha_quant.data import supabase_db as db  # noqa: E402
from seekingalpha_quant.data.market_data import load_daily  # noqa: E402

OUT = os.path.join(ROOT, "data", "steve_cress")
AMOUNT = 50.0
START = date(2022, 1, 1)


def add_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def contribution_dates(start, end):
    d = start
    while d <= end:
        yield d
        d = date(d.year, d.month, 15) if d.day == 1 else (date(d.year + (d.month == 12), d.month % 12 + 1, 1))


def xirr(flows):
    def npv(r):
        t0 = flows[0][0]
        return sum(v / (1 + r) ** ((d - t0).days / 365.25) for d, v in flows)
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return mid


def main():
    picks = db.select("picks", {"select": "source,published_date,published_time,symbol"})
    tickers = sorted({p["symbol"] for p in picks} | {"SPY"})
    px = load_daily(tickers, start="2021-12-01")
    cal = [r["date"] for r in px["SPY"]]
    last = cal[-1]
    adj = {t: {r["date"]: r["adj_close"] for r in rows} for t, rows in px.items()}

    def entry_day(p):
        d = date.fromisoformat(p["published_date"])
        after = p["published_time"] and p["published_time"] >= "16:00"
        return next((c for c in cal if (c > d if after else c >= d)), None)

    def price_on(t, d):
        """adj close on d, or last known before d (flat after delisting)."""
        s = adj.get(t, {})
        if d in s:
            return s[d]
        prior = [x for x in s if x <= d]
        return s[max(prior)] if prior else None

    cdates = list(contribution_dates(START, last))
    lots, carry, skipped = [], 0.0, []
    for i, c in enumerate(cdates):
        nxt = cdates[i + 1] if i + 1 < len(cdates) else date(9999, 1, 1)
        win = {}
        for p in picks:
            d = date.fromisoformat(p["published_date"])
            if c <= d < nxt:
                e = entry_day(p)
                if e is None or not adj.get(p["symbol"]) or e not in adj[p["symbol"]]:
                    skipped.append((p["symbol"], p["published_date"], "no entry price"))
                    continue
                if p["symbol"] not in win or e < win[p["symbol"]][0]:
                    win[p["symbol"]] = (e, p["source"])
        budget = AMOUNT + carry
        if not win:
            carry = budget
            continue
        carry = 0.0
        each = budget / len(win)
        for t, (e, src) in win.items():
            x = next((cc for cc in cal if cc > add_year(e)), None)
            lots.append(dict(window=c, ticker=t, source=src, entry=e, exit=x if x and x <= last else None,
                             dollars=each, shares=each / adj[t][e], spy_shares=each / adj["SPY"][e]))

    daily = []
    for d in cal:
        if d < date(2022, 1, 3):
            continue
        contrib = AMOUNT * sum(1 for c in cdates if c <= d)
        cash = contrib
        cash_spy = contrib
        mv = mv_spy = 0.0
        n_open = 0
        for L in lots:
            if L["entry"] > d:
                continue
            cash -= L["dollars"]
            cash_spy -= L["dollars"]
            if L["exit"] and L["exit"] <= d:
                cash += L["shares"] * price_on(L["ticker"], L["exit"])
                cash_spy += L["spy_shares"] * adj["SPY"][L["exit"]]
            else:
                mv += L["shares"] * price_on(L["ticker"], d)
                mv_spy += L["spy_shares"] * adj["SPY"][d]
                n_open += 1
        daily.append(dict(date=d, contributions=contrib, cash=round(cash, 2), market_value=round(mv, 2),
                          pnl=round(cash + mv - contrib, 2), spy_cash=round(cash_spy, 2),
                          spy_market_value=round(mv_spy, 2), spy_pnl=round(cash_spy + mv_spy - contrib, 2),
                          open_lots=n_open))

    with open(os.path.join(OUT, "dca_backtest_daily.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0]))
        w.writeheader()
        w.writerows(daily)
    for L in lots:
        end = L["exit"] or last
        L["exit_value"] = L["shares"] * price_on(L["ticker"], end)
        L["return"] = L["exit_value"] / L["dollars"] - 1
        L["spy_return"] = adj["SPY"][end] / adj["SPY"][L["entry"]] - 1
    with open(os.path.join(OUT, "dca_backtest_lots.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window", "ticker", "source", "entry", "exit", "status", "dollars", "exit_value",
                    "return", "spy_return"])
        for L in lots:
            w.writerow([L["window"], L["ticker"], L["source"], L["entry"], L["exit"] or last,
                        "closed" if L["exit"] else "open", round(L["dollars"], 2), round(L["exit_value"], 2),
                        round(L["return"], 4), round(L["spy_return"], 4)])

    end = daily[-1]
    flows = [(c, -AMOUNT) for c in cdates]
    print(f"period {daily[0]['date']} .. {end['date']}; contributions {len(cdates)} x ${AMOUNT:.0f} = ${end['contributions']:.0f}")
    print(f"lots {len(lots)} (closed {sum(1 for L in lots if L['exit'])}, open {sum(1 for L in lots if not L['exit'])}); skipped {skipped}")
    for name, k_pnl, k_cash, k_mv in (("Picks", "pnl", "cash", "market_value"), ("SPY", "spy_pnl", "spy_cash", "spy_market_value")):
        tv = end[k_cash] + end[k_mv]
        irr = xirr(flows + [(end["date"], tv)])
        peak, mdd = -1e9, 0
        for r in daily:
            peak = max(peak, r[k_pnl])
            mdd = min(mdd, r[k_pnl] - peak)
        print(f"{name:5} PnL ${end[k_pnl]:,.0f}  value ${tv:,.0f}  money-weighted IRR {irr:.1%}  "
              f"max PnL drawdown ${mdd:,.0f}")
    for y in range(2022, last.year + 1):
        r = [x for x in daily if x["date"].year == y][-1]
        print(f"  {r['date']}  contrib ${r['contributions']:,.0f}  PnL ${r['pnl']:,.0f}  SPY PnL ${r['spy_pnl']:,.0f}")
    closed = [L for L in lots if L["exit"]]
    print(f"closed lots: mean {sum(L['return'] for L in closed)/len(closed):.1%}, "
          f"beat SPY {sum(L['return'] > L['spy_return'] for L in closed)/len(closed):.0%}")
    top = sorted(lots, key=lambda L: L["exit_value"] - L["dollars"], reverse=True)
    print("top PnL contributors:", [(L["ticker"], str(L["entry"]), round(L["exit_value"] - L["dollars"], 1)) for L in top[:8]])
    print("worst:", [(L["ticker"], str(L["entry"]), round(L["exit_value"] - L["dollars"], 1)) for L in top[-5:]])


if __name__ == "__main__":
    main()
