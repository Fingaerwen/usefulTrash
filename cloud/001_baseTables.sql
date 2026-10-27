-- Upgrade 001: the real tables (plan 14), the rules every table follows, and the daily ping.
-- How to run (plan 14c, UP2.1): Supabase dashboard -> SQL Editor -> New query -> paste this whole
-- file (on GitHub: "Copy raw file") -> Run. Expected last line: "upgrade 001 done".
-- It runs as one transaction: if anything fails, nothing changes. Running it a second time is refused.
-- Structure only: no data, no secrets. camelCase names are "quoted", or Postgres lowercases them (11.4c).

begin;

-- Refuse to run twice: this upgrade creates "cloudInfo", so if that exists, 001 has already run.
do $$
begin
    if to_regclass('public."cloudInfo"') is not null then
        raise exception 'Upgrade 001 has already been run on this database.';
    end if;
end
$$;

-- The Phase 0 test table isn't needed any more (plan 14c).
drop table if exists public."phase0Notes";


-- ── Cloud version (plan 14b/14c, UP1.1) ───────────────────────────────────────────────────────

-- One row: which upgrade the cloud is at, and the oldest app schema still allowed to sync.
-- An app syncs only if minAppSchema <= its own schema number <= schemaVersion.
create table public."cloudInfo" (
    "id"            smallint primary key check ("id" = 1),  -- there's only ever this one row
    "schemaVersion" integer not null,                        -- the last upgrade run here
    "minAppSchema"  integer not null                         -- raised only for a breaking change
);
insert into public."cloudInfo" ("id", "schemaVersion", "minAppSchema") values (1, 1, 1);


-- ── The tables (plan 14) ─────────────────────────────────────────────────────────────────────
-- Every synced table starts with the same five columns:
--   id             the row's id, made on the device (for one-per-day rows, worked out from the date)
--   userId         whose row it is. Row-level security below only lets you reach your own
--   updatedAt      when the edit was made, from the device's clock. The newest edit wins (F11.1)
--   deleted        rows are never really removed: deleting is an edit like any other
--   cloudUpdatedAt stamped by the cloud when it stores a change. Used only to fetch what's new (SY1.1)
-- The database enforces no links between tables, because offline changes can arrive in any order.

-- Plan imports: the plan as imported, when it takes effect and the starting step you chose.
create table public."plans" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "importedAt"     timestamptz not null,                     -- orders imports taking effect the same day
    "effectiveDate"  date not null,                            -- the first day the plan applies
    "startStep"      integer not null check ("startStep" >= 0),
    "planJson"       jsonb not null check (jsonb_typeof("planJson") = 'object'),
    "archived"       boolean not null default false
);

-- Workouts: one per day (DT1.1), each recording which plan step it was.
create table public."sessions" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "date"           date not null,
    "planImportId"   uuid not null,                            -- the plan import this workout belongs to
    "stepIndex"      integer not null check ("stepIndex" >= 0),
    "finishedAt"     timestamptz,                              -- empty until you tap Finish
    unique ("userId", "date")
);

-- One exercise on one workout day: what was suggested and what you did.
create table public."exerciseLogs" (
    "id"                 uuid primary key,
    "userId"             uuid not null references auth.users (id) on delete cascade,
    "updatedAt"          timestamptz not null,
    "deleted"            boolean not null default false,
    "cloudUpdatedAt"     timestamptz not null default clock_timestamp(),
    "date"               date not null,
    "exerciseId"         text not null check (length("exerciseId") between 1 and 100),
    "targetReps"         integer check ("targetReps" >= 0),           -- what Today suggested
    "targetWeightKg"     numeric(6, 2) check ("targetWeightKg" >= 0),
    "sets"               jsonb not null default '[]' check (jsonb_typeof("sets") = 'array'),  -- reps + kg per set
    "minutes"            integer check ("minutes" >= 0),               -- cardio
    "skipped"            boolean not null default false,
    "declinedSuggestion" boolean not null default false,               -- you pressed Undo on ↑new
    unique ("userId", "date", "exerciseId")
);

-- Body weight: one per day (DT2.1). Shared with the diet app later.
create table public."bodyWeight" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "date"           date not null,
    "weightKg"       numeric(5, 2) not null check ("weightKg" > 0 and "weightKg" < 1000),
    unique ("userId", "date")
);

-- Daily step totals: one per day (CA1.1). Shared with the diet app later.
create table public."dailySteps" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "date"           date not null,
    "steps"          integer not null check ("steps" between 0 and 200000),
    unique ("userId", "date")
);

-- Backups made to Google Drive, so every device knows when the last one was (plan 12).
create table public."backups" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "madeAt"         timestamptz not null,
    "fileName"       text not null,
    "driveFileId"    text,
    "sizeBytes"      bigint check ("sizeBytes" >= 0),
    "schemaVersion"  integer not null,
    "madeBy"         text not null check ("madeBy" in ('phone', 'pcView'))
);


-- ── The rule every synced table follows (plan 14: F11.1 + SY1.1) ─────────────────────────────

create function public."keepNewestEdit"() returns trigger
language plpgsql set search_path = '' as $$
begin
    -- A device whose clock runs far ahead would win every conflict, so its change is refused.
    if new."updatedAt" > now() + interval '5 minutes' then
        raise exception 'futureEdit: this change is stamped % but the cloud''s time is %; check the device''s clock.',
            new."updatedAt", now();
    end if;
    if tg_op = 'UPDATE' then
        if new."id" <> old."id" then
            raise exception 'idChange: a row''s id never changes.';
        end if;
        -- Only a newer edit replaces the stored one. An older or equal one is quietly ignored.
        if new."updatedAt" <= old."updatedAt" then
            return null;
        end if;
    end if;
    new."cloudUpdatedAt" := clock_timestamp();  -- the cloud's own stamp, whatever the device sent
    return new;
end
$$;
-- Only the triggers below use it. Nobody may call it directly.
revoke all on function public."keepNewestEdit"() from public, anon, authenticated;

-- The same protection for every synced table, applied in one loop so none can be forgotten.
do $$
declare
    tableName text;
begin
    foreach tableName in array array['plans', 'sessions', 'exerciseLogs', 'bodyWeight', 'dailySteps', 'backups'] loop
        execute format('create trigger "keepNewestEdit" before insert or update on public.%I '
                       'for each row execute function public."keepNewestEdit"()', tableName);

        -- Fetching asks for "changed since", newest last, per user (plan 14b).
        execute format('create index on public.%I ("userId", "cloudUpdatedAt", "id")', tableName);

        -- Two locks (review F6): table permissions first, then row-level security.
        -- Anonymous visitors get nothing. Signed-in users may read, add and change, but never remove.
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

-- cloudInfo: signed-in apps can read it. Only upgrade scripts change it.
revoke all on table public."cloudInfo" from anon, authenticated;
grant select on table public."cloudInfo" to authenticated;
alter table public."cloudInfo" enable row level security;
create policy "signedInReads" on public."cloudInfo" for select to authenticated using (true);


-- ── Daily ping (plan 12, K1c) ────────────────────────────────────────────────────────────────

-- Called once a day by the GitHub workflow with only the publishable key, so the free project
-- doesn't pause. It reads nothing and changes nothing.
create function public."ping"() returns text
language sql stable set search_path = '' as $$
    select 'ok'
$$;
revoke all on function public."ping"() from public, anon, authenticated;
grant execute on function public."ping"() to anon, authenticated;

commit;

select 'upgrade 001 done' as "result";
