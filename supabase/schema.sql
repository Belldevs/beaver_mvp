-- Beaver: Task 1 schema. Run this whole file once in the Supabase SQL editor.

create extension if not exists "pgcrypto";

-- ---------- profiles ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  is_admin boolean not null default false,
  questions_used integer not null default 0,
  currency text not null default 'USD',
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now()
);

-- ---------- files (one per upload or linked Google Sheet) ----------
create table if not exists public.files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  source text not null default 'upload' check (source in ('upload', 'google_sheet')),
  size_bytes bigint not null default 0,
  created_at timestamptz not null default now()
);

-- ---------- sheets (one per sheet inside a file) ----------
create table if not exists public.sheets (
  id uuid primary key default gen_random_uuid(),
  file_id uuid not null references public.files(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  storage_path text,              -- Parquet file in Supabase Storage
  row_count integer not null default 0,
  profile jsonb not null default '{}'::jsonb,  -- columns, types, mapped fields, aggregates (never raw rows)
  version integer not null default 1,
  created_at timestamptz not null default now()
);

-- ---------- usage (one row per answered question) ----------
create table if not exists public.usage (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  question text,
  provider text,                  -- gemini, backup, rules, cache
  created_at timestamptz not null default now()
);

create index if not exists files_user_idx on public.files(user_id);
create index if not exists sheets_user_idx on public.sheets(user_id);
create index if not exists usage_user_idx on public.usage(user_id, created_at);

-- ---------- row-level security ----------
alter table public.profiles enable row level security;
alter table public.files    enable row level security;
alter table public.sheets   enable row level security;
alter table public.usage    enable row level security;

create policy "profiles: read own" on public.profiles
  for select using (auth.uid() = id);

create policy "profiles: update own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

-- Users may change ONLY their currency. They can never edit is_admin or questions_used.
revoke update on public.profiles from anon, authenticated;
grant update (currency) on public.profiles to authenticated;

create policy "files: read own"   on public.files  for select using (auth.uid() = user_id);
create policy "files: delete own" on public.files  for delete using (auth.uid() = user_id);
create policy "sheets: read own"  on public.sheets for select using (auth.uid() = user_id);
create policy "usage: read own"   on public.usage  for select using (auth.uid() = user_id);

-- Inserts and counter updates on files/sheets/usage are done by the backend
-- with the service-role key, which bypasses RLS.

-- ---------- auto-create a profile on signup ----------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
