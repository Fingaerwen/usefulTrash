-- Phase 0, check 3: a throwaway test table with camelCase columns and row-level security.
-- Run in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run. Safe to run again (it skips or replaces what exists).
-- camelCase names must be "quoted" in Postgres, otherwise they are silently lowercased (plan 11.4c).

create table if not exists public."phase0Notes" (
    "id"        uuid primary key default gen_random_uuid(),           -- unique row id
    "userId"    uuid not null default auth.uid()                      -- owner = whoever is signed in
                references auth.users (id) on delete cascade,
    "noteText"  text not null,                                        -- test payload
    "updatedAt" timestamptz not null default now()                    -- edit time (sync rule G7a); spike only: real tables take this time from the device
);

-- Table permissions. This Supabase project does NOT hand new tables to its API roles automatically:
-- on 2026-10-07 an anonymous read got "401 permission denied for table phase0Notes" (code 42501).
-- So signed-in users get exactly the four operations they need, and anonymous visitors get nothing,
-- even before row-level security is checked (two locks instead of one). Review F6.
revoke all on table public."phase0Notes" from anon;
grant select, insert, update, delete on table public."phase0Notes" to authenticated;

-- Lock the table: without a matching policy below, nobody can read or write anything.
alter table public."phase0Notes" enable row level security;

-- Signed-in users can only see and change their own rows. Anonymous visitors get nothing.
-- "drop ... if exists" first, so running this file again replaces the policies instead of failing.
drop policy if exists "ownRowsSelect" on public."phase0Notes";
create policy "ownRowsSelect" on public."phase0Notes"
    for select to authenticated using ("userId" = auth.uid());
drop policy if exists "ownRowsInsert" on public."phase0Notes";
create policy "ownRowsInsert" on public."phase0Notes"
    for insert to authenticated with check ("userId" = auth.uid());
drop policy if exists "ownRowsUpdate" on public."phase0Notes";
create policy "ownRowsUpdate" on public."phase0Notes"
    for update to authenticated using ("userId" = auth.uid()) with check ("userId" = auth.uid());
drop policy if exists "ownRowsDelete" on public."phase0Notes";
create policy "ownRowsDelete" on public."phase0Notes"
    for delete to authenticated using ("userId" = auth.uid());
