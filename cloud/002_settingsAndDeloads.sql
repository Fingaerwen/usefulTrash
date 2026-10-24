-- Upgrade 002: weights and weight steps you set in the app, and deloads you start by hand (WD2.1, WD2.4).
-- How to run (plan 14c, UP2.1): Supabase dashboard -> SQL Editor -> New query -> paste this whole
-- file (on GitHub: "Copy raw file") -> Run. Expected last line: "upgrade 002 done".
-- It runs as one transaction: if anything fails, nothing changes. It runs only right after 001.
-- Structure only: no data, no secrets. It only adds tables, so apps built for 001 keep syncing (UP1.1).

begin;

-- Run only on a cloud at upgrade 001: not twice, not out of order.
do $$
declare
    current integer;
begin
    if to_regclass('public."cloudInfo"') is null then
        raise exception 'Upgrade 001 has to be run first.';
    end if;
    select "schemaVersion" into current from public."cloudInfo" where "id" = 1;
    if current >= 2 then
        raise exception 'Upgrade 002 has already been run on this database.';
    end if;
    if current <> 1 then
        raise exception 'This database is at upgrade %, but 002 needs 001.', current;
    end if;
end
$$;


-- ── The new tables (plan 14), with the same five common columns as every synced table ────────

-- A weight you set in the app for one exercise on one day. Every change is its own row (the newest
-- on a day wins), so a later change never rewrites earlier progression.
create table public."exerciseWeights" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "exerciseId"     text not null check (length("exerciseId") between 1 and 100),
    "weekday"        integer not null check ("weekday" between 0 and 6),   -- 0 = Monday
    "weightKg"       numeric(6, 2) not null check ("weightKg" between 0 and 1000),
    "fromDate"       date not null                                          -- the first day it applies
);

-- A weight step you set in the app. Every change is its own row, like the weights above.
create table public."exerciseSteps" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "exerciseId"     text not null check (length("exerciseId") between 1 and 100),
    "incrementKg"    numeric(5, 2) not null check ("incrementKg" > 0 and "incrementKg" <= 100),
    "fromDate"       date not null                                          -- the first day it applies
);

-- A deload you started by hand: 7 days from startDate. Stopping it marks the row deleted.
create table public."deloads" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "startDate"      date not null
);


-- ── The same protection as every synced table (001: F11.1 + SY1.1, review F6) ────────────────

do $$
declare
    tableName text;
begin
    foreach tableName in array array['exerciseWeights', 'exerciseSteps', 'deloads'] loop
        execute format('create trigger "keepNewestEdit" before insert or update on public.%I '
                       'for each row execute function public."keepNewestEdit"()', tableName);

        execute format('create index on public.%I ("userId", "cloudUpdatedAt", "id")', tableName);

        execute format('revoke all on table public.%I from anon, authenticated', tableName);
        execute format('grant select, insert, update on table public.%I to authenticated', tableName);

        execute format('alter table public.%I enable row level security', tableName);
        execute format('create policy "ownRowsSelect" on public.%I for select to authenticated '
                       'using ("userId" = (select auth.uid()))', tableName);
        execute format('create policy "ownRowsInsert" on public.%I for insert to authenticated '
                       'with check ("userId" = (select auth.uid()))', tableName);
        execute format('create policy "ownRowsUpdate" on public.%I for update to authenticated '
                       'using ("userId" = (select auth.uid())) with check ("userId" = (select auth.uid()))',
                       tableName);
    end loop;
end
$$;

update public."cloudInfo" set "schemaVersion" = 2 where "id" = 1;

commit;

select 'upgrade 002 done' as "result";
