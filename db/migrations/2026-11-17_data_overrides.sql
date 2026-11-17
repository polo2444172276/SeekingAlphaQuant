-- Bad-data registry + corrected price rows. Run in the Supabase SQL Editor
-- AFTER 2026-11-17_data_change_log.sql. Safe to re-run.
--
-- Raw tables (prices_daily, ...) keep what the loaders wrote. Known problems
-- are registered in data_issues; seekingalpha_quant.data.market_data reads
-- through them:
--   action = 'override' -> rows in prices_daily_overrides replace the raw rows
--   action = 'exclude'  -> raw rows in [date_from, date_to] are dropped
--   action = 'flag'     -> data is returned unchanged, the issue is reported
-- Retire an issue (status = 'retired') instead of deleting it.

create table if not exists data_issues (
  id           bigint generated always as identity primary key,
  table_name   text   not null default 'prices_daily',
  security_id  bigint references securities(id),
  symbol       text,                         -- denormalised for reading
  date_from    date,                         -- null = open-ended
  date_to      date,
  field        text,                         -- e.g. adj_close; null = whole row
  action       text   not null check (action in ('override', 'exclude', 'flag')),
  description  text   not null,              -- what is wrong and why
  evidence     jsonb,                        -- numbers that prove it
  status       text   not null default 'active' check (status in ('active', 'retired')),
  created_by   text,                         -- session id
  created_at   timestamptz not null default now()
);
create index if not exists data_issues_security_idx on data_issues (security_id) where status = 'active';

create table if not exists prices_daily_overrides (
  security_id bigint not null references securities(id),
  date        date   not null,
  open        double precision,
  high        double precision,
  low         double precision,
  close       double precision,
  adj_close   double precision,
  volume      bigint,
  amount      double precision,
  adj_factor  double precision,
  source      text   not null,               -- where the corrected value came from
  issue_id    bigint not null references data_issues(id) on delete cascade,
  primary key (security_id, date)
);
create index if not exists prices_daily_overrides_issue_idx on prices_daily_overrides (issue_id);

alter table data_issues            enable row level security;
alter table prices_daily_overrides enable row level security;
grant all on data_issues, prices_daily_overrides to service_role;
grant all on all sequences in schema public to service_role;

-- Audit-log triggers, if the audit log is installed.
do $$
declare t text;
begin
  if exists (select 1 from pg_proc where proname = 'log_data_change') then
    foreach t in array array['data_issues','prices_daily_overrides'] loop
      execute format('drop trigger if exists %I on %I', t || '_log_ins', t);
      execute format('drop trigger if exists %I on %I', t || '_log_upd', t);
      execute format('drop trigger if exists %I on %I', t || '_log_del', t);
      execute format('create trigger %I after insert on %I referencing new table as new_rows for each statement execute function log_data_change()', t || '_log_ins', t);
      execute format('create trigger %I after update on %I referencing new table as new_rows for each statement execute function log_data_change()', t || '_log_upd', t);
      execute format('create trigger %I after delete on %I referencing old table as old_rows for each statement execute function log_data_change()', t || '_log_del', t);
    end loop;
  end if;
end $$;
