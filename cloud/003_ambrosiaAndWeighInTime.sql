-- Upgrade 003: Ambrosia's tables (apps/diet/docs/plan.md 4e, AM6.4) and the time of today's weigh-in (AM6.3).
-- How to run (plan 14c, UP2.1): Supabase dashboard -> SQL Editor -> New query -> paste this whole
-- file (on GitHub: "Copy raw file") -> Run. Expected last line: "upgrade 003 done".
-- It runs as one transaction: if anything fails, nothing changes. It runs only right after 002.
-- Structure only: no data, no secrets. It only adds tables and one column that may be empty, so apps built for
-- 001 and 002 keep syncing (UP1.1): they fetch and send only the columns they know, and an upsert without
-- "weighedAt" leaves it as it was.

begin;

-- Run only on a cloud at upgrade 002: not twice, not out of order.
do $$
declare
    current integer;
begin
    if to_regclass('public."cloudInfo"') is null then
        raise exception 'Upgrade 001 has to be run first.';
    end if;
    select "schemaVersion" into current from public."cloudInfo" where "id" = 1;
    if current >= 3 then
        raise exception 'Upgrade 003 has already been run on this database.';
    end if;
    if current <> 2 then
        raise exception 'This database is at upgrade %, but 003 needs 002.', current;
    end if;
end
$$;


-- ── Body weight: when you saved today's weigh-in (AM6.3) ─────────────────────────────────────

-- Talon 0.4 stamps it when you save today's weigh-in. A past day's weigh-in, and every one from before
-- Talon 0.4, has none.
alter table public."bodyWeight" add column "weighedAt" timestamptz;


-- ── Ambrosia's tables (its plan's 4e), with the same five common columns as every synced table ──

-- A food you've used. Its id comes from its barcode or its USDA number. Values are per 100 g, or per 100 ml
-- for a drink.
create table public."foods" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "source"         text not null check ("source" in ('openFoodFacts', 'usda', 'label')),
    "barcode"        text check ("barcode" ~ '^[0-9]{1,20}$'),
    "usdaId"         integer check ("usdaId" > 0),
    "name"           text not null check (length("name") between 1 and 200),
    "brand"          text check (length("brand") <= 200),
    "unit"           text not null check ("unit" in ('g', 'ml')),
    "kcal"           numeric(4, 1) not null check ("kcal" between 0 and 950),
    "proteinG"       numeric(5, 2) not null check ("proteinG" between 0 and 100),
    "fatG"           numeric(5, 2) not null check ("fatG" between 0 and 100),
    "carbsG"         numeric(5, 2) not null check ("carbsG" between 0 and 100),
    "servingG"       numeric(6, 1) check ("servingG" > 0 and "servingG" <= 10000),
    "packG"          numeric(6, 1) check ("packG" > 0 and "packG" <= 10000)
);

-- Something you ate, with copies of the food's name and values at the time.
create table public."foodLogs" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "date"           date not null,
    "meal"           text not null check ("meal" in ('breakfast', 'lunch', 'dinner', 'snacks')),
    "loggedAt"       timestamptz not null,                     -- its place in the meal
    "foodId"         uuid not null,
    "portion"        text not null check ("portion" in ('grams', 'servings', 'pack')),
    "portionCount"   numeric(8, 2) check ("portionCount" > 0),  -- empty for grams
    "grams"          numeric(6, 1) not null check ("grams" > 0 and "grams" <= 10000),
    "name"           text not null check (length("name") between 1 and 200),
    "brand"          text check (length("brand") <= 200),
    "unit"           text not null check ("unit" in ('g', 'ml')),
    "kcal"           numeric(4, 1) not null check ("kcal" between 0 and 950),
    "proteinG"       numeric(5, 2) not null check ("proteinG" between 0 and 100),
    "fatG"           numeric(5, 2) not null check ("fatG" between 0 and 100),
    "carbsG"         numeric(5, 2) not null check ("carbsG" between 0 and 100)
);

-- A day's water: one per day, its total.
create table public."water" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "date"           date not null,
    "ml"             integer not null check ("ml" between 0 and 20000),
    unique ("userId", "date")
);

-- A targets file as imported. It applies from the day you import it.
create table public."dietTargets" (
    "id"             uuid primary key,
    "userId"         uuid not null references auth.users (id) on delete cascade,
    "updatedAt"      timestamptz not null,
    "deleted"        boolean not null default false,
    "cloudUpdatedAt" timestamptz not null default clock_timestamp(),
    "importedAt"     timestamptz not null,                     -- orders imports on the same day
    "effectiveDate"  date not null,
    "targetsJson"    jsonb not null check (jsonb_typeof("targetsJson") = 'object')
);

-- A bulk-check change you applied: one per check (its Sunday), with the check's numbers. Undoing it marks it
-- deleted.
create table public."targetChanges" (
    "id"               uuid primary key,
    "userId"           uuid not null references auth.users (id) on delete cascade,
    "updatedAt"        timestamptz not null,
    "deleted"          boolean not null default false,
    "cloudUpdatedAt"   timestamptz not null default clock_timestamp(),
    "checkDate"        date not null,
    "fromDate"         date not null,                         -- the day you applied it
    "targetsImportId"  uuid not null,
    "reason"           text not null check ("reason" in ('rate', 'bigMissLow', 'bigMissHigh')),
    "kcalChange"       integer not null check ("kcalChange" between -1000 and 1000 and "kcalChange" <> 0),
    "macro"            text not null check ("macro" in ('carbs', 'fat')),
    "macroChangeG"     integer not null check ("macroChangeG" between -250 and 250),
    "blockAvgKg"       numeric(5, 2) not null check ("blockAvgKg" > 0),
    "blockWeighIns"    integer not null check ("blockWeighIns" between 1 and 14),
    "comparedStart"    date not null,                         -- the Monday of the block it was compared with
    "comparedAvgKg"    numeric(5, 2) not null check ("comparedAvgKg" > 0),
    "comparedWeighIns" integer not null check ("comparedWeighIns" between 1 and 14),
    "rateKgPerWeek"    numeric(5, 2),                         -- empty for a big miss
    unique ("userId", "checkDate")
);

-- Ambrosia's backups to Google Drive (AM5.6): like backups, in a table of its own, because Talon decides its
-- backup is due from the newest row in backups.
create table public."dietBackups" (
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


-- ── The same protection as every synced table (001: F11.1 + SY1.1, review F6) ────────────────

do $$
declare
    tableName text;
begin
    foreach tableName in array array['foods', 'foodLogs', 'water', 'dietTargets', 'targetChanges', 'dietBackups'] loop
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

update public."cloudInfo" set "schemaVersion" = 3 where "id" = 1;

commit;

select 'upgrade 003 done' as "result";
