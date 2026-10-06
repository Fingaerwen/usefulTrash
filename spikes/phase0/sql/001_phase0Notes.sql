-- Phase 0, check 3: a throwaway test table with camelCase columns and row-level security.
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.
-- camelCase names must be "quoted" in Postgres, otherwise they are silently lowercased (plan 11.4c).

create table if not exists public."phase0Notes" (
    "id"        uuid primary key default gen_random_uuid(),           -- unique row id
    "userId"    uuid not null default auth.uid()                      -- owner = whoever is signed in
                references auth.users (id) on delete cascade,
    "noteText"  text not null,                                        -- test payload
    "updatedAt" timestamptz not null default now()                    -- edit time (sync rule G7a)
);

-- Lock the table: without a matching policy below, nobody can read or write anything.
alter table public."phase0Notes" enable row level security;

-- Signed-in users can only see and change their own rows. Anonymous visitors get nothing.
create policy "ownRowsSelect" on public."phase0Notes"
    for select to authenticated using ("userId" = auth.uid());
create policy "ownRowsInsert" on public."phase0Notes"
    for insert to authenticated with check ("userId" = auth.uid());
create policy "ownRowsUpdate" on public."phase0Notes"
    for update to authenticated using ("userId" = auth.uid()) with check ("userId" = auth.uid());
create policy "ownRowsDelete" on public."phase0Notes"
    for delete to authenticated using ("userId" = auth.uid());
