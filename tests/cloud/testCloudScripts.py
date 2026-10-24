"""Tests for the cloud upgrade scripts in cloud/ (plan 14c), run in a throwaway local Postgres.

Each test gets a fresh database with the Supabase stand-in (supabaseStandIn.sql) and the scripts.
The container has no network at all and no password: it's reached only through `podman exec`.
Skipped when podman isn't installed.
"""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from gym.tables import appSchema, appTables

repoRoot = Path(__file__).resolve().parents[2]
cloudScripts = sorted((repoRoot / "cloud").glob("[0-9][0-9][0-9]_*.sql"))
standInSql = (Path(__file__).parent / "supabaseStandIn.sql").read_text(encoding="utf-8")

# Official Postgres 17 image, pinned by digest so every run uses exactly the same build (17.11).
# Supabase runs Postgres 17 for new projects; the plan's release checklist compares the major version.
postgresImage = (
    "docker.io/library/postgres@sha256:aa90e97ee862e558111d34cfb8b2c4bec768c2b039fb791341686928560263b3"
)

syncedTables = ["plans", "sessions", "exerciseLogs", "bodyWeight", "dailySteps", "backups", "exerciseWeights",
                "exerciseSteps", "deloads"]
userA = str(uuid.UUID(int=1))
userB = str(uuid.UUID(int=2))

pytestmark = pytest.mark.skipif(shutil.which("podman") is None, reason="podman isn't installed")


# --- Container and database helpers -------------------------------------------------------------

@pytest.fixture(scope="session")
def container():
    """Starts one Postgres container for the whole test run and removes it afterwards."""
    name = f"usefulTrashCloudTest{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["podman", "run", "--detach", "--rm", "--name", name, "--network", "none",
         "--env", "POSTGRES_HOST_AUTH_METHOD=trust", postgresImage],
        check=True, capture_output=True, timeout=120,
    )
    try:
        _waitUntilReady(name)
        yield name
    finally:
        subprocess.run(["podman", "rm", "--force", name], capture_output=True, timeout=60)


def _waitUntilReady(name: str) -> None:
    """Waits for the image's first-start setup to finish and the real server to accept queries."""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        logs = subprocess.run(["podman", "logs", name], capture_output=True, text=True)
        if "PostgreSQL init process complete" in logs.stdout + logs.stderr:
            probe = subprocess.run(["podman", "exec", name, "psql", "-U", "postgres", "-Atc", "select 1"],
                                   capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "1":
                return
        time.sleep(0.5)
    raise TimeoutError("the test Postgres didn't start within 90 s")


class Database:
    """One fresh test database in the container."""

    def __init__(self, container: str, name: str):
        self.container = container
        self.name = name

    def run(self, sql: str, *, asUser: str | None = None, anonymous: bool = False) -> subprocess.CompletedProcess:
        """Runs SQL as the admin (like Supabase's SQL editor), as a signed-in user, or anonymously.

        Stops at the first error. Returns psql's result: output in unaligned rows, errors in stderr.
        """
        if asUser is not None:
            claims = json.dumps({"sub": asUser, "role": "authenticated"})
            sql = f"set role authenticated; select set_config('request.jwt.claims', '{claims}', false) \\g /dev/null\n{sql}"
        elif anonymous:
            sql = f"set role anon;\n{sql}"
        return subprocess.run(
            ["podman", "exec", "-i", self.container, "psql", "-U", "postgres", "-d", self.name,
             "-v", "ON_ERROR_STOP=1", "-X", "-q", "-At"],
            input=sql, capture_output=True, text=True, timeout=60,
        )

    def ok(self, sql: str, **who) -> list[str]:
        """Runs SQL that must succeed; returns the output rows."""
        result = self.run(sql, **who)
        assert result.returncode == 0, result.stderr
        return [line for line in result.stdout.splitlines() if line]

    def fails(self, sql: str, expectedError: str, **who) -> None:
        """Runs SQL that must fail with an error containing expectedError."""
        result = self.run(sql, **who)
        assert result.returncode != 0, f"expected an error, got: {result.stdout}"
        assert expectedError in result.stderr, result.stderr


@pytest.fixture
def emptyDatabase(container) -> Database:
    """A fresh database with only the Supabase stand-in and two users, A and B."""
    name = f"test{uuid.uuid4().hex[:12]}"
    subprocess.run(["podman", "exec", container, "createdb", "-U", "postgres", "-T", "template0", name],
                   check=True, capture_output=True, timeout=60)
    database = Database(container, name)
    database.ok(standInSql)
    database.ok(f"insert into auth.users (id) values ('{userA}'), ('{userB}');")
    return database


@pytest.fixture
def database(emptyDatabase) -> Database:
    """A fresh database with every cloud script run on it, in order."""
    for script in cloudScripts:
        emptyDatabase.ok(script.read_text(encoding="utf-8"))
    return emptyDatabase


def newRow(table: str, userId: str = userA, updatedAt: str = "now()", **columns) -> str:
    """An INSERT for a valid row in `table`; keyword arguments override columns (as SQL text)."""
    defaults = {
        "plans": {"importedAt": "now()", "effectiveDate": "'2026-10-12'", "startStep": "0",
                  "planJson": "'{\"name\": \"Push Pull Legs\"}'"},
        "sessions": {"date": "'2026-10-12'", "planImportId": f"'{uuid.uuid4()}'", "stepIndex": "0"},
        "exerciseLogs": {"date": "'2026-10-12'", "exerciseId": "'benchPress'"},
        "bodyWeight": {"date": "'2026-10-12'", "weightKg": "81.2"},
        "dailySteps": {"date": "'2026-10-12'", "steps": "14000"},
        "backups": {"madeAt": "now()", "fileName": "'backup.zip'", "schemaVersion": "1", "madeBy": "'phone'"},
        "exerciseWeights": {"exerciseId": "'benchPress'", "weekday": "0", "weightKg": "82.5",
                            "fromDate": "'2026-10-12'"},
        "exerciseSteps": {"exerciseId": "'benchPress'", "incrementKg": "2.5", "fromDate": "'2026-10-12'"},
        "deloads": {"startDate": "'2026-10-19'"},
    }[table]
    values = {"id": f"'{uuid.uuid4()}'", "userId": f"'{userId}'", "updatedAt": updatedAt, **defaults, **columns}
    names = ", ".join(f'"{name}"' for name in values)
    return f'insert into public."{table}" ({names}) values ({", ".join(values.values())});'


# --- Running the scripts ------------------------------------------------------------------------

def testScriptsAreNumberedWithoutGaps():
    numbers = [int(script.name[:3]) for script in cloudScripts]
    assert numbers == list(range(1, len(numbers) + 1))


def testScriptsRunOnAFreshDatabase(emptyDatabase):
    for script in cloudScripts:
        output = emptyDatabase.ok(script.read_text(encoding="utf-8"))
        assert output[-1] == f"upgrade {script.name[:3]} done"
    latest = len(cloudScripts)
    assert emptyDatabase.ok('select "id", "schemaVersion", "minAppSchema" from public."cloudInfo";') == [
        f"1|{latest}|1"]


def testRunningAnUpgradeTwiceIsRefused(database):
    database.fails(cloudScripts[0].read_text(encoding="utf-8"), "has already been run")
    assert database.ok('select count(*) from public."cloudInfo";') == ["1"]
    database.fails(cloudScripts[1].read_text(encoding="utf-8"), "has already been run")


def testUpgrade002NeedsUpgrade001First(emptyDatabase):
    emptyDatabase.fails(cloudScripts[1].read_text(encoding="utf-8"), "Upgrade 001 has to be run first")


def testUpgrade002LetsAppsBuiltFor001KeepSyncing(database):
    """It only adds tables (UP1.1), so minAppSchema stays 1."""
    assert database.ok('select "schemaVersion", "minAppSchema" from public."cloudInfo";') == ["2|1"]


def testAFailedUpgradeChangesNothing(emptyDatabase):
    """Something in the way halfway through: the whole upgrade is rolled back, even the drop."""
    emptyDatabase.ok('create table public."phase0Notes" ("id" uuid); create table public."sessions" ("id" uuid);')
    emptyDatabase.fails(cloudScripts[0].read_text(encoding="utf-8"), 'relation "sessions" already exists')
    assert emptyDatabase.ok("""select to_regclass('public."cloudInfo"') is null,
                                      to_regclass('public."phase0Notes"') is not null;""") == ["t|t"]


def testPhase0TableIsRemoved(emptyDatabase):
    emptyDatabase.ok('create table public."phase0Notes" ("id" uuid);')
    emptyDatabase.ok(cloudScripts[0].read_text(encoding="utf-8"))
    assert emptyDatabase.ok("""select to_regclass('public."phase0Notes"') is null;""") == ["t"]


# --- Who can do what ------------------------------------------------------------------------------

@pytest.mark.parametrize("table", syncedTables + ["cloudInfo"])
def testAnonymousVisitorsGetNothing(database, table):
    database.fails(f'select * from public."{table}";', "permission denied", anonymous=True)


def testAnonymousVisitorsCanOnlyPing(database):
    assert database.ok("select public.ping();", anonymous=True) == ["ok"]
    database.fails('select public."keepNewestEdit"();', "permission denied", anonymous=True)


@pytest.mark.parametrize("table", syncedTables)
def testSignedInUsersReachOnlyTheirOwnRows(database, table):
    database.ok(newRow(table, userId=userA), asUser=userA)
    assert database.ok(f'select count(*) from public."{table}";', asUser=userA) == ["1"]
    assert database.ok(f'select count(*) from public."{table}";', asUser=userB) == ["0"]
    database.ok(f'update public."{table}" set "updatedAt" = now(), "deleted" = true;', asUser=userB)
    assert database.ok(f'select count(*) from public."{table}" where "deleted";') == ["0"]


@pytest.mark.parametrize("table", syncedTables)
def testNobodyCanWriteRowsForSomeoneElse(database, table):
    database.fails(newRow(table, userId=userB), "row-level security", asUser=userA)
    database.ok(newRow(table, userId=userA), asUser=userA)
    database.fails(f'update public."{table}" set "userId" = \'{userB}\', "updatedAt" = now() + interval \'1 second\';',
                   "row-level security", asUser=userA)


@pytest.mark.parametrize("table", syncedTables)
def testRowsCanNeverBeRemoved(database, table):
    database.ok(newRow(table, userId=userA), asUser=userA)
    database.fails(f'delete from public."{table}";', "permission denied", asUser=userA)


def testSignedInAppsCanReadTheCloudVersionButNotChangeIt(database):
    assert database.ok('select "schemaVersion" from public."cloudInfo";', asUser=userA) == [str(len(cloudScripts))]
    database.fails('update public."cloudInfo" set "minAppSchema" = 99;', "permission denied", asUser=userA)


# --- The newest edit wins (F11.1 + SY1.1) ---------------------------------------------------------

def upsertWeight(rowId: str, updatedAt: str, weightKg: str) -> str:
    """The same "insert, or update if it exists" that sync sends (PostgREST's merge-duplicates)."""
    return (f'insert into public."bodyWeight" ("id", "userId", "updatedAt", "date", "weightKg") '
            f"values ('{rowId}', '{userA}', {updatedAt}, '2026-10-12', {weightKg}) "
            f'on conflict ("id") do update set "updatedAt" = excluded."updatedAt", "weightKg" = excluded."weightKg";')


def storedWeight(database: Database, rowId: str) -> str:
    return database.ok(f'select "weightKg" from public."bodyWeight" where "id" = \'{rowId}\';')[0]


def testOnlyANewerEditReplacesTheStoredOne(database):
    # Fixed times: each call is its own session, so now() would differ between calls.
    rowId = str(uuid.uuid4())
    database.ok(upsertWeight(rowId, "'2026-10-12 08:00:00+00'", "81.20"), asUser=userA)
    database.ok(upsertWeight(rowId, "'2026-10-12 07:00:00+00'", "90.00"), asUser=userA)  # older: ignored
    assert storedWeight(database, rowId) == "81.20"
    database.ok(upsertWeight(rowId, "'2026-10-12 08:00:00+00'", "90.00"), asUser=userA)  # same time: ignored
    assert storedWeight(database, rowId) == "81.20"
    database.ok(upsertWeight(rowId, "'2026-10-12 09:00:00+00'", "80.90"), asUser=userA)  # newer: wins
    assert storedWeight(database, rowId) == "80.90"


def testAChangeFromAClockFarAheadIsRefused(database):
    database.fails(upsertWeight(str(uuid.uuid4()), "now() + interval '6 minutes'", "81.2"), "futureEdit",
                   asUser=userA)
    database.ok(upsertWeight(str(uuid.uuid4()), "now() + interval '4 minutes'", "81.2"), asUser=userA)


def testTheCloudStampsCloudUpdatedAtItself(database):
    rowId = str(uuid.uuid4())
    database.ok(newRow("bodyWeight", id=f"'{rowId}'", cloudUpdatedAt="'2000-01-01'"), asUser=userA)
    stamp = f'select "cloudUpdatedAt" from public."bodyWeight" where "id" = \'{rowId}\';'
    first = database.ok(stamp)[0]
    assert first > "2026"
    database.ok(upsertWeight(rowId, "now() - interval '1 day'", "70"), asUser=userA)  # older: ignored
    assert database.ok(stamp)[0] == first
    database.ok(upsertWeight(rowId, "now() + interval '1 second'", "70"), asUser=userA)  # newer: re-stamped
    assert database.ok(stamp)[0] > first


def testARowsIdNeverChanges(database):
    rowId = str(uuid.uuid4())
    database.ok(newRow("bodyWeight", id=f"'{rowId}'"), asUser=userA)
    database.fails(f'update public."bodyWeight" set "id" = \'{uuid.uuid4()}\', "updatedAt" = now() + interval \'1 second\';',
                   "idChange", asUser=userA)


@pytest.mark.parametrize(("table", "sameDayColumns"), [
    ("sessions", {}),
    ("exerciseLogs", {"exerciseId": "'benchPress'"}),
    ("bodyWeight", {}),
    ("dailySteps", {}),
])
def testOneRowPerDay(database, table, sameDayColumns):
    """DT1.1 / DT2.1 / CA1.1: a second row for the same day (with a different id) is refused."""
    database.ok(newRow(table, **sameDayColumns), asUser=userA)
    database.fails(newRow(table, **sameDayColumns), "duplicate key", asUser=userA)
    database.ok(newRow(table, userId=userB, **sameDayColumns), asUser=userB)  # another user's same day is fine


@pytest.mark.parametrize("table", ["exerciseWeights", "exerciseSteps"])
def testEveryChangeSetInTheAppIsItsOwnRow(database, table):
    """WD2.1: setting a weight or a step again adds a row, so the earlier change is kept."""
    database.ok(newRow(table), asUser=userA)
    database.ok(newRow(table), asUser=userA)


def testTwoExercisesOnTheSameDayAreFine(database):
    database.ok(newRow("exerciseLogs", exerciseId="'benchPress'"), asUser=userA)
    database.ok(newRow("exerciseLogs", exerciseId="'dips'"), asUser=userA)


# --- Every table has the same protection (so none was forgotten) -------------------------------

@pytest.mark.parametrize("table", syncedTables)
def testEverySyncedTableIsFullyProtected(database, table):
    rows = database.ok(f"""
        select c.relrowsecurity,
               exists (select from pg_trigger t where t.tgrelid = c.oid and t.tgname = 'keepNewestEdit'),
               (select string_agg(p.polcmd::text, '' order by p.polcmd::text) from pg_policy p where p.polrelid = c.oid),
               has_table_privilege('anon', c.oid, 'select, insert, update, delete, truncate, references, trigger'),
               has_table_privilege('authenticated', c.oid, 'delete, truncate, references, trigger'),
               has_table_privilege('authenticated', c.oid, 'select'),
               has_table_privilege('authenticated', c.oid, 'insert'),
               has_table_privilege('authenticated', c.oid, 'update')
        from pg_class c where c.oid = 'public."{table}"'::regclass;""")
    # RLS on, trigger present, policies for select (r), insert (a) and update (w) only, anon nothing,
    # signed-in users no delete/truncate/references/trigger, but select, insert and update.
    assert rows == ["t|t|arw|f|f|t|t|t"]


@pytest.mark.parametrize("table", syncedTables)
def testEverySyncedTableHasTheCommonColumns(database, table):
    rows = database.ok(f"""
        select string_agg(column_name || ':' || data_type, ',' order by ordinal_position)
        from information_schema.columns
        where table_schema = 'public' and table_name = '{table}' and ordinal_position <= 5;""")
    assert rows == ["id:uuid,userId:uuid,updatedAt:timestamp with time zone,deleted:boolean,"
                    "cloudUpdatedAt:timestamp with time zone"]


# --- The apps' table definitions match the cloud (plan 14) --------------------------------------

@pytest.mark.parametrize("table", appTables, ids=lambda table: table.name)
def testAppTablesMatchTheCloud(database, table):
    """gym/tables.py and usefulShared/tables.py list every column with the cloud's own type, in order."""
    rows = database.ok(f"""
        select a.attname || '|' || format_type(a.atttypid, a.atttypmod) || '|' || a.attnotnull
        from pg_attribute a
        where a.attrelid = 'public."{table.name}"'::regclass and a.attnum > 0 and not a.attisdropped
        order by a.attnum;""")
    assert rows == [f"{column.name}|{column.cloudType}|{str(column.required).lower()}" for column in table.columns]


def testEveryCloudTableIsDefinedInTheApp(database):
    rows = database.ok("select tablename from pg_tables where schemaname = 'public' order by tablename;")
    assert rows == sorted([table.name for table in appTables] + ["cloudInfo"])
    assert sorted(syncedTables) == sorted(table.name for table in appTables)


def testTheAppIsBuiltForTheLatestUpgrade(database):
    """Raising appSchema with each new cloud script can't be forgotten (version check, 14b)."""
    assert database.ok('select "schemaVersion" from public."cloudInfo";') == [str(appSchema)]
    assert appSchema == len(cloudScripts)
