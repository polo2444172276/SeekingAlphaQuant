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
- Schema: `db/schema.sql`. Additive changes (new table, index, view, added
  column, comment) can be made from a session with `db.ddl("create table ...")`
  inside `with db.change_note("why"):` - one statement per call, public schema
  only; new tables get RLS, the service_role grant and the audit triggers.
  The database refuses DROP / TRUNCATE / RENAME / ALTER COLUMN and the like
  (`public.claude_ddl`, `db/migrations/2026-11-25_claude_ddl.sql`). Also add the
  DDL to `db/schema.sql`. Anything destructive or outside that list: write the
  SQL into a migration file and ask the user to run it in the Supabase SQL
  Editor (no management token is stored on purpose).

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
| `data_change_log` | audit trail: one row per write statement (session, script@git-ref, note, table, op, row count, key ranges) |

Parquet layout: `us/sp500/prices_daily/year=YYYY.parquet` (more markets to come).

Earnings-call transcripts (point-in-time top-100 S&P 500 by market cap, 2005-10..2026-11, speaker turns
with an `is_ceo` flag): `us/sp500_top100/earnings_calls/calls.parquet` and
`us/sp500_top100/earnings_calls/turns/year=YYYY.parquet`. Sources, gaps and rebuild steps:
`scripts/earnings_calls/README.md`. Read the per-call cache first
(`us/sp500_top100/earnings_calls/key_points/year=YYYY.parquet`: topics, forward-looking statements, numeric
targets, already-scored predictions) and open the full turns only for what the cache lacks; after new
analysis, save it to `analysis_results` and rebuild the cache (`extract_key_points.py`).

## Audit trail (who changed what, when)

- Every write through `supabase_db.py` is logged automatically in
  `data_change_log` by DB triggers (`db/migrations/2026-11-17_data_change_log.sql`).
  The client sends `x-session-id` (`session_...` for Claude cloud sessions,
  `local:user@host` elsewhere, override with `SA_SESSION_ID`), `x-session-url`
  and `x-client` (script name + git short sha) on every request.
- Wrap writes in `with db.change_note("why"):` so the log says why.
- Storage (Parquet) uploads have no trigger; `upload()` logs them itself.
- Writes from the SQL Editor show up as `sql-editor:<role>`.
- Before touching data someone else loaded, check the log:
  `select("data_change_log", {"table_name": "eq.public.prices_daily", "order": "changed_at.desc"})`.
- Don't overwrite rows from another `source` silently; insert only missing dates,
  or say so in the note.

## Conventions

- Entry prices for performance studies use the first price a reader could
  actually trade at after publication (not the pre-publication close).
- Delisted names: FMP fallback; LTHM is spliced through the 2.406 Arcadium
  merger ratio (`scripts/steve_cress_prices.py`).
- Steven Cress analysis lives in `data/steve_cress/` and `scripts/steve_cress_*.py`.
