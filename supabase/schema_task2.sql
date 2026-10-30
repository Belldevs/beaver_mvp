-- Beaver: Task 2. Run once in the Supabase SQL editor (after schema.sql).

-- Private bucket for the Parquet files (only the backend's service-role key can touch it).
insert into storage.buckets (id, name, public)
values ('sheets', 'sheets', false)
on conflict (id) do nothing;

-- Deleting a file must go through the backend so its Parquet files are removed too.
drop policy if exists "files: delete own" on public.files;
