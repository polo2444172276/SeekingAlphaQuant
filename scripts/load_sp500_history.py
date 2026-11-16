"""Load daily prices since 2018-11-01 for every stock that has been in the
S&P 500 since then into the shared Supabase database, plus SP500
index_membership rows and per-year Parquet snapshots in Storage.

Universe = current members (data/sp500_constituents.csv)
         U every ticker added/removed in data/sp500_membership_changes.csv (2019-01-18 on)
         U members removed 2018-11-01..2019-01-17 (the gap before the changes
           file starts), taken from fja05680/sp500 sp500_ticker_start_end.csv,
           the same community source update_membership_history.py uses.

Prices: Yahoo chart API (source 'yahoo'); if Yahoo has nothing, FMP
/stable/historical-price-eod (source 'fmp'). Zero-volume rows are dropped.
API keys are injected by the session's network proxy (placeholders sent).

Idempotent / resumable:
  * all writes are upserts on natural keys;
  * a ticker is skipped (unless --force) when prices_daily already has a row
    on/before 2018-11-05, or when securities.listed_date is set (the ticker
    started trading inside the window) and a row exists on that date;
  * fetched series are cached as JSON under --cache-dir, so a rerun does not
    re-download, and the Parquet export is built from that cache.

Usage:
  python scripts/load_sp500_history.py [--force] [--limit N] [--tickers AAPL,MSFT]
                                       [--no-parquet] [--cache-dir DIR]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seekingalpha_quant.data import supabase_db as db  # noqa: E402

START = date(2018, 11, 1)
START_EPOCH = int(datetime(2018, 11, 1, tzinfo=timezone.utc).timestamp())  # 1541030400
SKIP_CUTOFF = "2018-11-05"
INDEX = "SP500"
BATCH = 5000
CONSTITUENTS = os.path.join(ROOT, "data", "sp500_constituents.csv")
CHANGES = os.path.join(ROOT, "data", "sp500_membership_changes.csv")
GAP_SOURCE = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
FMP = "https://financialmodelingprep.com/stable/historical-price-eod"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{t}"
# FMP splices a predecessor under these symbols (FOX: 21st Century Fox until 2019-03-12,
# then the new Fox Corp at a ~23% lower price), so keep Yahoo's post-spin series.
YAHOO_ONLY = {"FOX"}

_http = requests.Session()


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def http_json(url, headers=None, params=None, tries=6):
    """GET JSON; None on 404/400; retries with backoff on 429/5xx/network errors."""
    for attempt in range(tries):
        try:
            r = _http.get(url, headers=headers, params=params, timeout=30)
            if r.status_code in (400, 404):
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == tries - 1:
                raise RuntimeError(f"GET {url.split('?')[0]} failed: {e}") from e
            time.sleep(min(60, 2 ** attempt + 0.5))


# ---------------------------------------------------------------- universe

def build_universe():
    """-> (meta {ticker: {name, sector}}, intervals {ticker: [(start, end|None, source)]}, notes)."""
    meta, notes = {}, []
    current = set()
    for r in csv.DictReader(open(CONSTITUENTS)):
        t = r["ticker"].strip().replace(".", "-")
        current.add(t)
        meta[t] = {"name": r.get("name") or None, "sector": r.get("sector") or None}
    events = {}
    changes = list(csv.DictReader(open(CHANGES)))
    first_change = min(r["date"] for r in changes)
    for r in changes:
        t = r["ticker"].strip().replace(".", "-")
        events.setdefault(t, []).append((r["date"], r["action"]))
        meta.setdefault(t, {"name": None, "sector": None})

    # Gap before the changes file: members on 2018-11-01 removed before it starts,
    # and true add dates for tickers added in the gap.
    gap_removed, gap_added = {}, {}
    try:
        txt = _http.get(GAP_SOURCE, timeout=30).text
        for r in csv.DictReader(io.StringIO(txt)):
            t = r["ticker"].strip().replace(".", "-")
            s, e = r["start_date"], r["end_date"] or None
            if s <= START.isoformat() and e and START.isoformat() <= e < first_change:
                gap_removed[t] = e
            if START.isoformat() < s < first_change:
                gap_added[t] = s
    except Exception as e:  # noqa: BLE001
        notes.append(f"gap source unavailable ({e}); removals 2018-11-01..{first_change} missing")
    for t, e in gap_removed.items():
        meta.setdefault(t, {"name": None, "sector": None})
    notes.append(f"gap removals {START}..{first_change}: {sorted(gap_removed.items())}")
    notes.append(f"gap additions {START}..{first_change}: {sorted(gap_added.items())}")

    intervals = {}
    for t in sorted(meta):
        ev = sorted(events.get(t, []))
        iv, open_start, src = [], None, "sp500_membership_changes.csv"
        if t in gap_removed:
            iv.append((gap_added.get(t, START.isoformat()), gap_removed[t], "fja05680 start_end"))
        elif (ev and ev[0][1] == "remove") or (not ev and t in current):
            open_start = gap_added.get(t, START.isoformat())  # member before the changes file starts
        for d, a in ev:
            if a == "add":
                if open_start is None:
                    open_start = d
            else:
                if open_start is not None:
                    iv.append((open_start, d, src))
                    open_start = None
                else:
                    notes.append(f"{t}: remove on {d} without open membership")
        if open_start is not None:
            iv.append((open_start, None, src))
            if t not in current:
                notes.append(f"{t}: open membership but not in current constituents")
        elif t in current:
            notes.append(f"{t}: current constituent but membership closed in changes file")
        intervals[t] = iv
    return meta, intervals, notes


# ---------------------------------------------------------------- fetchers

def fetch_yahoo(t):
    js = http_json(YAHOO.format(t=t), headers={"User-Agent": "research-script/1.0"},
                   params={"period1": START_EPOCH, "period2": 9999999999, "interval": "1d", "events": "div,splits"})
    if not js or not (js.get("chart") or {}).get("result"):
        return [], {}
    res = js["chart"]["result"][0]
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    if not q.get("close"):
        return [], {}
    adj = ((res["indicators"].get("adjclose") or [{}])[0].get("adjclose")) or q["close"]
    vol = q.get("volume") or [None] * len(q["close"])
    out = []
    for i, ts in enumerate(res.get("timestamp") or []):
        o, h, lo, c, a, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i], vol[i]
        if None in (o, h, lo, c, a) or not v:
            continue
        d = datetime.fromtimestamp(ts + (res["meta"].get("gmtoffset") or 0), timezone.utc).date()
        if d < START:
            continue
        out.append([d.isoformat(), o, h, lo, c, a, int(v)])
    m = res.get("meta") or {}
    return out, {"name": m.get("longName") or m.get("shortName"), "exchange": m.get("fullExchangeName"),
                 "currency": m.get("currency")}


def fetch_fmp(t):
    h = {"apikey": "proxy-injected"}
    full = http_json(f"{FMP}/full", headers=h, params={"symbol": t, "from": START.isoformat()}) or []
    if not isinstance(full, list) or not full:
        return []
    adj = http_json(f"{FMP}/dividend-adjusted", headers=h, params={"symbol": t, "from": START.isoformat()}) or []
    adj = {x["date"]: x.get("adjClose") for x in adj if isinstance(x, dict)}
    out = []
    for x in sorted(full, key=lambda x: x["date"]):
        if not x.get("volume") or x.get("close") is None:
            continue
        out.append([x["date"], x["open"], x["high"], x["low"], x["close"], adj.get(x["date"]) or x["close"],
                    int(x["volume"])])
    return out


def overlaps(rows, iv):
    """True if the series has data inside some membership interval (else: ticker reused by another issuer)."""
    if not rows or not iv:
        return bool(rows)
    lo, hi = rows[0][0], rows[-1][0]
    return any(lo <= (e or "9999") and hi >= s for s, e, _ in iv)


def fetch(t, cache_dir, force, iv=None):
    path = os.path.join(cache_dir, f"{t.replace('^', '_')}.json")
    if os.path.exists(path) and not force:
        return json.load(open(path)), True
    rows, info = fetch_yahoo(t)
    src, note = "yahoo", None
    if rows and not overlaps(rows, iv):
        note = f"yahoo series {rows[0][0]}..{rows[-1][0]} is outside membership (ticker reused)"
        rows = []
    ms = min((s_ for s_, _, _ in iv or []), default=START.isoformat())
    if rows and t not in YAHOO_ONLY and (date.fromisoformat(rows[0][0]) - date.fromisoformat(ms)).days > 10:
        # Yahoo sometimes keeps only the last few days of a delisted/merged name; prefer FMP if longer
        alt = fetch_fmp(t)
        if alt and overlaps(alt, iv) and alt[0][0] < rows[0][0] and len(alt) > len(rows):
            note = f"yahoo series started {rows[0][0]}; FMP used (starts {alt[0][0]})"
            rows, info, src = alt, info, "fmp"
    if not rows:
        rows, info, src = fetch_fmp(t), {}, "fmp"
        if rows and not overlaps(rows, iv):
            note = (note + "; " if note else "") + f"fmp series {rows[0][0]}..{rows[-1][0]} outside membership"
            rows = []
    rec = {"ticker": t, "source": src if rows else None, "rows": rows, "info": info, "note": note,
           "fetched_at": datetime.now(timezone.utc).isoformat()}
    with open(path + ".tmp", "w") as f:
        json.dump(rec, f)
    os.replace(path + ".tmp", path)
    return rec, False


# ---------------------------------------------------------------- db helpers

def count(table, params=None):
    p = dict(params or {})
    p["select"] = p.get("select", "*")
    r = db._req("HEAD", f"/rest/v1/{table}", params=p, headers={"Prefer": "count=exact", "Range": "0-0"})
    return int(r.headers.get("Content-Range", "*/0").split("/")[-1])


def already_loaded(ids):
    """Security ids considered complete."""
    done = {r["security_id"] for r in db.select("prices_daily", {"select": "security_id",
                                                                 "date": f"lte.{SKIP_CUTOFF}"})}
    secs = db.select("securities", {"market": "eq.US", "select": "id,listed_date", "listed_date": "not.is.null"})
    for s in secs:
        if s["id"] in ids.values() and s["id"] not in done:
            if db.select("prices_daily", {"select": "date", "security_id": f"eq.{s['id']}",
                                          "date": f"eq.{s['listed_date']}"}):
                done.add(s["id"])
    return done


# ---------------------------------------------------------------- parquet

def export_parquet(cache_dir, tickers):
    import pyarrow as pa
    import pyarrow.parquet as pq
    by_year = {}
    for t in tickers:
        p = os.path.join(cache_dir, f"{t.replace('^', '_')}.json")
        if not os.path.exists(p):
            continue
        rec = json.load(open(p))
        for r in rec["rows"]:
            by_year.setdefault(int(r[0][:4]), []).append((t, *r, rec["source"]))
    out = []
    for y in sorted(by_year):
        rows = sorted(by_year[y], key=lambda r: (r[0], r[1]))
        cols = list(zip(*rows))
        table = pa.table({
            "symbol": pa.array(cols[0], pa.string()),
            "date": pa.array([date.fromisoformat(d) for d in cols[1]], pa.date32()),
            "open": pa.array(cols[2], pa.float64()), "high": pa.array(cols[3], pa.float64()),
            "low": pa.array(cols[4], pa.float64()), "close": pa.array(cols[5], pa.float64()),
            "adj_close": pa.array(cols[6], pa.float64()), "volume": pa.array(cols[7], pa.int64()),
            "source": pa.array(cols[8], pa.string()),
        })
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        data = buf.getvalue()
        path = f"us/sp500/prices_daily/year={y}.parquet"
        db.upload(path, data)
        rec = {"path": path, "market": "US", "kind": "prices_daily_sp500", "year": y, "rows": len(rows),
               "min_date": min(cols[1]), "max_date": max(cols[1]),
               "sha256": hashlib.sha256(data).hexdigest(), "updated_at": datetime.now(timezone.utc).isoformat()}
        db.upsert("data_files", [rec], on_conflict="path")
        out.append((path, len(rows), len(data)))
        log(f"parquet {path}: {len(rows)} rows, {len(data) / 1e6:.2f} MB")
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch and rewrite tickers already loaded")
    ap.add_argument("--limit", type=int, help="only the first N tickers (testing)")
    ap.add_argument("--tickers", help="comma list to restrict to")
    ap.add_argument("--no-parquet", action="store_true")
    ap.add_argument("--cache-dir", default=os.path.expanduser("~/.cache/seekingalpha_quant/sp500_prices"))
    args = ap.parse_args()
    os.makedirs(args.cache_dir, exist_ok=True)
    t_start = time.time()

    meta, intervals, notes = build_universe()
    for n in notes:
        log(f"universe note: {n}")
    tickers = sorted(meta)
    if args.tickers:
        tickers = [t for t in tickers if t in set(args.tickers.split(","))]
    if args.limit:
        tickers = tickers[:args.limit]
    log(f"universe: {len(meta)} tickers; processing {len(tickers)}")

    # securities: insert missing, fill name/sector where known (don't blank existing values)
    existing = {r["symbol"]: r for r in db.select("securities", {"market": "eq.US"})}
    new = [{"market": "US", "symbol": t, "name": meta[t]["name"], "sector": meta[t]["sector"]}
           for t in tickers if t not in existing]
    upd = [{"market": "US", "symbol": t, "name": meta[t]["name"] or existing[t]["name"],
            "sector": meta[t]["sector"] or existing[t]["sector"]}
           for t in tickers if t in existing and (meta[t]["name"] or meta[t]["sector"])]
    if new:
        db.upsert("securities", new, on_conflict="market,symbol")
    if upd:
        db.upsert("securities", upd, on_conflict="market,symbol")
    ids = db.security_ids("US")
    log(f"securities: {len(new)} new, {len(upd)} name/sector refreshed")

    done = set() if args.force else already_loaded(ids)

    # writer thread pool overlaps Supabase writes with fetching
    pool = ThreadPoolExecutor(max_workers=3)
    pending, write_secs, lock = [], [0.0], threading.Lock()
    buf = []

    def _write(rows):
        t0 = time.time()
        db.upsert("prices_daily", rows, on_conflict="security_id,date", batch=BATCH)
        with lock:
            write_secs[0] += time.time() - t0

    def flush(final=False):
        while len(buf) >= BATCH or (final and buf):
            chunk = buf[:BATCH]
            del buf[:BATCH]
            pending.append(pool.submit(_write, chunk))
        # surface write errors early (e.g. size limit)
        for f in [f for f in pending if f.done()]:
            f.result()
            pending.remove(f)

    stats = {"attempted": 0, "loaded": 0, "skipped": 0, "failed": {}, "rows": 0, "by_source": {},
             "fmp": [], "suspect": []}
    last_date, first_date, info_by = {}, {}, {}
    fetch_secs = 0.0
    for i, t in enumerate(tickers, 1):
        sid = ids[t]
        if sid in done:
            stats["skipped"] += 1
            continue
        stats["attempted"] += 1
        t0 = time.time()
        try:
            rec, cached = fetch(t, args.cache_dir, args.force, intervals.get(t))
        except Exception as e:  # noqa: BLE001
            stats["failed"][t] = str(e)[:200]
            log(f"{i}/{len(tickers)} {t}: FAILED {e}")
            continue
        fetch_secs += time.time() - t0
        rows = rec["rows"]
        if not rows:
            stats["failed"][t] = rec.get("note") or "no data from Yahoo or FMP"
            log(f"{i}/{len(tickers)} {t}: no data")
            if not cached:
                time.sleep(0.2)
            continue
        src = rec["source"]
        buf.extend({"security_id": sid, "date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4],
                    "adj_close": r[5], "volume": r[6], "source": src} for r in rows)
        stats["loaded"] += 1
        stats["rows"] += len(rows)
        stats["by_source"][src] = stats["by_source"].get(src, 0) + len(rows)
        if src == "fmp":
            stats["fmp"].append(t)
        first_date[t], last_date[t], info_by[t] = rows[0][0], rows[-1][0], rec.get("info") or {}
        iv = intervals.get(t) or []
        if iv:
            ms = min(s for s, _, _ in iv)
            # first data well after membership began -> ticker probably reused / renamed
            if (date.fromisoformat(rows[0][0]) - date.fromisoformat(ms)).days > 10:
                stats["suspect"].append(f"{t}: member from {ms} but data starts {rows[0][0]} ({src})")
            ends = [e for _, e, _ in iv if e]
            if all(e for _, e, _ in iv) and ends and rows[-1][0] < max(ends) and \
                    (date.fromisoformat(max(ends)) - date.fromisoformat(rows[-1][0])).days > 10:
                stats["suspect"].append(f"{t}: member until {max(ends)} but data ends {rows[-1][0]} ({src})")
        gaps = [(a[0], b[0]) for a, b in zip(rows, rows[1:])
                if (date.fromisoformat(b[0]) - date.fromisoformat(a[0])).days > 20]
        if gaps:
            stats["suspect"].append(f"{t}: gaps >20 days {gaps[:3]} ({src})")
        log(f"{i}/{len(tickers)} {t}: {len(rows)} rows {rows[0][0]}..{rows[-1][0]} {src}{' (cache)' if cached else ''}")
        flush()
        if not cached:
            time.sleep(0.2)
    flush(final=True)
    for f in pending:
        f.result()
    pool.shutdown()
    log(f"prices: fetch {fetch_secs:.0f}s, write {write_secs[0]:.0f}s (thread time, overlapped)")

    # securities metadata: listed_date (started inside window), delisted_date, exchange/currency/name
    cal = [r[0] for r in fetch("SPY", args.cache_dir, False)[0]["rows"]]  # trading calendar
    cutoff = cal[-10] if len(cal) >= 10 else None
    sec_rows, delisted = [], []
    for t in last_date:
        row = {"market": "US", "symbol": t,
               "name": meta[t]["name"] or (existing.get(t) or {}).get("name") or info_by[t].get("name"),
               "sector": meta[t]["sector"] or (existing.get(t) or {}).get("sector"),
               "exchange": info_by[t].get("exchange") or (existing.get(t) or {}).get("exchange"),
               "currency": info_by[t].get("currency") or (existing.get(t) or {}).get("currency") or "USD",
               "listed_date": first_date[t] if first_date[t] > SKIP_CUTOFF else None,
               "delisted_date": None, "updated_at": datetime.now(timezone.utc).isoformat()}
        if cutoff and last_date[t] < cutoff:
            row["delisted_date"] = last_date[t]
            delisted.append(t)
        sec_rows.append(row)
    if sec_rows:
        db.upsert("securities", sec_rows, on_conflict="market,symbol")
    log(f"securities: {len(delisted)} marked delisted (no data since {cutoff})")

    # index membership
    mem = [{"index_code": INDEX, "security_id": ids[t], "start_date": s, "end_date": e, "source": src}
           for t in tickers for s, e, src in intervals.get(t, [])]
    db.upsert("index_membership", mem, on_conflict="index_code,security_id,start_date")
    log(f"index_membership: {len(mem)} {INDEX} intervals")

    files = [] if args.no_parquet else export_parquet(args.cache_dir, tickers)

    summary = {k: v for k, v in stats.items()}
    summary.update({"delisted": delisted, "fetch_secs": round(fetch_secs), "write_secs": round(write_secs[0]),
                    "elapsed_secs": round(time.time() - t_start),
                    "parquet": {"files": len(files), "mb": round(sum(f[2] for f in files) / 1e6, 2)}})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
