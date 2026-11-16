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

create table if not exists analysis_results (
  id          bigint generated always as identity primary key,
  analysis    text not null,                 -- e.g. event_study, holding_stats
  params      jsonb,
  result      jsonb not null,
  created_at  timestamptz not null default now()
);

-- Lock down: RLS on, no policies -> only the secret key (bypasses RLS) has access.
alter table securities            enable row level security;
alter table prices_daily          enable row level security;
alter table index_membership      enable row level security;
alter table picks                 enable row level security;
alter table alpha_picks_positions enable row level security;
alter table fundamentals          enable row level security;
alter table data_files            enable row level security;
alter table analysis_results      enable row level security;

-- Make sure the secret key's role can use the tables through the Data API.
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
