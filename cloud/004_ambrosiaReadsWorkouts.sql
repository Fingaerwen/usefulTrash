-- Upgrade 004: Ambrosia reads Talon's workouts (apps/diet/docs/plan.md AM12.4), for the water a finished workout adds.
-- How to run (plan 14c, UP2.1): Supabase dashboard -> SQL Editor -> New query -> paste this whole
-- file (on GitHub: "Copy raw file") -> Run. Expected last line: "upgrade 004 done".
-- It runs as one transaction: if anything fails, nothing changes. It runs only right after 003.
-- Nothing in the cloud changes but the number: Ambrosia 0.2 keeps a copy of Talon's "sessions" on the phone, and
-- each app's phone steps follow the cloud's numbers (plan 14c), so its new step needs one. Row-level security
-- already lets you read your own workouts. Talon (schema 3) and Ambrosia 0.1 (schema 3) keep syncing (UP1.1).

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

update public."cloudInfo" set "schemaVersion" = 4 where "id" = 1;

commit;

select 'upgrade 004 done' as "result";
