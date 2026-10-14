"""The app's cloud calls against the real Data API server: PostgREST, which Supabase runs in front of
Postgres, on a local copy of the cloud built from cloud/ (plan 14c). This proves what the stand-in
cloud (tests/cloudStandIn.py) only imitates: the exact paging filters, upserts through the newest-edit
trigger, row-level security, and the cloud's error answers, all through usefulShared.cloud.supabaseApi.
It ends with full sync rounds between two devices.

Postgres and PostgREST run together in one podman pod. Only PostgREST's port is published, on
127.0.0.1, so nothing outside this PC can reach it; the database itself isn't reachable from outside
the pod at all. Sign-in tokens are signed with a random key made for each run and never stored.
Skipped when podman isn't installed.
"""

import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import pytest
from usefulTestKit import FakeClock, exampleRow, userA, userB

from gym.phoneSteps import phoneSteps
from gym.tables import appSchema, appTables, tablesByName
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi, urllibTransport
from usefulShared.store.phoneStore import PhoneStore, runPhoneSteps
from usefulShared.sync import fetchChanges as fetching
from usefulShared.sync.syncEngine import SyncEngine
from usefulShared.tables import fromCloud, momentText, toCloud

repoRoot = Path(__file__).resolve().parents[2]
cloudScripts = sorted((repoRoot / "cloud").glob("[0-9][0-9][0-9]_*.sql"))
standInSql = (Path(__file__).parent / "supabaseStandIn.sql").read_text(encoding="utf-8")

# Pinned by digest, like the Postgres image: PostgREST 16.4, the official image.
postgresImage = (
    "docker.io/library/postgres@sha256:aa90e97ee862e558111d34cfb8b2c4bec768c2b039fb791341686928560263b3"
)
postgrestImage = (
    "docker.io/postgrest/postgrest@sha256:bee9e1efe9d90d8f6be359f756e039dbb6e1972474bc271b7c49c5a495911a41"
)
cloudUrl = "https://cloud.test"  # the address the app thinks it talks to; the transport below redirects it here

pytestmark = pytest.mark.skipif(shutil.which("podman") is None, reason="podman isn't installed")


class LocalCloud:
    """The running pod: the Data API's local address, the token signing key and the admin's psql."""

    def __init__(self, podName: str, port: int, signingKey: str):
        self.podName = podName
        self.port = port
        self.signingKey = signingKey

    def admin(self, sql: str) -> list[str]:
        """Runs SQL as the database admin (like Supabase's SQL editor); returns the rows."""
        result = subprocess.run(
            ["podman", "exec", "-i", f"{self.podName}Db", "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-X",
             "-q", "-At"], input=sql, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        return [line for line in result.stdout.splitlines() if line]

    def tokenFor(self, userId: str, expiresInSec: int = 3600) -> str:
        """A signed-in user's access token, as Supabase Auth would issue it (HS256 with this run's key)."""
        def encoded(part: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

        unsigned = f"{encoded({'alg': 'HS256', 'typ': 'JWT'})}." + encoded(
            {"sub": userId, "role": "authenticated", "exp": int(time.time()) + expiresInSec})
        signature = hmac.new(self.signingKey.encode(), unsigned.encode(), hashlib.sha256).digest()
        return f"{unsigned}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def api(self) -> SupabaseApi:
        """The app's own client, its requests sent to the local PostgREST instead of Supabase."""
        async def localTransport(method, url, headers, body):
            assert url.startswith(f"{cloudUrl}/rest/v1/")  # Supabase serves the Data API under /rest/v1
            localUrl = f"http://127.0.0.1:{self.port}/" + url.removeprefix(f"{cloudUrl}/rest/v1/")
            return await urllibTransport(method, localUrl, headers, body)

        return SupabaseApi(cloudUrl, "testPublishableKey", localTransport)


def _freePort() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _waitFor(check, what: str, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.5)
    raise TimeoutError(f"{what} didn't start within {seconds} s")


@pytest.fixture(scope="module")
def localCloud():
    """Starts Postgres with every cloud script run, then PostgREST in front of it; removes both after."""
    podName = f"usefulTrashDataApi{uuid.uuid4().hex[:8]}"
    port = _freePort()
    signingKey = secrets.token_urlsafe(48)
    subprocess.run(["podman", "pod", "create", "--name", podName, "--publish", f"127.0.0.1:{port}:3000"],
                   check=True, capture_output=True, timeout=60)
    try:
        subprocess.run(["podman", "run", "--detach", "--pod", podName, "--name", f"{podName}Db",
                        "--env", "POSTGRES_HOST_AUTH_METHOD=trust", postgresImage],
                       check=True, capture_output=True, timeout=120)
        cloud = LocalCloud(podName, port, signingKey)

        def databaseReady() -> bool:
            logs = subprocess.run(["podman", "logs", f"{podName}Db"], capture_output=True, text=True)
            if "PostgreSQL init process complete" not in logs.stdout + logs.stderr:
                return False
            probe = subprocess.run(["podman", "exec", f"{podName}Db", "psql", "-U", "postgres", "-Atc", "select 1"],
                                   capture_output=True, text=True)
            return probe.returncode == 0

        _waitFor(databaseReady, "the test Postgres")
        cloud.admin(standInSql)
        cloud.admin(f"insert into auth.users (id) values ('{userA}'), ('{userB}');")
        # PostgREST logs in as "authenticator" and switches to anon or authenticated for each request.
        cloud.admin("create role authenticator login noinherit; grant anon, authenticated to authenticator;")
        for script in cloudScripts:
            cloud.admin(script.read_text(encoding="utf-8"))

        # The signing key reaches the container through the environment, never a command line.
        subprocess.run(["podman", "run", "--detach", "--pod", podName, "--name", f"{podName}Rest",
                        "--env", "PGRST_DB_URI=postgres://authenticator@localhost:5432/postgres",
                        "--env", "PGRST_DB_SCHEMAS=public", "--env", "PGRST_DB_ANON_ROLE=anon",
                        "--env", "PGRST_JWT_SECRET", postgrestImage],
                       check=True, capture_output=True, timeout=120,
                       env={**os.environ, "PGRST_JWT_SECRET": signingKey})

        def dataApiReady() -> bool:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/cloudInfo", timeout=2) as answer:
                    return answer.status in (200, 401)
            except urllib.error.HTTPError as answer:
                return answer.code in (401, 403)
            except OSError:
                return False

        _waitFor(dataApiReady, "PostgREST")
        yield cloud
    finally:
        subprocess.run(["podman", "pod", "rm", "--force", podName], capture_output=True, timeout=120)


@pytest.fixture
def cloud(localCloud) -> LocalCloud:
    """The local cloud with every synced table emptied before the test."""
    names = ", ".join(f'public."{table.name}"' for table in appTables)
    localCloud.admin(f"truncate {names};")
    return localCloud


def run(coroutine):
    return asyncio.run(coroutine)


def nowRow(tableName: str, userId: str = userA, minutesAgo: float = 1, **columns) -> dict:
    """A valid row edited a little while ago (real time: the cloud refuses edits too far in the future)."""
    updatedAt = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutesAgo)
    return exampleRow(tableName, userId=userId, updatedAt=updatedAt, **columns)


def cloudRows(cloud: LocalCloud, tableName: str, userId: str = userA) -> list[dict]:
    """Every row of a table as the app reads it, through the Data API as that user."""
    api, token = cloud.api(), cloud.tokenFor(userId)
    table = tablesByName[tableName]
    page = run(api.fetchRows(tableName, table.columnNames, "1970-01-01T00:00:00+00:00", None, 1000, token))
    return [fromCloud(table, data) for data in page]


# --- Single calls -------------------------------------------------------------------------------

def testCloudInfoIsReadable(cloud):
    assert run(cloud.api().readCloudInfo(cloud.tokenFor(userA))) == (appSchema, 1)


def testUpsertStoresRowsAndTheCloudStampsThem(cloud):
    rows = [nowRow("dailySteps", date=dt.date(2026, 10, day)) for day in (1, 2, 3)]
    run(cloud.api().upsertRows("dailySteps", [toCloud(tablesByName["dailySteps"], row) for row in rows],
                               cloud.tokenFor(userA)))
    stored = {row["id"]: row for row in cloudRows(cloud, "dailySteps")}
    assert set(stored) == {row["id"] for row in rows}
    for row in rows:
        assert stored[row["id"]]["steps"] == 14000
        assert stored[row["id"]]["cloudUpdatedAt"] > row["updatedAt"]  # stamped by the cloud on arrival


def testOnlyANewerEditReplacesTheStoredOne(cloud):
    """Through the real upsert: an older edit is quietly ignored (2xx, nothing changes)."""
    api, token, table = cloud.api(), cloud.tokenFor(userA), tablesByName["bodyWeight"]
    current = nowRow("bodyWeight", minutesAgo=2, weightKg=81.2)
    run(api.upsertRows("bodyWeight", [toCloud(table, current)], token))
    older = dict(current, updatedAt=current["updatedAt"] - dt.timedelta(minutes=1), weightKg=90.0)
    run(api.upsertRows("bodyWeight", [toCloud(table, older)], token))
    assert cloudRows(cloud, "bodyWeight")[0]["weightKg"] == 81.2
    newer = dict(current, updatedAt=current["updatedAt"] + dt.timedelta(minutes=1), weightKg=80.9)
    run(api.upsertRows("bodyWeight", [toCloud(table, newer)], token))
    assert cloudRows(cloud, "bodyWeight")[0]["weightKg"] == 80.9


def testRefusalsComeBackWithTheCloudsReason(cloud):
    api, token, table = cloud.api(), cloud.tokenFor(userA), tablesByName["bodyWeight"]
    future = nowRow("bodyWeight", minutesAgo=-10)
    with pytest.raises(CloudError) as problem:
        run(api.upsertRows("bodyWeight", [toCloud(table, future)], token))
    assert (problem.value.statusCode, problem.value.errorCode) == (400, "P0001")
    assert problem.value.message.startswith("futureEdit:") and not problem.value.isTemporary

    with pytest.raises(CloudError) as problem:
        run(api.upsertRows("bodyWeight", [toCloud(table, nowRow("bodyWeight", weightKg=0.0))], token))
    assert (problem.value.statusCode, problem.value.errorCode) == (400, "23514")


def testABatchIsAllOrNothing(cloud):
    """One refused row refuses the whole request, which is why sync then sends one by one."""
    api, token, table = cloud.api(), cloud.tokenFor(userA), tablesByName["bodyWeight"]
    good = nowRow("bodyWeight", date=dt.date(2026, 10, 9))
    bad = nowRow("bodyWeight", weightKg=0.0)
    with pytest.raises(CloudError):
        run(api.upsertRows("bodyWeight", [toCloud(table, good), toCloud(table, bad)], token))
    assert cloudRows(cloud, "bodyWeight") == []


def testNobodyCanWriteOrReadSomeoneElsesRows(cloud):
    api, table = cloud.api(), tablesByName["dailySteps"]
    run(api.upsertRows("dailySteps", [toCloud(table, nowRow("dailySteps"))], cloud.tokenFor(userA)))
    assert cloudRows(cloud, "dailySteps", userB) == []
    with pytest.raises(CloudError) as problem:
        run(api.upsertRows("dailySteps", [toCloud(table, nowRow("dailySteps", userId=userA, date=dt.date(2026, 9, 1)))],
                           cloud.tokenFor(userB)))
    assert problem.value.errorCode == "42501" and not problem.value.isTemporary


def testAnExpiredTokenIsASessionProblem(cloud):
    with pytest.raises(CloudError) as problem:
        run(cloud.api().readCloudInfo(cloud.tokenFor(userA, expiresInSec=-60)))
    assert problem.value.isSessionProblem


def testAnonymousVisitorsCanOnlyPing(cloud):
    """The daily ping workflow's call (plan 12): POST /rest/v1/rpc/ping with only the publishable key."""
    request = urllib.request.Request(f"http://127.0.0.1:{cloud.port}/rpc/ping", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as answer:
        assert json.loads(answer.read()) == "ok"
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(f"http://127.0.0.1:{cloud.port}/bodyWeight", timeout=10)
    assert refused.value.code in (401, 403)


# --- Paging (14b) -------------------------------------------------------------------------------

def testPagesNeverSkipOrRepeatRowsWithTheSameStamp(cloud):
    """Rows stamped in the very same microsecond (written here with the trigger paused) still come
    exactly once each, through the real or=(...) filter with quoted times."""
    table = tablesByName["dailySteps"]
    rows = [nowRow("dailySteps", date=dt.date(2026, 9, 1) + dt.timedelta(days=day)) for day in range(23)]
    values = ", ".join(
        f"('{row['id']}', '{userA}', '{momentText(row['updatedAt'])}', false, '2026-10-12T07:00:00.123456+00:00', "
        f"'{row['date'].isoformat()}', {row['steps']})" for row in rows)
    cloud.admin(f'alter table public."dailySteps" disable trigger "keepNewestEdit";'
                f'insert into public."dailySteps" values {values};'
                f'alter table public."dailySteps" enable trigger "keepNewestEdit";')
    api, token = cloud.api(), cloud.tokenFor(userA)
    seen: list[str] = []
    after = None
    while True:
        page = run(api.fetchRows("dailySteps", table.columnNames, "2026-10-12T07:00:00+00:00", after, 5, token))
        seen += [row["id"] for row in page]
        if len(page) < 5:
            break
        last = fromCloud(table, page[-1])
        after = (momentText(last["cloudUpdatedAt"]), last["id"])
    assert sorted(seen) == sorted(row["id"] for row in rows) and len(seen) == 23


def testSinceLeavesOutOlderRows(cloud):
    table = tablesByName["dailySteps"]
    run(cloud.api().upsertRows("dailySteps", [toCloud(table, nowRow("dailySteps"))], cloud.tokenFor(userA)))
    stamp = cloudRows(cloud, "dailySteps")[0]["cloudUpdatedAt"]
    later = momentText(stamp + dt.timedelta(microseconds=1))
    assert run(cloud.api().fetchRows("dailySteps", ["id"], later, None, 10, cloud.tokenFor(userA))) == []
    assert len(run(cloud.api().fetchRows("dailySteps", ["id"], momentText(stamp), None, 10, cloud.tokenFor(userA)))) == 1


# --- Whole sync rounds --------------------------------------------------------------------------

class RealClock:
    def __call__(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)


class TokenSession:
    def __init__(self, cloud: LocalCloud):
        self.cloud = cloud

    async def freshAccessToken(self) -> str:
        return self.cloud.tokenFor(userA)

    async def renewNow(self) -> None:
        pass


def device(cloud: LocalCloud, folder: Path, name: str) -> tuple[PhoneStore, SyncEngine]:
    path = str(folder / f"{name}.sqlite3")
    runPhoneSteps(path, phoneSteps)
    store = PhoneStore(path, appTables, RealClock())
    store.claimFor(userA)
    return store, SyncEngine(store, cloud.api(), TokenSession(cloud), appTables, appSchema, RealClock())


def testTwoDevicesSyncThroughTheRealDataApi(cloud, tmp_path, monkeypatch):
    """The phone logs a workout day and a weight; the second device gets them, edits the weight, and
    the phone ends up with that edit. Small pages, so paging runs for real."""
    monkeypatch.setattr(fetching, "pageSize", 2)
    phone, phoneSync = device(cloud, tmp_path, "phone")
    other, otherSync = device(cloud, tmp_path, "other")
    session = phone.save("sessions", exampleRow("sessions", updatedAt=RealClock()()))
    log = phone.save("exerciseLogs", exampleRow("exerciseLogs", updatedAt=RealClock()()))
    weight = phone.save("bodyWeight", exampleRow("bodyWeight", updatedAt=RealClock()()))
    steps = [phone.save("dailySteps", exampleRow("dailySteps", date=dt.date(2026, 10, day))) for day in range(1, 6)]

    outcome = run(phoneSync.runRound())
    assert (outcome.status, outcome.sent) == ("done", 8)
    assert phone.waiting().count == 0
    assert run(otherSync.runRound()).status == "done"
    assert other.row("sessions", session["id"])["planImportId"] == session["planImportId"]
    assert other.row("exerciseLogs", log["id"])["sets"] == [{"reps": 9, "weightKg": 82.5}]
    assert len(other.rows("dailySteps")) == len(steps)

    other.save("bodyWeight", dict(other.row("bodyWeight", weight["id"]), weightKg=80.9))
    run(otherSync.runRound())
    run(phoneSync.runRound())
    assert phone.row("bodyWeight", weight["id"])["weightKg"] == 80.9
    assert phone.waiting().count == 0 and other.waiting().count == 0
