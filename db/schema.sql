-- SeekingAlphaQuant shared database (Supabase Postgres).
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to re-run: every statement is IF NOT EXISTS / idempotent.
--
-- Design:
--   * Bulk daily history (Russell 2000 / A-shares, 20y) lives as Parquet in
--     Storage bucket `market-data`; `data_files` catalogues those files.
--   * Postgres holds reference data, picks, recent/ad-hoc prices,
--     fundamentals and analysis results.
--   * RLS is enabled with no policies: only the secret (service_role) key,
--     which bypasses RLS, can read or write. The publishable key sees nothing.

create table if not exists securities (
  id            bigint generated always as identity primary key,
  market        text not null check (market in ('US', 'CN')),
  symbol        text not null,               -- e.g. AAPL, BRK-B, 600519.SS
  exchange      text,
  name          text,
  sector        text,
  industry      text,
  currency      text,
  listed_date   date,
  delisted_date date,
  updated_at    timestamptz not null default now(),
  unique (market, symbol)
);

create table if not exists prices_daily (
  security_id bigint not null references securities(id),
  date        date   not null,
  open        double precision,
  high        double precision,
  low         double precision,
  close       double precision,
  adj_close   double precision,              -- dividend + split adjusted
  volume      bigint,
  amount      double precision,              -- turnover in currency (A-shares)
  adj_factor  double precision,              -- A-share adjustment factor
  source      text not null,                 -- yahoo / fmp / eastmoney / ...
  primary key (security_id, date)
);
create index if not exists prices_daily_date_idx on prices_daily (date);

create table if not exists index_membership (
  index_code  text   not null,               -- e.g. R2K, CSI300
  security_id bigint not null references securities(id),
  start_date  date   not null,
  end_date    date,                          -- null = still a member
  source      text,
  primary key (index_code, security_id, start_date)
);

create table if not exists picks (
  id              bigint generated always as identity primary key,
  source          text not null check (source in ('Annual Top 10', 'H2 Top 10', 'Alpha Picks')),
  list_id         text,                      -- e.g. 2024, 2024H2; null for Alpha Picks
  article_title   text,
  published_date  date not null,
  published_time  time,                      -- US/Eastern; null when unknown
  symbol          text not null,
  security_id     bigint references securities(id),
  note            text,
  unique (source, published_date, symbol)
);

create table if not exists alpha_picks_positions (
  id                  bigint generated always as identity primary key,
  symbol              text not null,
  company             text,
  picked_date         date not null,
  closed_date         date,                  -- null = still held
  reported_return_pct double precision,      -- as shown on SA at snapshot time
  sector              text,
  rating              text,
  holding_pct         double precision,
  winner              boolean not null default false,
  snapshot_date       date not null,         -- when the screenshot/page was taken
  note                text
);

create table if not exists fundamentals (
  security_id    bigint not null references securities(id),
  statement      text   not null check (statement in ('income', 'balance', 'cashflow', 'ratios', 'other')),
  period_end     date   not null,
  fiscal_period  text,                       -- e.g. 2024Q3, FY2024
  accepted_at    timestamptz not null,       -- when it became public (point-in-time)
  data           jsonb  not null,
  source         text   not null,
  primary key (security_id, statement, period_end, accepted_at)
);

create table if not exists data_files (
  path        text primary key,              -- object path inside bucket market-data
  market      text,
  kind        text,                          -- e.g. prices_daily
  year        int,
  rows        bigint,
  min_date    date,
  max_date    date,
  sha256      text,
  updated_at  timestamptz not null default now()
);

-- Cached key points per earnings call (scripts/earnings_calls/summarize.py;
-- db/migrations/2026-11-25_transcript_summaries.sql).
create table if not exists transcript_summaries (
  symbol          text        not null,
  call_date       date        not null,
  prompt_version  text        not null,
  model           text        not null,
  summary         jsonb       not null,            -- one_line, ceo_present, tone, key_points[], guidance[], analyst_focus[], topics[]
  input_tokens    int,
  output_tokens   int,
  created_at      timestamptz not null default now(),
  primary key (symbol, call_date, prompt_version, model)
);
create index if not exists transcript_summaries_date_idx   on transcript_summaries (call_date);
create index if not exists transcript_summaries_topics_idx on transcript_summaries using gin ((summary -> 'topics'));

create table if not exists analysis_results (
  id          bigint generated always as identity primary key,
  analysis    text not null,                 -- e.g. event_study, holding_stats
  params      jsonb,
  result      jsonb not null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Audit log (db/migrations/2026-11-17_data_change_log.sql): every write to the
-- tables above is recorded by a statement-level trigger, tagged with the
-- x-session-id / x-client / x-change-note headers sent by supabase_db.py.
-- ---------------------------------------------------------------------------
create table if not exists data_change_log (
  id           bigint generated always as identity primary key,
  changed_at   timestamptz not null default now(),
  session_id   text,            -- e.g. session_015Wx... (Claude cloud), local:user@host, sql-editor:postgres
  session_url  text,            -- https://claude.ai/code/session_... when known
  client       text,            -- script + git ref, e.g. scripts/load_sp500_history.py@0397891
  note         text,            -- free text: why the change was made
  table_name   text not null,   -- public.<table>, or storage:market-data for Parquet uploads
  operation    text not null,   -- INSERT / UPDATE / DELETE / UPLOAD
  row_count    bigint not null,
  summary      jsonb            -- per key column: distinct count, min, max, up to 20 sample values
);
create index if not exists data_change_log_changed_at_idx on data_change_log (changed_at desc);
create index if not exists data_change_log_table_idx      on data_change_log (table_name, changed_at desc);
create index if not exists data_change_log_session_idx    on data_change_log (session_id);
alter table data_change_log enable row level security;
grant all on data_change_log to service_role;
grant all on all sequences in schema public to service_role;

-- Header values arrive JSON-escaped (ASCII-only), so non-ASCII notes survive HTTP.
create or replace function public._hdr(h json, k text) returns text
language sql immutable as $$
  select case when h->>k is null then null
              else ('"' || (h->>k) || '"')::json #>> '{}' end
$$;

-- Statement-level trigger: one log row per write statement, not per row.
create or replace function public.log_data_change() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  h     json;
  rws   jsonb;
  n     bigint;
  k     text;
  summ  jsonb := '{}'::jsonb;
  d     bigint; lo text; hi text; smp jsonb;
  sid   text;
begin
  if TG_OP = 'DELETE' then
    select coalesce(jsonb_agg(to_jsonb(o)), '[]'::jsonb) into rws from old_rows o;
  else
    select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) into rws from new_rows x;
  end if;
  n := jsonb_array_length(rws);
  if n = 0 then return null; end if;

  foreach k in array array['id','security_id','symbol','market','date','snapshot_date',
                           'published_date','source','index_code','path','kind','year',
                           'analysis','period','statement'] loop
    select count(distinct e->>k), min(e->>k), max(e->>k)
      into d, lo, hi
      from jsonb_array_elements(rws) e where e ? k;
    if d > 0 then
      select jsonb_agg(v) into smp
        from (select distinct e->>k v from jsonb_array_elements(rws) e
              where e ? k order by 1 limit 20) s;
      summ := summ || jsonb_build_object(k, jsonb_build_object('distinct', d, 'min', lo, 'max', hi, 'sample', smp));
    end if;
  end loop;

  begin
    h := nullif(current_setting('request.headers', true), '')::json;
  exception when others then h := null;
  end;
  sid := coalesce(_hdr(h, 'x-session-id'),
                  case when h is null then 'sql-editor:' || current_user else 'unknown-api-client' end);

  insert into data_change_log (session_id, session_url, client, note, table_name, operation, row_count, summary)
  values (sid, _hdr(h, 'x-session-url'), _hdr(h, 'x-client'), _hdr(h, 'x-change-note'),
          TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP, n, summ);
  return null;
end $$;

-- Attach to every data table (transition tables need one trigger per event).
do $$
declare t text;
begin
  foreach t in array array['securities','prices_daily','index_membership','picks',
                           'alpha_picks_positions','fundamentals','data_files','analysis_results',
                           'transcript_summaries'] loop
    execute format('drop trigger if exists %I on %I', t || '_log_ins', t);
    execute format('drop trigger if exists %I on %I', t || '_log_upd', t);
    execute format('drop trigger if exists %I on %I', t || '_log_del', t);
    execute format('create trigger %I after insert on %I referencing new table as new_rows for each statement execute function log_data_change()', t || '_log_ins', t);
    execute format('create trigger %I after update on %I referencing new table as new_rows for each statement execute function log_data_change()', t || '_log_upd', t);
    execute format('create trigger %I after delete on %I referencing old table as old_rows for each statement execute function log_data_change()', t || '_log_del', t);
  end loop;
end $$;

-- Lock down: RLS on, no policies -> only the secret key (bypasses RLS) has access.
alter table securities            enable row level security;
alter table prices_daily          enable row level security;
alter table index_membership      enable row level security;
alter table picks                 enable row level security;
alter table alpha_picks_positions enable row level security;
alter table fundamentals          enable row level security;
alter table data_files            enable row level security;
alter table analysis_results      enable row level security;
alter table transcript_summaries  enable row level security;

-- Make sure the secret key's role can use the tables through the Data API.
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
