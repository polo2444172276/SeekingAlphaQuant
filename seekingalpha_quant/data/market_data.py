"""One way to read prices from the shared database, with known bad data fixed.

    from seekingalpha_quant.data import market_data as md
    px = md.get_prices(["SPY", "MTUM"], start="2015-01-01")      # long frame
    adj = md.get_adj_close(["SPY", "MTUM"], start="2015-01-01")  # wide frame

Reads `prices_daily` (REST for a few symbols, the Parquet files for many),
then applies the bad-data registry:

- `data_issues` lists every known problem. `action` says what to do:
  'override' (replace with rows from `prices_daily_overrides`),
  'exclude' (drop the raw rows in the date range) or 'flag' (keep, report).
- `prices_daily_overrides` holds the corrected rows of 'override' issues.

The raw tables are never edited; the fix lives in the registry so it can be
seen, explained and retired. Register new problems with `add_price_override`,
`add_issue` or `scripts/register_data_issue.py`. Returned frames carry
`issue_id` (the override/exclude issue that touched the row) and
`.attrs["issues"]` (every active issue for the requested symbols).
"""

import io
import sys
import warnings

import pandas as pd

from seekingalpha_quant.data import supabase_db as db

PRICE_COLS = ["open", "high", "low", "close", "adj_close", "volume", "amount", "adj_factor", "source"]
PARQUET_THRESHOLD = 50          # more symbols than this -> read the Parquet files
_missing_tables_warned = False


# ------------------------------------------------------------------ lookups

def _ids(symbols, market):
    rows = db.select("securities", {"select": "id,symbol", "market": f"eq.{market}",
                                    "symbol": f"in.({','.join(_quote(s) for s in symbols)})"})
    return {r["symbol"]: r["id"] for r in rows}


def _quote(s):
    return f'"{s}"' if any(c in s for c in ",.()^ ") else s


def _registry(security_ids):
    """(issues, override_rows) for these security ids; empty if tables don't exist yet."""
    global _missing_tables_warned
    if not security_ids:
        return pd.DataFrame(), pd.DataFrame()
    idlist = f"in.({','.join(map(str, security_ids))})"
    try:
        issues = pd.DataFrame(db.select("data_issues", {"security_id": idlist, "status": "eq.active",
                                                        "table_name": "eq.prices_daily"}))
        ovr = pd.DataFrame()
        if not issues.empty and (issues.action == "override").any():
            ovr = pd.DataFrame(db.select("prices_daily_overrides", {"security_id": idlist}))
    except RuntimeError as e:
        if "PGRST205" not in str(e):
            raise
        if not _missing_tables_warned:
            print("warning: data_issues / prices_daily_overrides not created yet; "
                  "run db/migrations/2026-11-17_data_overrides.sql. Returning raw prices.", file=sys.stderr)
            _missing_tables_warned = True
        return pd.DataFrame(), pd.DataFrame()
    return issues, ovr


# ------------------------------------------------------------------ core logic (pure, tested)

def apply_registry(raw, issues, overrides):
    """Apply issues/override rows to a raw long price frame.

    raw: columns security_id, date (Timestamp) + PRICE_COLS subset.
    issues: data_issues rows; overrides: prices_daily_overrides rows.
    Returns a new frame with an `issue_id` column (NaN where untouched).
    """
    out = raw.copy()
    out["issue_id"] = pd.NA
    if issues is None or issues.empty:
        return out
    iss = issues.copy()
    iss["date_from"] = pd.to_datetime(iss["date_from"]) if "date_from" in iss else pd.NaT
    iss["date_to"] = pd.to_datetime(iss["date_to"]) if "date_to" in iss else pd.NaT

    def in_range(df, row):
        m = df.security_id == row.security_id
        if pd.notna(row.date_from):
            m &= df.date >= row.date_from
        if pd.notna(row.date_to):
            m &= df.date <= row.date_to
        return m

    for row in iss[iss.action == "exclude"].itertuples():
        out = out[~in_range(out, row)]

    ov_issues = iss[iss.action == "override"]
    if not ov_issues.empty and overrides is not None and not overrides.empty:
        ov = overrides[overrides.issue_id.isin(ov_issues.id)].copy()
        ov["date"] = pd.to_datetime(ov["date"])
        # an override issue replaces its whole date range: raw rows without a
        # corrected counterpart in that range are dropped too, not kept as bad data
        for row in ov_issues.itertuples():
            out = out[~in_range(out, row)]
        keep = [c for c in out.columns if c in ov.columns or c == "issue_id"]
        out = pd.concat([out, ov[keep]], ignore_index=True)
    return out.sort_values(["security_id", "date"]).reset_index(drop=True)


# ------------------------------------------------------------------ readers

def _rest(ids, start, end):
    frames = []
    for sid in ids:
        p = {"select": "security_id,date," + ",".join(PRICE_COLS), "security_id": f"eq.{sid}", "order": "date.asc"}
        if start and end:
            p["and"] = f"(date.gte.{start},date.lte.{end})"
        elif start:
            p["date"] = f"gte.{start}"
        elif end:
            p["date"] = f"lte.{end}"
        frames.append(pd.DataFrame(db.select("prices_daily", p)))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _parquet(sym_to_id, start, end, kind="prices_daily_sp500"):
    import pyarrow.parquet as pq
    files = db.select("data_files", {"select": "path,year", "kind": f"eq.{kind}"})
    y0 = pd.Timestamp(start).year if start else -1
    y1 = pd.Timestamp(end).year if end else 9999
    frames = []
    for f in files:
        if y0 <= f["year"] <= y1:
            t = pq.read_table(io.BytesIO(db.download(f["path"]))).to_pandas()
            frames.append(t[t.symbol.isin(sym_to_id)])
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df.date >= pd.Timestamp(start)]
    if end:
        df = df[df.date <= pd.Timestamp(end)]
    df["security_id"] = df.symbol.map(sym_to_id)
    return df.drop(columns="symbol")


def get_prices(symbols, start=None, end=None, market="US", apply_overrides=True, via="auto"):
    """Long frame: symbol, date, OHLC, adj_close, volume, source, issue_id.

    via: 'rest', 'parquet' or 'auto' (Parquet above PARQUET_THRESHOLD symbols;
    symbols the Parquet files lack are filled from REST).
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    sym_to_id = _ids(symbols, market)
    missing = [s for s in symbols if s not in sym_to_id]
    if missing:
        warnings.warn(f"not in securities ({market}): {missing}")
    use_pq = via == "parquet" or (via == "auto" and len(sym_to_id) > PARQUET_THRESHOLD)
    raw = _parquet(sym_to_id, start, end) if use_pq else pd.DataFrame()
    have = set(raw.security_id) if not raw.empty else set()
    rest_ids = [i for i in sym_to_id.values() if i not in have]
    if rest_ids:
        raw = pd.concat([raw, _rest(rest_ids, start, end)], ignore_index=True)
    if raw.empty:
        return raw
    issues, ovr = _registry(list(sym_to_id.values()))
    if apply_overrides and not ovr.empty:
        ovr = ovr.copy()
        ovr["date"] = pd.to_datetime(ovr["date"])
        if start:
            ovr = ovr[ovr.date >= pd.Timestamp(start)]
        if end:
            ovr = ovr[ovr.date <= pd.Timestamp(end)]
    out = apply_registry(raw, issues if apply_overrides else None, ovr)
    id_to_sym = {v: k for k, v in sym_to_id.items()}
    out.insert(0, "symbol", out.pop("security_id").map(id_to_sym))
    out.attrs["issues"] = issues.to_dict("records") if not issues.empty else []
    for i in out.attrs["issues"]:
        if i["action"] == "flag":
            warnings.warn(f"data issue #{i['id']} {i.get('symbol')}: {i['description']}")
    return out


def get_adj_close(symbols, start=None, end=None, **kw):
    """Wide frame of adj_close: index date, one column per symbol."""
    px = get_prices(symbols, start, end, **kw)
    wide = px.pivot(index="date", columns="symbol", values="adj_close").sort_index()
    wide.attrs["issues"] = px.attrs.get("issues", [])
    return wide


def issues(symbols=None, status="active"):
    """data_issues rows, optionally for some symbols."""
    p = {"order": "id.asc"}
    if status:
        p["status"] = f"eq.{status}"
    if symbols:
        p["symbol"] = f"in.({','.join(_quote(s) for s in symbols)})"
    return pd.DataFrame(db.select("data_issues", p))


# ------------------------------------------------------------------ writers

def add_issue(symbol, action, description, date_from=None, date_to=None, field=None,
              evidence=None, market="US", table_name="prices_daily"):
    """Register a problem; returns the new issue id."""
    sid = _ids([symbol], market).get(symbol)
    row = {"table_name": table_name, "security_id": sid, "symbol": symbol, "action": action,
           "description": description, "date_from": date_from and str(date_from),
           "date_to": date_to and str(date_to), "field": field, "evidence": evidence,
           "created_by": db.SESSION_ID}
    with db.change_note(f"register data issue: {symbol} {action}"):
        return db.upsert("data_issues", [row], returning=True)[0]["id"]


def add_price_override(symbol, rows, description, source, evidence=None, field=None, market="US"):
    """Register an 'override' issue covering rows' date range and store the corrected rows.

    rows: iterable of dicts with date + any of PRICE_COLS (source is filled in).
    """
    rows = sorted(rows, key=lambda r: str(r["date"]))
    sid = _ids([symbol], market)[symbol]
    iid = add_issue(symbol, "override", description, rows[0]["date"], rows[-1]["date"],
                    field=field, evidence=evidence, market=market)
    out = [{**{k: v for k, v in r.items() if k in PRICE_COLS or k == "date"},
            "date": str(r["date"]), "security_id": sid, "source": source, "issue_id": iid} for r in rows]
    with db.change_note(f"override rows for issue #{iid} ({symbol})"):
        db.upsert("prices_daily_overrides", out, on_conflict="security_id,date")
    return iid
