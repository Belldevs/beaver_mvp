-- Beaver: Tasks 4-7. Run once in the Supabase SQL editor (after schema.sql and schema_task2.sql).

alter table public.profiles add column if not exists suspended boolean not null default false;

-- One row per answered question: powers History and the answer cache.
create table if not exists public.answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  question text not null,
  cache_key text not null,
  card jsonb not null,
  provider text,
  created_at timestamptz not null default now()
);
create index if not exists answers_user_idx on public.answers(user_id, created_at desc);
create index if not exists answers_cache_idx on public.answers(cache_key);

alter table public.answers enable row level security;
drop policy if exists "answers: read own" on public.answers;
create policy "answers: read own" on public.answers for select using (auth.uid() = user_id);
-- Inserts happen only in the backend (service-role key).

-- To make yourself admin (replace the email):
-- update public.profiles set is_admin = true where email = 'you@example.com';
