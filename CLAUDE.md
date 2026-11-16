# SeekingAlphaQuant — notes for Claude sessions

## Data first: use the shared Supabase database before the internet

All analysis and experiments should read market data from the shared
Supabase project first. Only go to the web (Yahoo, FMP, Eastmoney, web
search) for data the database does not have — and when you do fetch it,
write it back to the database so the next session has it.

Order of preference:
1. **Supabase** — one data source with two access paths; pick by query size,
   not one after the other:
   - **Postgres (REST Data API)** for small / precise reads and all writes:
     reference data, picks, a handful of tickers' prices, fundamentals,
     analysis results. Also the catalogue: `data_files` lists every Parquet
     file, and `securities` / `index_membership` say what exists.
   - **Parquet in Storage bucket `market-data` + DuckDB** for bulk history
     (whole index, many years, backtests, cross-sectional scans). Look up the
     files in `data_files`, download, query locally.
2. **Live APIs** — only when Supabase lacks the data: Yahoo chart API, FMP
   (`financialmodelingprep.com`, key is injected by the proxy),
   Eastmoney/Sina/Tencent for A-shares. Then upsert what you fetched into
   `prices_daily` / `securities` (or a Parquet file + `data_files` row for
   bulk history).
3. **Web search** — only for things no data source has (news, articles,
   corporate-action details).

## Access

- Client: `seekingalpha_quant/data/supabase_db.py`
  (`select`, `upsert`, `insert`, `delete`, `upload`, `download`, `security_ids`).
- In cloud sessions on the SeekingAlphaQuant environment the network proxy
  injects the secret key as the `apikey` header; the code sends a
  placeholder. Never print, log or commit a key. `SUPABASE_URL` is set on the
  environment. Outside the cloud, set `SUPABASE_SECRET_KEY` locally.
- Only HTTPS works from cloud sessions (no direct Postgres port / psql).
- PostgREST returns at most ~1000 rows per page; `select()` paginates. For
  more than ~100k rows, use the Parquet files instead of REST.
- Schema: `db/schema.sql`. Schema changes: write the SQL into that file and
  ask the user to run it in the Supabase SQL Editor (no management token is
  stored on purpose).

## Tables (public schema)

| table | contents |
|---|---|
| `securities` | one row per (market, symbol); market `US` or `CN`; Yahoo-style symbols (`BRK-B`) |
| `prices_daily` | daily OHLC, `adj_close` (dividend+split adjusted), volume, A-share `amount`/`adj_factor`, `source` |
| `index_membership` | index constituents over time (`SP500`, later `R2K`, ...) |
| `picks` | Steven Cress / SA Quant picks: `Annual Top 10`, `H2 Top 10`, `Alpha Picks` |
| `alpha_picks_positions` | Alpha Picks current + closed rows as shown on SA, per `snapshot_date` |
| `fundamentals` | statements as JSONB with `accepted_at` for point-in-time use |
| `data_files` | Parquet files in bucket `market-data` (path, market, kind, year, rows, dates, sha256) |
| `analysis_results` | saved analysis outputs (JSON) |

Parquet layout: `us/sp500/prices_daily/year=YYYY.parquet` (more markets to come).

## Conventions

- Entry prices for performance studies use the first price a reader could
  actually trade at after publication (not the pre-publication close).
- Delisted names: FMP fallback; LTHM is spliced through the 2.406 Arcadium
  merger ratio (`scripts/steve_cress_prices.py`).
- Steven Cress analysis lives in `data/steve_cress/` and `scripts/steve_cress_*.py`.
