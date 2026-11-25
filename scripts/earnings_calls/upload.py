"""Upload the built earnings-call Parquet files to bucket market-data and register them in data_files.

usage: python scripts/earnings_calls/upload.py <workdir>
  <workdir>/out/calls.parquet, <workdir>/out/turns/year=YYYY.parquet (from build.py)
"""
import glob, hashlib, os, sys
from datetime import datetime, timezone

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from seekingalpha_quant.data import supabase_db as db

W = sys.argv[1]
PREFIX = "us/sp500_top100/earnings_calls"
con = duckdb.connect()


def put(local, path, kind, year, date_col):
    data = open(local, "rb").read()
    n, lo, hi = con.execute(f"select count(*), min({date_col}), max({date_col}) from read_parquet(?)", [local]).fetchall()[0]
    db.upload(path, data)
    db.upsert("data_files", [{"path": path, "market": "US", "kind": kind, "year": year, "rows": n,
                              "min_date": lo, "max_date": hi, "sha256": hashlib.sha256(data).hexdigest(),
                              "updated_at": datetime.now(timezone.utc).isoformat()}], on_conflict="path")
    print(f"{path}: {n} rows, {len(data) / 1e6:.1f} MB", flush=True)


with db.change_note("Earnings-call transcripts, point-in-time top-100 S&P 500 by market cap, 2005-10..2026-11 "
                    "(HF zcyeee/sp500-earnings-call-turns MIT + Motley Fool pages); speaker turns with CEO flag"):
    put(f"{W}/out/calls.parquet", f"{PREFIX}/calls.parquet", "earnings_calls_top100", None, "call_date")
    for f in sorted(glob.glob(f"{W}/out/turns/year=*.parquet")):
        y = int(os.path.basename(f)[5:9])
        put(f, f"{PREFIX}/turns/year={y}.parquet", "earnings_call_turns_top100", y, "call_date")
