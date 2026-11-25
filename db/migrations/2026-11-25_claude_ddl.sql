-- Additive-only schema changes over the REST API: public.claude_ddl(stmt).
-- Run once in the Supabase SQL Editor, AFTER 2026-11-17_data_change_log.sql. Safe to re-run.
-- The same DDL is kept in db/schema.sql.
--
-- What it allows (one statement per call, public schema only):
--   CREATE TABLE [IF NOT EXISTS] name (...)    -> RLS on, service_role grant, audit triggers attached
--   CREATE [UNIQUE] INDEX [IF NOT EXISTS] ... ON name (...)
--   CREATE VIEW name AS SELECT ...
--   ALTER TABLE [IF EXISTS] name ADD COLUMN ... | ADD CONSTRAINT ...
--   COMMENT ON TABLE | COLUMN ...
-- What it refuses: DROP, TRUNCATE, DELETE, RENAME, ALTER COLUMN, OR REPLACE, GRANT/REVOKE,
-- functions/triggers/policies/roles/extensions, other schemas, multiple statements, SQL comments.
-- Row-level DELETE through REST is not affected by this file (see the optional block at the end).

create or replace function public.claude_ddl(stmt text) returns text
language plpgsql security definer set search_path = public as $$
declare
  s     text := regexp_replace(btrim(stmt), ';\s*$', '');
  low   text;
  chk   text;
  tbl   text;
  kind  text;
  h     json := nullif(current_setting('request.headers', true), '')::json;
begin
  if s is null or s = '' then raise exception 'claude_ddl: empty statement'; end if;
  low := lower(s);

  if position(';' in low) > 0 then raise exception 'claude_ddl: one statement per call'; end if;
  if low ~ '(--|/\*)' then raise exception 'claude_ddl: SQL comments are not allowed'; end if;

  -- Foreign-key actions contain the words delete/update; strip them before the keyword check.
  chk := regexp_replace(low, 'on\s+(delete|update)\s+(cascade|restrict|set\s+null|set\s+default|no\s+action)', ' ', 'g');
  if chk ~ '\m(drop|truncate|delete|rename|grant|revoke|owner|policy|policies|execute|function|procedure|trigger|rule|extension|schema|role|password|copy|vacuum|cluster|reindex|disable|security|replace|do|call|import|attach|detach|inherit)\M'
     then raise exception 'claude_ddl: statement contains a forbidden keyword: %', s; end if;
  if chk ~ '(\mauth\.|\mstorage\.|\mvault\.|\mextensions\.|\mpg_|information_schema|supabase|realtime\.|graphql)'
     then raise exception 'claude_ddl: only the public schema may be touched'; end if;
  if (select count(*) from regexp_matches(chk, '\malter\M', 'g')) > 1
     then raise exception 'claude_ddl: ALTER COLUMN / multiple ALTER actions are not allowed'; end if;

  if low ~ '^create\s+table\s' then
    kind := 'CREATE TABLE';
    tbl := substring(low from '^create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?"?([a-z_][a-z0-9_]*)"?');
  elsif low ~ '^create\s+(unique\s+)?index\s' then
    if low ~ '\mconcurrently\M' then raise exception 'claude_ddl: CONCURRENTLY cannot run inside a function'; end if;
    kind := 'CREATE INDEX';
    tbl := substring(low from '\son\s+(?:only\s+)?(?:public\.)?"?([a-z_][a-z0-9_]*)"?');
  elsif low ~ '^create\s+view\s' then
    kind := 'CREATE VIEW';
    tbl := substring(low from '^create\s+view\s+(?:public\.)?"?([a-z_][a-z0-9_]*)"?');
  elsif low ~ '^alter\s+table\s+(if\s+exists\s+)?(only\s+)?(public\.)?"?[a-z_][a-z0-9_]*"?\s+add\s' then
    kind := 'ALTER TABLE ADD';
    tbl := substring(low from '^alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?"?([a-z_][a-z0-9_]*)"?');
  elsif low ~ '^comment\s+on\s+(table|column)\s' then
    kind := 'COMMENT';
    tbl := substring(low from '^comment\s+on\s+(?:table|column)\s+(?:public\.)?"?([a-z_][a-z0-9_]*)"?');
  else
    raise exception 'claude_ddl: only CREATE TABLE / CREATE INDEX / CREATE VIEW / ALTER TABLE ... ADD / COMMENT ON are allowed';
  end if;
  if tbl is null then raise exception 'claude_ddl: could not read the table name'; end if;

  execute s;

  if kind = 'CREATE TABLE' then
    execute format('alter table public.%I enable row level security', tbl);
    execute format('grant all on public.%I to service_role', tbl);
    execute 'grant all on all sequences in schema public to service_role';
    if to_regprocedure('public.log_data_change()') is not null then
      execute format('drop trigger if exists %I on public.%I', tbl || '_log_ins', tbl);
      execute format('drop trigger if exists %I on public.%I', tbl || '_log_upd', tbl);
      execute format('drop trigger if exists %I on public.%I', tbl || '_log_del', tbl);
      execute format('create trigger %I after insert on public.%I referencing new table as new_rows for each statement execute function log_data_change()', tbl || '_log_ins', tbl);
      execute format('create trigger %I after update on public.%I referencing new table as new_rows for each statement execute function log_data_change()', tbl || '_log_upd', tbl);
      execute format('create trigger %I after delete on public.%I referencing old table as old_rows for each statement execute function log_data_change()', tbl || '_log_del', tbl);
    end if;
  elsif kind = 'CREATE VIEW' then
    execute format('grant select on public.%I to service_role', tbl);
  end if;

  if to_regclass('public.data_change_log') is not null then
    insert into data_change_log (session_id, session_url, client, note, table_name, operation, row_count, summary)
    values (coalesce(_hdr(h, 'x-session-id'), 'rpc:' || current_user), _hdr(h, 'x-session-url'), _hdr(h, 'x-client'),
            _hdr(h, 'x-change-note'), 'public.' || tbl, 'DDL', 0, jsonb_build_object('kind', kind, 'statement', s));
  end if;

  notify pgrst, 'reload schema';   -- make the new table visible to the REST API right away
  return kind || ' public.' || tbl;
end $$;

revoke all on function public.claude_ddl(text) from public, anon, authenticated;
grant execute on function public.claude_ddl(text) to service_role;

notify pgrst, 'reload schema';

-- Optional, not run by default: also stop row deletes through the REST API.
-- (supabase_db.delete() would then fail; uncomment only if you want that.)
-- revoke delete on all tables in schema public from service_role;
