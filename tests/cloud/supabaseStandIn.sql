-- A small stand-in for the parts of Supabase our cloud scripts rely on, so they can be tested in a
-- plain local Postgres before you paste them into Supabase (plan 14c). Not a copy of Supabase: only
-- what the scripts and their tests touch. Runs once per fresh test database.

-- Supabase's API roles: anon = no sign-in (publishable key only), authenticated = signed in.
-- Roles belong to the whole server, so they're created only if an earlier test database hasn't yet.
do $$
begin
    if not exists (select from pg_roles where rolname = 'anon') then
        create role anon nologin noinherit;
        create role authenticated nologin noinherit;
        create role service_role nologin noinherit bypassrls;
    end if;
end
$$;

-- Classic Supabase projects hand every new table and function in "public" to all API roles. This
-- project doesn't (Phase 0 found that out, review F6), but the stand-in does: the riskier way round,
-- so the tests prove our scripts take away what isn't needed and grant what is, explicitly.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

-- Supabase's sign-in schema: the users table, and auth.uid(), which reads the signed-in user's id
-- from the request's token claims (the same definition Supabase uses).
create schema auth;
grant usage on schema auth to anon, authenticated, service_role;
create table auth.users (id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.sub', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
    )::uuid
$$;
grant execute on function auth.uid() to anon, authenticated, service_role;
