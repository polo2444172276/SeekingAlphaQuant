"""Does the Steven Cress / SA Quant pick set have alpha, or is it just beta?

Calendar-time portfolio: every pick (annual Top 10, H2 Top 10, Alpha Picks;
one entry per ticker per publication) is held from its first tradable close
after publication to the first close more than one year later. Each day the
portfolio return is the equal-weighted average of the daily returns of all
picks currently held (fully invested, no cash drag, no DCA timing).

Daily excess returns (over the 13-week T-bill, ^IRX) are regressed on
- CAPM: SPY
- 5-factor ETF proxies: SPY, size (IWM - SPY), value (IWD - IWF),
  momentum (MTUM - SPY), quality (QUAL - SPY)
with Newey-West (5 lags) standard errors. Alphas are annualised x252.
Sharpe ratios are compared with SPY and high-beta / small-cap / equal-weight
benchmarks (SPHB, IWM, RSP, MTUM) over the same dates.

Prices: Supabase first; ETFs missing from the DB are fetched from FMP and
cached back (seekingalpha_quant.data.market_data.load_daily).
Writes data/steve_cress/alpha_summary.csv and alpha_daily.csv.
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
ETFS = ["SPY", "IWM", "IWD", "IWF", "MTUM", "QUAL", "SPHB", "RSP", "^IRX"]
# robustness: --exclude APP,CLS,... drops those tickers (outputs get a _ex suffix)
EXCLUDE = set(sys.argv[sys.argv.index("--exclude") + 1].split(",")) if "--exclude" in sys.argv else set()
SUFFIX = "_ex" + str(len(EXCLUDE)) if EXCLUDE else ""


def add_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def ols_nw(y, X, lags=5):
    """OLS with Newey-West SEs. X without constant; returns coef (incl. const first), se, t, r2."""
    X = np.column_stack([np.ones(len(y)), X])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    r2 = 1 - e.var() / y.var()
    return b, se, b / se, r2


def main():
    picks = db.select("picks", {"select": "source,published_date,published_time,symbol"})
    tick = sorted({p["symbol"] for p in picks})
    px = load_daily(tick + ETFS, start="2021-12-01")
    cal = [r["date"] for r in px["SPY"]]
    idx = {d: i for i, d in enumerate(cal)}
    n = len(cal)

    def series(t, field="adj_close"):
        a = np.full(n, np.nan)
        for r in px.get(t, []):
            if r["date"] in idx and r[field] is not None:
                a[idx[r["date"]]] = r[field]
        for i in range(1, n):
            if np.isnan(a[i]) and not np.isnan(a[i - 1]):
                a[i] = a[i - 1]
        return a

    P = {t: series(t) for t in tick + [e for e in ETFS if e != "^IRX"]}
    irx = series("^IRX", "close")
    rf = np.nan_to_num(irx / 100 / 252, nan=0.0)
    R = {t: np.concatenate([[np.nan], P[t][1:] / P[t][:-1] - 1]) for t in P}

    # holdings: (ticker, entry_idx, exit_idx, source)
    hold = {}
    for p in picks:
        d = date.fromisoformat(p["published_date"])
        after = p["published_time"] and p["published_time"] >= "16:00"
        e = next((i for i, x in enumerate(cal) if (x > d if after else x >= d)), None)
        t = p["symbol"]
        if e is None or t not in P or np.isnan(P[t][e]) or t in EXCLUDE:
            continue
        tgt = add_year(cal[e])
        x = next((i for i in range(e, n) if cal[i] > tgt), n - 1)
        key = (t, e)
        src = "Alpha Picks" if p["source"] == "Alpha Picks" else "Top 10 lists"
        if key not in hold or src == "Alpha Picks":
            hold[key] = (t, e, x, src)

    def portfolio(filter_src=None):
        ret = np.full(n, np.nan)
        cnt = np.zeros(n, int)
        for i in range(1, n):
            rs = [R[t][i] for (t, e, x, s) in hold.values()
                  if e < i <= x and (filter_src is None or s == filter_src) and not np.isnan(R[t][i])]
            if rs:
                ret[i] = np.mean(rs)
                cnt[i] = len(rs)
        return ret, cnt

    start = idx[next(d for d in cal if d >= date(2022, 1, 20))]
    variants = {"All picks": portfolio(), "Alpha Picks only": portfolio("Alpha Picks"),
                "Top 10 lists only": portfolio("Top 10 lists")}

    def stats(r, mask):
        r, f = r[mask], rf[mask]
        ann = np.prod(1 + r) ** (252 / len(r)) - 1
        vol = r.std() * np.sqrt(252)
        sh = (r - f).mean() / r.std() * np.sqrt(252)
        nav = np.cumprod(1 + r)
        mdd = (nav / np.maximum.accumulate(nav) - 1).min()
        return ann, vol, sh, mdd

    rows = []
    for name, (ret, cnt) in variants.items():
        mask = np.zeros(n, bool)
        mask[start:] = True
        mask &= ~np.isnan(ret)
        for t in ("SPY", "IWM", "IWD", "IWF", "MTUM", "QUAL"):
            mask &= ~np.isnan(R[t])
        y = ret[mask] - rf[mask]
        mkt = R["SPY"][mask] - rf[mask]
        b1, se1, t1, r21 = ols_nw(y, mkt[:, None])
        F = np.column_stack([mkt, R["IWM"][mask] - R["SPY"][mask], R["IWD"][mask] - R["IWF"][mask],
                             R["MTUM"][mask] - R["SPY"][mask], R["QUAL"][mask] - R["SPY"][mask]])
        b5, se5, t5, r25 = ols_nw(y, F)
        ann, vol, sh, mdd = stats(ret, mask)
        resid = y - (b1[0] + b1[1] * mkt)
        ir = b1[0] * 252 / (resid.std() * np.sqrt(252))
        rows.append(dict(portfolio=name, days=int(mask.sum()), avg_holdings=round(float(cnt[mask].mean()), 1),
                         ann_return=round(ann, 4), ann_vol=round(vol, 4), sharpe=round(sh, 2), max_dd=round(mdd, 4),
                         beta=round(b1[1], 2), capm_alpha=round(b1[0] * 252, 4), capm_alpha_t=round(t1[0], 2),
                         capm_r2=round(r21, 2), info_ratio=round(ir, 2),
                         ff_alpha=round(b5[0] * 252, 4), ff_alpha_t=round(t5[0], 2), ff_r2=round(r25, 2),
                         b_mkt=round(b5[1], 2), b_size=round(b5[2], 2), b_value=round(b5[3], 2),
                         b_mom=round(b5[4], 2), b_quality=round(b5[5], 2),
                         t_size=round(t5[2], 1), t_value=round(t5[3], 1), t_mom=round(t5[4], 1),
                         t_quality=round(t5[5], 1)))
        if name == "All picks":
            base_mask = mask
    for t in ("SPY", "SPHB", "IWM", "RSP", "MTUM"):
        m = base_mask & ~np.isnan(R[t])
        ann, vol, sh, mdd = stats(R[t], m)
        b, se, tt, r2 = ols_nw(R[t][m] - rf[m], (R["SPY"][m] - rf[m])[:, None])
        rows.append(dict(portfolio=t, days=int(m.sum()), ann_return=round(ann, 4), ann_vol=round(vol, 4),
                         sharpe=round(sh, 2), max_dd=round(mdd, 4), beta=round(b[1], 2),
                         capm_alpha=round(b[0] * 252, 4), capm_alpha_t=round(tt[0], 2)))

    # calendar-year returns
    years = {}
    allret = variants["All picks"][0]
    for y_ in range(2022, cal[-1].year + 1):
        m = base_mask & np.array([d.year == y_ for d in cal])
        if m.sum() > 20:
            years[y_] = {k: float(np.prod(1 + v[m]) - 1) for k, v in
                         (("picks", allret), ("SPY", R["SPY"]), ("SPHB", R["SPHB"]), ("IWM", R["IWM"]))}

    keys = list(rows[0].keys())
    with open(os.path.join(OUT, f"alpha_summary{SUFFIX}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})
    with open(os.path.join(OUT, f"alpha_daily{SUFFIX}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "all_picks", "alpha_picks", "top10_lists", "spy", "sphb", "rf"])
        for i in np.where(base_mask)[0]:
            w.writerow([cal[i]] + [round(float(v[i]), 6) if not np.isnan(v[i]) else "" for v in
                                    (variants["All picks"][0], variants["Alpha Picks only"][0],
                                     variants["Top 10 lists only"][0], R["SPY"], R["SPHB"], rf)])
    for r in rows:
        print(r)
    print("calendar-year returns:")
    for y_, v in years.items():
        print(f"  {y_}: " + "  ".join(f"{k} {x:6.1%}" for k, x in v.items()))


if __name__ == "__main__":
    main()
