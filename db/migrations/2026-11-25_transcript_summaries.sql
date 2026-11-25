-- Cached key points per earnings call (scripts/earnings_calls/summarize.py).
-- Run once in the Supabase SQL Editor.

create table if not exists transcript_summaries (
  symbol          text        not null,
  call_date       date        not null,
  prompt_version  text        not null,            -- bump when the prompt/schema changes
  model           text        not null,            -- Claude model that wrote the summary
  summary         jsonb       not null,            -- one_line, ceo_present, tone, key_points[], guidance[], analyst_focus[], topics[]
  input_tokens    int,
  output_tokens   int,
  created_at      timestamptz not null default now(),
  primary key (symbol, call_date, prompt_version, model)
);
create index if not exists transcript_summaries_date_idx   on transcript_summaries (call_date);
create index if not exists transcript_summaries_topics_idx on transcript_summaries using gin ((summary -> 'topics'));

alter table transcript_summaries enable row level security;
grant all on transcript_summaries to service_role;

-- Audit triggers, same as the other data tables (needs 2026-11-17_data_change_log.sql applied first).
do $$
begin
  if exists (select 1 from pg_proc where proname = 'log_data_change') then
    drop trigger if exists transcript_summaries_log_ins on transcript_summaries;
    drop trigger if exists transcript_summaries_log_upd on transcript_summaries;
    drop trigger if exists transcript_summaries_log_del on transcript_summaries;
    create trigger transcript_summaries_log_ins after insert on transcript_summaries
      referencing new table as new_rows for each statement execute function log_data_change();
    create trigger transcript_summaries_log_upd after update on transcript_summaries
      referencing new table as new_rows for each statement execute function log_data_change();
    create trigger transcript_summaries_log_del after delete on transcript_summaries
      referencing old table as old_rows for each statement execute function log_data_change();
  end if;
end $$;

notify pgrst, 'reload schema';
