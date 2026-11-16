"""Backtest: each year buy the 10 largest S&P 500 members by market cap, hold to year end.

Formation: on the second-to-last trading day of year Y-1, rank the then-current
S&P 500 members (point-in-time `index_membership`) by FMP historical market cap.
Entry: the next close (last trading day of Y-1), i.e. the first price a trader
could act on after seeing the ranking. Exit: last close of year Y.
Equal-weight and cap-weight portfolios, benchmark SPY. Returns use adj_close
(dividends reinvested). One share class per company (GOOG dropped for GOOGL, etc.).

Data: prices from the Supabase Parquet files; market caps from FMP, cached to
data/top10_mcap/market_caps.csv. Output: CSVs + log cumulative return chart.
"""
import io
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seekingalpha_quant.data import supabase_db as db  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "top10_mcap")
DUP_CLASSES = {"GOOG", "FOX", "NWS"}  # keep GOOGL / FOXA / NWSA
N = 10


def load_prices():
    files = [r["path"] for r in db.select("data_files", {"select": "path"})
             if r["path"].startswith("us/sp500/prices_daily/")]
    frames = [pd.read_parquet(io.BytesIO(db.download(p))) for p in sorted(files)]
    return pd.concat(frames, ignore_index=True)


def fetch_mcaps(symbols, start, end):
    """FMP daily market caps, cached; resumes, retries 429s, records empties."""
    path = os.path.join(OUT, "market_caps.csv")
    done_path = os.path.join(OUT, "market_caps_done.txt")
    have = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=["symbol", "date", "market_cap"])
    done = set(open(done_path).read().split()) if os.path.exists(done_path) else set(have["symbol"])
    todo = [x for x in symbols if x not in done]
    s = requests.Session()
    rows = []
    for k, sym in enumerate(todo):
        fmp_sym = sym.replace("-", ".") if sym in ("BRK-B", "BF-B") else sym
        for attempt in range(8):
            r = s.get("https://financialmodelingprep.com/stable/historical-market-capitalization",
                      params={"symbol": fmp_sym, "from": start, "to": end, "limit": 5000}, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(min(60, 5 * 2 ** attempt))
        if r.status_code == 200 and isinstance(r.json(), list):
            rows += [{"symbol": sym, "date": x["date"], "market_cap": x["marketCap"]} for x in r.json()]
        elif r.status_code == 429:
            print("giving up on", sym, "(429)")
            continue
        done.add(sym)
        time.sleep(0.25)
        if k % 50 == 49 or k == len(todo) - 1:
            have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
            rows = []
            have.to_csv(path, index=False)
            open(done_path, "w").write("\n".join(sorted(done)))
            print(f"market caps: {k + 1}/{len(todo)}", flush=True)
    have["date"] = pd.to_datetime(have["date"])
    return have


def ensure_spy(start):
    """SPY adj_close from Supabase; backfill missing history from Yahoo and write it back."""
    sid = db.security_ids("US")["SPY"]
    rows = db.select("prices_daily", {"security_id": f"eq.{sid}", "select": "date,adj_close"})
    spy = pd.Series({pd.Timestamp(r["date"]): r["adj_close"] for r in rows}).sort_index()
    if len(spy) and spy.index[0] <= pd.Timestamp(start) + pd.Timedelta(days=5):
        return spy
    p1 = int(pd.Timestamp(start).timestamp())
    p2 = int((spy.index[0] if len(spy) else pd.Timestamp.now()).timestamp())
    j = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY",
                     params={"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=60).json()["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    ac = j["indicators"]["adjclose"][0]["adjclose"]
    new = []
    for i, t in enumerate(j["timestamp"]):
        d = pd.Timestamp(t, unit="s").normalize()
        if (len(spy) and d >= spy.index[0]) or ac[i] is None:
            continue
        new.append({"security_id": sid, "date": str(d.date()), "open": q["open"][i], "high": q["high"][i],
                    "low": q["low"][i], "close": q["close"][i], "adj_close": ac[i],
                    "volume": q["volume"][i], "source": "yahoo"})
    if new:
        db.upsert("prices_daily", new, on_conflict="security_id,date")
        print(f"SPY: wrote {len(new)} backfilled rows to prices_daily")
    rows = db.select("prices_daily", {"security_id": f"eq.{sid}", "select": "date,adj_close"})
    return pd.Series({pd.Timestamp(r["date"]): r["adj_close"] for r in rows}).sort_index()


def main():
    os.makedirs(OUT, exist_ok=True)
    secs = pd.DataFrame(db.select("securities", {"market": "eq.US", "select": "id,symbol"}))
    mem = pd.DataFrame(db.select("index_membership", {"index_code": "eq.SP500"}))
    mem = mem.merge(secs, left_on="security_id", right_on="id")
    mem["start_date"] = pd.to_datetime(mem["start_date"])
    mem["end_date"] = pd.to_datetime(mem["end_date"])

    px = load_prices()
    px["date"] = pd.to_datetime(px["date"])
    if "symbol" not in px.columns:
        px = px.merge(secs, left_on="security_id", right_on="id")
    adj = px.pivot_table(index="date", columns="symbol", values="adj_close").sort_index()
    adj["SPY"] = ensure_spy(str(adj.index[0].date()))

    dates = adj.index
    years = sorted({d.year for d in dates if d.year >= dates[0].year + 1})

    # formation dates: second-to-last trading day of each prior year
    form = {}
    for y in years:
        prev = dates[dates.year == y - 1]
        form[y] = (prev[-2], prev[-1])  # (rank date, entry date)

    mc = fetch_mcaps(sorted(set(mem["symbol"])), f"{years[0]-1}-12-01", f"{years[-1]-1}-12-31")

    picks, rets = [], []
    daily_ew, daily_cw = [], []
    for y in years:
        rank_d, entry_d = form[y]
        members = mem[(mem.start_date <= rank_d) & (mem.end_date.isna() | (mem.end_date > rank_d))]["symbol"]
        members = set(members) - DUP_CLASSES
        snap = mc[(mc.date <= rank_d) & (mc.date > rank_d - pd.Timedelta(days=7)) & mc.symbol.isin(members)]
        snap = snap.sort_values("date").groupby("symbol").last()
        top = snap.sort_values("market_cap", ascending=False).head(N)
        w_cw = top["market_cap"] / top["market_cap"].sum()

        period = adj.loc[(adj.index >= entry_d) & (adj.index <= dates[dates.year == y][-1]), list(top.index) + ["SPY"]]
        period = period.ffill()  # delisting mid-year: hold last price (none in practice for mega caps)
        rel = period / period.iloc[0]
        ew = rel[top.index].mean(axis=1)
        cw = (rel[top.index] * w_cw).sum(axis=1)
        daily_ew.append(ew.pct_change().dropna())
        daily_cw.append(cw.pct_change().dropna())
        for i, (sym, row) in enumerate(top.iterrows(), 1):
            picks.append({"year": y, "rank": i, "symbol": sym, "market_cap_bn": round(row.market_cap / 1e9, 1),
                          "rank_date": rank_d.date(), "return": rel[sym].iloc[-1] - 1})
        rets.append({"year": y, "end": period.index[-1].date(), "EW_top10": ew.iloc[-1] - 1,
                     "CW_top10": cw.iloc[-1] - 1, "SPY": rel["SPY"].iloc[-1] - 1})

    picks = pd.DataFrame(picks)
    rets = pd.DataFrame(rets)
    ew = pd.concat(daily_ew)
    cw = pd.concat(daily_cw)
    spy = adj["SPY"].loc[ew.index[0] - pd.Timedelta(days=5):].pct_change().loc[ew.index]
    curves = pd.DataFrame({"EW_top10": np.log1p(ew).cumsum(), "CW_top10": np.log1p(cw).cumsum(),
                           "SPY": np.log1p(spy).cumsum()})
    picks.to_csv(os.path.join(OUT, "picks.csv"), index=False)
    rets.to_csv(os.path.join(OUT, "annual_returns.csv"), index=False)
    curves.to_csv(os.path.join(OUT, "log_cum_returns.csv"))

    yrs = (curves.index[-1] - curves.index[0]).days / 365.25
    stats = {}
    for c, d in {"EW_top10": ew, "CW_top10": cw, "SPY": spy}.items():
        eq = np.exp(curves[c])
        stats[c] = {"log_cum": curves[c].iloc[-1], "total": eq.iloc[-1] - 1,
                    "CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "vol": d.std() * np.sqrt(252),
                    "sharpe(rf=0)": d.mean() / d.std() * np.sqrt(252),
                    "maxDD": (eq / eq.cummax() - 1).min()}
    stats = pd.DataFrame(stats).T
    stats.to_csv(os.path.join(OUT, "summary.csv"))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for c, col in zip(curves.columns, ["#1f6feb", "#d97706", "#6b7280"]):
        ax.plot(curves.index, curves[c], label=f"{c}  (log cum {curves[c].iloc[-1]:.2f})", color=col, lw=1.6)
    for y in years:
        ax.axvline(form[y][1], color="#e5e7eb", lw=0.8, zorder=0)
    ax.axhline(0, color="#9ca3af", lw=0.8)
    ax.set_title("Top-10 S&P 500 by market cap, rebalanced yearly — log cumulative return")
    ax.set_ylabel("log(1 + cumulative return)")
    ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "log_cum_returns.png"), dpi=160)

    db.insert("analysis_results", [{
        "analysis": "top10_mcap_yearly",
        "params": {"n": N, "universe": "SP500 point-in-time", "rank": "2nd-last trading day of Y-1",
                   "entry": "last close of Y-1", "exit": "last close of Y"},
        "result": {"summary": stats.reset_index().rename(columns={"index": "portfolio"}).to_dict("records"),
                   "annual": rets.astype({"end": str}).to_dict("records"),
                   "picks": picks.astype({"rank_date": str}).to_dict("records")},
    }])

    pd.set_option("display.width", 200)
    print(picks.pivot(index="rank", columns="year", values="symbol").to_string())
    print()
    print(rets.to_string(index=False, float_format=lambda v: f"{v:.1%}"))
    print()
    print(stats.to_string(float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
