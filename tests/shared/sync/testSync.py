"""Tests for sync (plan 14b) against the cloud stand-in: offline then online, conflicts both ways, the
5-minute fetch overlap, refused changes, the first download, the version check, lost answers and
signed-out pauses. Two phone databases stand for the phone and a second device."""

import asyncio
import datetime as dt

import pytest
from cloudStandIn import CloudStandIn
from usefulTestKit import FakeClock, exampleRow, startOfTests, userA

from gym.phoneSteps import phoneSteps
from gym.tables import appSchema, appTables, tablesByName
from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.store.phoneStore import PhoneStore, runPhoneSteps
from usefulShared.sync import fetchChanges as fetching
from usefulShared.sync.syncEngine import SyncEngine, SyncLoop, SyncOutcome
from usefulShared.tables import dayRowId, momentText, toCloud


class FakeSession:
    """The signed-in session, as sync sees it: hands out the cloud's tokens; renewing makes a new one."""

    def __init__(self, cloud: CloudStandIn, userId: str = userA):
        self.cloud = cloud
        self.userId = userId
        self.token = cloud.tokenFor(userId)
        self.signedIn = True
        self.renewals = 0

    async def freshAccessToken(self) -> str:
        if not self.signedIn:
            raise CloudError(401, "notSignedIn", "Not signed in")
        return self.token

    async def renewNow(self) -> None:
        self.renewals += 1
        self.token = self.cloud.tokenFor(self.userId)


class Device:
    """One device with its own database, clock and sync engine, all talking to the same cloud."""

    def __init__(self, folder, name: str, cloud: CloudStandIn, clock: FakeClock):
        path = str(folder / f"{name}.sqlite3")
        runPhoneSteps(path, phoneSteps)
        self.clock = clock
        self.store = PhoneStore(path, appTables, clock)
        self.store.claimFor(userA)
        self.session = FakeSession(cloud)
        self.engine = SyncEngine(self.store, cloud, self.session, appTables, appSchema, clock)

    def sync(self, onProgress=None) -> SyncOutcome:
        return asyncio.run(self.engine.runRound(onProgress))


@pytest.fixture
def cloudClock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cloud(cloudClock) -> CloudStandIn:
    return CloudStandIn(cloudClock)


@pytest.fixture
def phone(tmp_path, cloud) -> Device:
    return Device(tmp_path, "phone", cloud, FakeClock())


@pytest.fixture
def pc(tmp_path, cloud) -> Device:
    return Device(tmp_path, "pc", cloud, FakeClock())


def advanceAll(*clocks: FakeClock, **delta) -> None:
    for clock in clocks:
        clock.advance(**delta)


# --- Offline, then online (SY2.2) ---------------------------------------------------------------

def testChangesMadeOfflineGoOutWhenTheConnectionReturns(phone, cloud):
    cloud.offline = True
    saved = phone.store.save("dailySteps", exampleRow("dailySteps"))
    outcome = phone.sync()
    assert outcome.status == "offline" and "network" in outcome.problem
    assert phone.store.waiting().count == 1
    cloud.offline = False
    assert phone.sync() == SyncOutcome("done", sent=1, fetched=1)  # it comes back with the cloud's stamp
    assert cloud.rows["dailySteps"][saved["id"]]["steps"] == 14000
    assert phone.store.waiting().count == 0
    assert phone.store.row("dailySteps", saved["id"])["cloudUpdatedAt"] is not None


def testALostAnswerJustMeansSendingAgain(phone, cloud):
    """The cloud stored it but the answer never came: the change stays queued, and sending it again
    (or fetching it back) is harmless."""
    saved = phone.store.save("bodyWeight", exampleRow("bodyWeight"))
    cloud.loseNextAnswer = True
    assert phone.sync().status == "offline"
    assert phone.store.waiting().count == 1
    assert phone.sync().status == "done"
    assert phone.store.waiting().count == 0
    assert list(cloud.rows["bodyWeight"]) == [saved["id"]]


# --- Conflicts: the newest edit wins (G7a, F11.1) -----------------------------------------------

@pytest.mark.parametrize("firstToSync", ["phone", "pc"])
def testNewestEditWinsWhicheverDeviceSyncsFirst(phone, pc, firstToSync):
    """Both devices change the same day's steps while offline; the later edit wins on both."""
    stepsId = dayRowId(tablesByName["dailySteps"], userA, date=dt.date(2026, 10, 12))
    phone.store.save("dailySteps", exampleRow("dailySteps", steps=12000))
    pc.clock.advance(minutes=2)
    pc.store.save("dailySteps", exampleRow("dailySteps", steps=14500))  # made later
    devices = [phone, pc] if firstToSync == "phone" else [pc, phone]
    for device in devices + devices:  # two rounds each, so each sees the other's change
        assert device.sync().status == "done"
    for device in (phone, pc):
        assert device.store.row("dailySteps", stepsId)["steps"] == 14500
        assert device.store.waiting().count == 0


def testDeletingSyncsLikeAnyEdit(phone, pc):
    saved = phone.store.save("bodyWeight", exampleRow("bodyWeight"))
    phone.sync()
    pc.sync()
    pc.clock.advance(minutes=1)
    pc.store.save("bodyWeight", dict(pc.store.row("bodyWeight", saved["id"]), deleted=True))
    pc.sync()
    phone.sync()
    assert phone.store.row("bodyWeight", saved["id"])["deleted"] is True


# --- Fetching (14b) -----------------------------------------------------------------------------

def testFirstDownloadFetchesEverythingWithProgress(phone, cloud, cloudClock):
    """1,200 workouts on another device: three pages, with a running count for "Downloading… N rows"."""
    table = tablesByName["sessions"]
    for day in range(1200):
        row = exampleRow("sessions", date=dt.date(2023, 1, 1) + dt.timedelta(days=day))
        cloud.storeDirectly("sessions", toCloud(table, row))
        cloudClock.advance(seconds=1)
    counts: list[int] = []
    outcome = phone.sync(counts.append)
    assert (outcome.status, outcome.fetched) == ("done", 1200)
    assert len(phone.store.rows("sessions")) == 1200
    assert counts == [500, 1000, 1200]
    assert cloud.calls.count("fetch sessions") == 3


def testPagesNeverSkipRowsStoredInTheSameMicrosecond(phone, cloud, monkeypatch):
    monkeypatch.setattr(fetching, "pageSize", 7)
    table = tablesByName["dailySteps"]
    for day in range(20):  # the cloud's clock doesn't move: every row gets the very same stamp
        cloud.storeDirectly("dailySteps", toCloud(table, exampleRow("dailySteps", date=dt.date(2026, 9, 1) +
                                                                     dt.timedelta(days=day))))
    phone.sync()
    assert len(phone.store.rows("dailySteps")) == 20


def testOverlapCatchesAChangeThatFinishedSavingLate(phone, cloud, cloudClock):
    """A change stamped 2 minutes before the newest one fetched, because it took that long to finish
    saving, still arrives: each fetch starts 5 minutes before the newest stamp seen (14b)."""
    table = tablesByName["dailySteps"]
    cloud.storeDirectly("dailySteps", toCloud(table, exampleRow("dailySteps", date=dt.date(2026, 10, 1))))
    phone.sync()
    late = exampleRow("dailySteps", date=dt.date(2026, 10, 2))
    cloud.storeDirectly("dailySteps", toCloud(table, late), stampedAt=cloudClock.now - dt.timedelta(minutes=2))
    phone.sync()
    assert phone.store.row("dailySteps", late["id"]) is not None


def testCursorMovesOnSoFetchingStaysSmall(phone, cloud, cloudClock):
    """Each fetch re-reads the 5 minutes before the newest row seen (harmless), but nothing older."""
    table = tablesByName["dailySteps"]
    cloud.storeDirectly("dailySteps", toCloud(table, exampleRow("dailySteps", date=dt.date(2026, 10, 1))))
    assert phone.sync().fetched == 1
    cloudClock.advance(minutes=6)
    cloud.storeDirectly("dailySteps", toCloud(table, exampleRow("dailySteps", date=dt.date(2026, 10, 2))))
    assert phone.sync().fetched == 2  # the first row is still within 5 minutes of the newest seen until now
    assert phone.sync().fetched == 1  # now it's 6 minutes older than the newest: only the new row is re-read
    assert len(phone.store.rows("dailySteps")) == 2


def testMalformedCloudRowEndsTheRoundWithTheReason(phone, cloud):
    data = toCloud(tablesByName["bodyWeight"], exampleRow("bodyWeight"))
    cloud.storeDirectly("bodyWeight", dict(data, date="someday"))
    outcome = phone.sync()
    assert outcome.status == "failed" and "badRow" in outcome.problem


# --- Refused changes (12d) ----------------------------------------------------------------------

def testARefusedChangeIsSetAsideAndTheRestStillGoes(phone, cloud):
    """A weight of 0 kg is refused by the cloud; the steps saved with it still go out."""
    badWeight = phone.store.save("bodyWeight", exampleRow("bodyWeight", weightKg=0.0))
    steps = phone.store.save("dailySteps", exampleRow("dailySteps"))
    secondWeight = phone.store.save("bodyWeight", exampleRow("bodyWeight", date=dt.date(2026, 10, 9)))
    outcome = phone.sync()
    assert (outcome.status, outcome.sent) == ("done", 2)
    assert steps["id"] in cloud.rows["dailySteps"] and secondWeight["id"] in cloud.rows["bodyWeight"]
    waiting = phone.store.waiting()
    assert waiting.count == 1
    assert waiting.refused == (("bodyWeight", badWeight["id"],
                                '23514: new row for relation "bodyWeight" violates check constraint'),)
    assert phone.sync().sent == 0  # not sent again until it's edited or retried


def testConnectionDroppingWhileLookingForTheRefusedRowRefusesNothingElse(phone, cloud):
    """The batch is refused, so rows go one by one; the connection drops before the good row: it stays
    queued, not refused."""
    bad = phone.store.save("bodyWeight", exampleRow("bodyWeight", weightKg=0.0))
    phone.clock.advance(seconds=1)  # so the bad row is first in line
    good = phone.store.save("bodyWeight", exampleRow("bodyWeight", date=dt.date(2026, 10, 9)))
    cloud.callsUntilOffline = 3  # the version check, the batch, then the bad row alone
    assert phone.sync().status == "offline"
    assert phone.store.waiting().refused == (("bodyWeight", bad["id"],
                                              '23514: new row for relation "bodyWeight" violates check constraint'),)
    cloud.offline, cloud.callsUntilOffline = False, None
    assert phone.sync().sent == 1
    assert good["id"] in cloud.rows["bodyWeight"]


def testAPhoneClockFarAheadIsRefusedWithTheReason(phone, cloud):
    phone.clock.advance(minutes=10)
    phone.store.save("dailySteps", exampleRow("dailySteps"))
    phone.sync()
    (_, _, reason), = phone.store.waiting().refused
    assert reason.startswith("P0001: futureEdit")


# --- Versions, sign-in --------------------------------------------------------------------------

def testAppTooOldForTheCloudStopsAndKeepsTheOutbox(phone, cloud):
    phone.store.save("dailySteps", exampleRow("dailySteps"))
    cloud.schemaVersion, cloud.minAppSchema = appSchema + 1, appSchema + 1
    outcome = phone.sync()
    assert outcome.status == "appTooOld" and "Update the app" in outcome.problem
    assert phone.store.waiting().count == 1 and "dailySteps" not in cloud.rows


def testCloudNotUpgradedYetStops(phone, cloud):
    phone.store.save("dailySteps", exampleRow("dailySteps"))
    cloud.schemaVersion = appSchema - 1
    outcome = phone.sync()
    assert outcome.status == "cloudTooOld" and f"{appSchema:03d}" in outcome.problem
    assert "dailySteps" not in cloud.rows


def testSignedOutPausesSyncAndKeepsTheOutbox(phone, cloud):
    phone.store.save("dailySteps", exampleRow("dailySteps"))
    phone.session.signedIn = False
    assert phone.sync().status == "signedOut"
    assert phone.store.waiting().count == 1 and cloud.calls == []


def testARefusedTokenIsRenewedOnceAndTheRoundCarriesOn(phone, cloud):
    """The phone's clock says the token is fresh, the cloud says it expired: renew and go on."""
    del cloud.signedIn[phone.session.token]
    phone.store.save("dailySteps", exampleRow("dailySteps"))
    assert phone.sync().status == "done"
    assert phone.session.renewals == 1 and phone.store.waiting().count == 0


def testRoundsNeverOverlap(phone):
    async def twoAtOnce():
        return await asyncio.gather(phone.engine.runRound(), phone.engine.runRound())

    first, second = asyncio.run(twoAtOnce())
    assert first.status == "done" and second.status == "busy"


def testLastSyncTimeIsKept(phone):
    phone.clock.advance(minutes=3)
    phone.sync()
    assert phone.store.meta("lastSyncAt") == momentText(startOfTests + dt.timedelta(minutes=3))


# --- When rounds run (14b) ----------------------------------------------------------------------

def testLoopRunsAtStartAfterChangesAndEveryInterval(phone):
    outcomes: list[SyncOutcome] = []

    async def scenario():
        loop = SyncLoop(phone.engine, outcomes.append, everySec=0.5, afterChangeSec=0.05)
        loop.start()
        await asyncio.sleep(0.02)
        assert len(outcomes) == 1  # at start
        loop.changed()
        loop.changed()  # quick changes share one round
        await asyncio.sleep(0.01)
        assert len(outcomes) == 1  # not at once: a few seconds after the change
        await asyncio.sleep(0.14)
        assert len(outcomes) == 2
        await asyncio.sleep(0.5)
        assert len(outcomes) == 3  # the interval
        loop.resumed()
        await asyncio.sleep(0.02)
        assert len(outcomes) == 4  # back on screen
        loop.stop()

    asyncio.run(scenario())


def testLoopKeepsGoingAfterAnUnexpectedError(phone, monkeypatch):
    outcomes: list[SyncOutcome] = []

    async def broken():
        raise RuntimeError("a bug")

    async def scenario():
        monkeypatch.setattr(phone.engine, "runRound", broken)
        loop = SyncLoop(phone.engine, outcomes.append, everySec=0.05)
        loop.start()
        await asyncio.sleep(0.12)
        loop.stop()

    asyncio.run(scenario())
    assert len(outcomes) >= 2
    assert outcomes[0] == SyncOutcome("failed", problem="unexpected RuntimeError: a bug")
