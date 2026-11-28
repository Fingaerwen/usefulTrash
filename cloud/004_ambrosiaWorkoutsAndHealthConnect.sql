-- Upgrade 004: Ambrosia reads Talon's workouts (apps/diet/docs/plan.md AM12.4), for the water a finished workout adds,
-- and Talon's daily steps get the calories it reads from Health Connect (plan HC1.1).
-- How to run (plan 14c, UP2.1): Supabase dashboard -> SQL Editor -> New query -> paste this whole
-- file (on GitHub: "Copy raw file") -> Run. Expected last line: "upgrade 004 done".
-- It runs as one transaction: if anything fails, nothing changes. It runs only right after 003.
-- Structure only: no data, no secrets. Ambrosia 0.2 keeps a copy of Talon's "sessions" on the phone, which needs
-- nothing new in the cloud, since row-level security already lets you read your own workouts. "dailySteps" gets
-- three columns that may be empty, so Talon 0.5 (schema 3) and Ambrosia 0.1 keep syncing (UP1.1): they fetch and
-- send only the columns they know, and an upsert without the new ones leaves them as they were.

begin;

-- Run only on a cloud at upgrade 003: not twice, not out of order.
do $$
declare
    current integer;
begin
    if to_regclass('public."cloudInfo"') is null then
        raise exception 'Upgrade 001 has to be run first.';
    end if;
    select "schemaVersion" into current from public."cloudInfo" where "id" = 1;
    if current >= 4 then
        raise exception 'Upgrade 004 has already been run on this database.';
    end if;
    if current <> 3 then
        raise exception 'This database is at upgrade %, but 004 needs 003.', current;
    end if;
end
$$;

-- ── Daily steps: what Talon reads from Health Connect (HC1.1) ──────────────────────────────────

-- Active and total (active + resting) calories burned that day, in whole kcal, and when Talon last read the day
-- from Health Connect. All three are empty for steps you typed. Health Connect's numbers replace typed steps.
alter table public."dailySteps"
    add column "activeKcal"   integer check ("activeKcal" between 0 and 20000),
    add column "totalKcal"    integer check ("totalKcal" between 0 and 30000),
    add column "healthReadAt" timestamptz;

update public."cloudInfo" set "schemaVersion" = 4 where "id" = 1;

commit;

select 'upgrade 004 done' as "result";
