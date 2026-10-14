"""Tests for the phone's database (usefulShared.store.phoneStore with gym/phoneSteps.py): its upgrade
steps, saving edits with the outbox, and what sync relies on (plan 14, 14b, 14c)."""

import datetime as dt
import sqlite3

import pytest
from usefulTestKit import FakeClock, exampleRow, startOfTests, userA, userB

from gym.phoneSteps import phoneSteps
from gym.tables import appSchema, appTables
from usefulShared.store.phoneStore import PhoneDatabaseError, PhoneStore, runPhoneSteps

microsecond = dt.timedelta(microseconds=1)


@pytest.fixture
def path(tmp_path) -> str:
    return str(tmp_path / "gymTracker.sqlite3")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(path, clock) -> PhoneStore:
    runPhoneSteps(path, phoneSteps)
    store = PhoneStore(path, appTables, clock)
    store.claimFor(userA)
    yield store
    store.close()


# --- Upgrade steps (14c) ------------------------------------------------------------------------

def testOneStepPerCloudUpgrade():
    assert len(phoneSteps) == appSchema


def testStepsBuildExactlyTheAppTables(path):
    runPhoneSteps(path, phoneSteps)
    db = sqlite3.connect(path)
    storedAs = {"uuid": "TEXT", "text": "TEXT", "date": "TEXT", "timestamp with time zone": "TEXT", "jsonb": "TEXT",
                "integer": "INTEGER", "bigint": "INTEGER", "boolean": "INTEGER"}
    for table in appTables:
        found = [(name, kind.upper(), bool(notNull), bool(key))
                 for _, name, kind, notNull, _, key in db.execute(f'pragma table_info("{table.name}")')]
        expected = [(column.name, storedAs.get(column.cloudType, "REAL"),
                     column.required and not column.stampedByCloud, column.name == "id")
                    for column in table.columns]
        assert found == expected, table.name
    phoneOnly = {name for (name,) in db.execute("select name from sqlite_master where type = 'table'")}
    assert phoneOnly - {table.name for table in appTables} == {"outbox", "syncState", "meta"}


def testStepsRunOnlyOnce(path):
    assert runPhoneSteps(path, phoneSteps) == len(phoneSteps)
    assert runPhoneSteps(path, phoneSteps) == 0


def testAFailedStepChangesNothing(store, path):
    saved = store.save("bodyWeight", exampleRow("bodyWeight"))
    brokenNextStep = phoneSteps + (('alter table "bodyWeight" add column "note" text', "this is not SQL"),)
    with pytest.raises(PhoneDatabaseError, match="step 2"):
        runPhoneSteps(path, brokenNextStep)
    db = sqlite3.connect(path)
    assert db.execute("pragma user_version").fetchone()[0] == len(phoneSteps)
    assert "note" not in [row[1] for row in db.execute('pragma table_info("bodyWeight")')]
    assert store.row("bodyWeight", saved["id"]) == saved


def testTheCopyIsPutBackEvenIfAStepCommittedHalfway(path):
    """A badly written step that commits partway can't be undone by a rollback; the copy restores it."""
    runPhoneSteps(path, phoneSteps)
    badStep = phoneSteps + (('alter table "bodyWeight" add column "note" text', "commit", "this is not SQL"),)
    with pytest.raises(PhoneDatabaseError):
        runPhoneSteps(path, badStep)
    db = sqlite3.connect(path)
    assert "note" not in [row[1] for row in db.execute('pragma table_info("bodyWeight")')]
    assert db.execute("pragma user_version").fetchone()[0] == len(phoneSteps)


def testDatabaseFromANewerAppIsRefused(path):
    runPhoneSteps(path, phoneSteps)
    sqlite3.connect(path).execute("pragma user_version = 99")
    with pytest.raises(PhoneDatabaseError, match="newer version"):
        runPhoneSteps(path, phoneSteps)


def testFolderThatCantBeOpened(tmp_path):
    with pytest.raises(PhoneDatabaseError, match="can't be opened"):
        runPhoneSteps(str(tmp_path / "missing" / "gym.sqlite3"), phoneSteps)


def testUnreadableDatabaseFile(path):
    with open(path, "wb") as file:
        file.write(b"not a database" * 100)
    with pytest.raises(PhoneDatabaseError, match="can't be read"):
        runPhoneSteps(path, phoneSteps)


# --- Saving edits (CS1.1) -----------------------------------------------------------------------

def testSaveKeepsTheRowAndQueuesIt(store):
    saved = store.save("dailySteps", exampleRow("dailySteps"))
    assert store.row("dailySteps", saved["id"]) == saved
    assert store.rows("dailySteps") == [saved]
    assert store.waiting().count == 1
    assert store.changesToSend(10) == [("dailySteps", saved)]


def testSaveStampsTheEditTime(store, clock):
    """The device's clock says when the edit was made; whatever the row said is replaced (F11.1)."""
    clock.advance(hours=2)
    saved = store.save("dailySteps", exampleRow("dailySteps", updatedAt=startOfTests - dt.timedelta(days=9)))
    assert saved["updatedAt"] == clock.now


def testAnEditAlwaysBeatsTheVersionItReplaces(store, clock):
    """The clock went back an hour since the last edit: the new edit is still stamped after it."""
    first = store.save("dailySteps", exampleRow("dailySteps"))
    clock.advance(hours=-1)
    second = store.save("dailySteps", dict(first, steps=15000))
    assert second["updatedAt"] == first["updatedAt"] + microsecond


def testEditingAgainKeepsOneEntryQueuedSinceTheFirstEdit(store, clock):
    first = store.save("bodyWeight", exampleRow("bodyWeight"))
    clock.advance(minutes=10)
    store.save("bodyWeight", dict(first, weightKg=81.0))
    waiting = store.waiting()
    assert (waiting.count, waiting.oldestQueuedAt) == (1, startOfTests)


def testMalformedRowIsNotSaved(store):
    with pytest.raises(ValueError, match="bodyWeight.weightKg"):
        store.save("bodyWeight", exampleRow("bodyWeight", weightKg="heavy"))
    assert store.rows("bodyWeight") == [] and store.waiting().count == 0


def testRowAndOutboxAreSavedTogetherOrNotAtAll(store, path):
    """If queuing fails, the edit isn't kept either: nothing saved can be missing from the outbox."""
    sqlite3.connect(path, isolation_level=None).execute('drop table "outbox"')
    with pytest.raises(sqlite3.OperationalError):
        store.save("dailySteps", exampleRow("dailySteps"))
    assert store.rows("dailySteps") == []


def testAnotherAccountsRowIsRefused(store):
    with pytest.raises(ValueError, match="another account"):
        store.save("dailySteps", exampleRow("dailySteps", userId=userB))


# --- Sending (14b) ------------------------------------------------------------------------------

def testSentChangeLeavesTheOutbox(store):
    saved = store.save("dailySteps", exampleRow("dailySteps"))
    store.markSent("dailySteps", [(saved["id"], saved["updatedAt"])])
    assert store.waiting().count == 0 and store.changesToSend(10) == []


def testAChangeEditedWhileSendingStaysWaiting(store, clock):
    """The answer for the first version arrives after a second edit: the second must still be sent."""
    first = store.save("dailySteps", exampleRow("dailySteps"))
    clock.advance(seconds=5)
    second = store.save("dailySteps", dict(first, steps=15000))
    store.markSent("dailySteps", [(first["id"], first["updatedAt"])])
    assert store.changesToSend(10) == [("dailySteps", second)]


def testRefusedChangeWaitsUntilEditedOrRetried(store, clock):
    saved = store.save("bodyWeight", exampleRow("bodyWeight"))
    store.markRefused("bodyWeight", saved["id"], saved["updatedAt"], "P0001: futureEdit: check the clock")
    assert store.changesToSend(10) == []
    assert store.waiting().refused == (("bodyWeight", saved["id"], "P0001: futureEdit: check the clock"),)
    assert store.waiting().count == 1  # still not in the cloud
    clock.advance(seconds=1)
    store.save("bodyWeight", dict(saved, weightKg=81.0))  # editing it clears the refusal
    assert len(store.changesToSend(10)) == 1
    store.markRefused("bodyWeight", saved["id"], store.row("bodyWeight", saved["id"])["updatedAt"], "again")
    assert store.sendRefusedAgain() == 1 and len(store.changesToSend(10)) == 1


def testOldestChangesAreSentFirst(store, clock):
    """By when they were made, not by id: the first change has the larger id here."""
    first = store.save("backups", exampleRow("backups", id="ffffffff-0000-4000-8000-000000000000"))
    clock.advance(seconds=1)
    store.save("backups", exampleRow("backups", id="00000000-0000-4000-8000-000000000000"))
    assert store.changesToSend(1) == [("backups", first)]


# --- Fetching (14b) -----------------------------------------------------------------------------

def cloudVersion(row: dict, updatedAt: dt.datetime, **changes) -> dict:
    """The row as the cloud would hand it back: an edit time and the cloud's own stamp."""
    return dict(row, updatedAt=updatedAt, cloudUpdatedAt=updatedAt + dt.timedelta(seconds=1), **changes)


def testFetchedRowReplacesOnlyAnOlderOne(store, clock):
    clock.advance(minutes=10)
    local = store.save("dailySteps", exampleRow("dailySteps"))
    older = cloudVersion(local, startOfTests, steps=1)
    assert store.applyFetched("dailySteps", [older], older["cloudUpdatedAt"]) == 0
    assert store.row("dailySteps", local["id"])["steps"] == 14000
    newer = cloudVersion(local, local["updatedAt"] + dt.timedelta(minutes=1), steps=2)
    assert store.applyFetched("dailySteps", [newer], newer["cloudUpdatedAt"]) == 1
    assert store.row("dailySteps", local["id"]) == newer


def testANewerEditFromElsewhereWinsOverAWaitingOne(store):
    """Conflict: the PC view edited the same row later than the phone's waiting edit (G7a)."""
    local = store.save("dailySteps", exampleRow("dailySteps"))
    fromPc = cloudVersion(local, local["updatedAt"] + dt.timedelta(minutes=5), steps=9500)
    store.applyFetched("dailySteps", [fromPc], fromPc["cloudUpdatedAt"])
    assert store.row("dailySteps", local["id"])["steps"] == 9500
    assert store.waiting().count == 0  # the phone's older edit would be ignored by the cloud anyway


def testFetchingTheSameEditConfirmsIt(store):
    """The answer to a send was lost, but the cloud has it: fetching it back clears the outbox."""
    local = store.save("dailySteps", exampleRow("dailySteps"))
    echo = cloudVersion(local, local["updatedAt"])
    assert store.applyFetched("dailySteps", [echo], echo["cloudUpdatedAt"]) == 0
    assert store.waiting().count == 0
    assert store.row("dailySteps", local["id"])["cloudUpdatedAt"] == echo["cloudUpdatedAt"]


def testFetchingTheSameRowTwiceIsHarmless(store):
    row = cloudVersion(exampleRow("bodyWeight"), startOfTests)
    assert store.applyFetched("bodyWeight", [row], row["cloudUpdatedAt"]) == 1
    assert store.applyFetched("bodyWeight", [row], row["cloudUpdatedAt"]) == 0
    assert store.rows("bodyWeight") == [row] and store.waiting().count == 0


def testFetchCursorOnlyMovesForward(store):
    assert store.fetchCursor("bodyWeight") is None
    store.applyFetched("bodyWeight", [], startOfTests)
    store.applyFetched("bodyWeight", [], startOfTests - dt.timedelta(hours=1))
    assert store.fetchCursor("bodyWeight") == startOfTests


def testAnotherAccountsFetchedRowIsIgnored(store):
    row = cloudVersion(exampleRow("bodyWeight", userId=userB), startOfTests)
    assert store.applyFetched("bodyWeight", [row], row["cloudUpdatedAt"]) == 0
    assert store.rows("bodyWeight") == []


# --- Whose data (14b) ---------------------------------------------------------------------------

def testADifferentAccountSigningInClearsEverything(store):
    store.save("bodyWeight", exampleRow("bodyWeight"))
    store.applyFetched("dailySteps", [], startOfTests)
    assert store.claimFor(userA) is False and store.owner() == userA
    assert store.claimFor(userB) is True
    assert store.owner() == userB
    assert store.rows("bodyWeight") == [] and store.waiting().count == 0 and store.fetchCursor("dailySteps") is None


def testSeveralEditsAreSavedTogetherOrNotAtAll(store):
    """A workout day and its first exercise go in together; a bad row keeps the good one out too."""
    session = exampleRow("sessions")
    with pytest.raises(ValueError):
        store.saveMany([("sessions", session), ("exerciseLogs", exampleRow("exerciseLogs", targetReps=True))])
    assert store.rows("sessions") == [] and store.waiting().count == 0
    saved = store.saveMany([("sessions", session), ("exerciseLogs", exampleRow("exerciseLogs"))])
    assert [row["id"] for row in saved] == [session["id"], exampleRow("exerciseLogs")["id"]]
    assert store.waiting().count == 2
