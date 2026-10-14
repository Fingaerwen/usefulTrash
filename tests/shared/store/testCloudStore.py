"""Tests for the PC view's store (usefulShared.store.cloudStore) against the cloud stand-in: loading
everything, fetching only changes, writing straight to the cloud, and a failed write changing nothing."""

import asyncio
import datetime as dt

import pytest
from cloudStandIn import CloudStandIn
from usefulTestKit import FakeClock, exampleRow, userA

from gym.tables import appSchema, appTables, tablesByName
from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.store.cloudStore import CloudStore, VersionMismatch, describeCloudError
from usefulShared.tables import toCloud


class TokenSession:
    def __init__(self, cloud):
        self.token = cloud.tokenFor(userA)

    async def freshAccessToken(self):
        return self.token


@pytest.fixture
def cloud():
    return CloudStandIn(FakeClock(dt.datetime(2026, 10, 12, 18, 0, tzinfo=dt.UTC)))


@pytest.fixture
def store(cloud):
    return CloudStore(cloud, TokenSession(cloud), appTables, appSchema, FakeClock(dt.datetime(2026, 10, 12, 18, 0,
                                                                                             tzinfo=dt.UTC)))


def put(cloud, tableName, **columns):
    cloud.storeDirectly(tableName, toCloud(tablesByName[tableName], exampleRow(tableName, **columns)))


def testLoadsEverythingThenOnlyChanges(cloud, store):
    put(cloud, "dailySteps", date=dt.date(2026, 10, 1))
    put(cloud, "bodyWeight")
    counts = []
    assert asyncio.run(store.fetch(counts.append)) == 2 and counts == [1, 2]
    cloud.clock.advance(minutes=10)
    put(cloud, "dailySteps", date=dt.date(2026, 10, 2))
    asyncio.run(store.fetch())
    assert len(store.rows("dailySteps")) == 2 and len(store.rows("bodyWeight")) == 1


def testWritesGoStraightToTheCloud(cloud, store):
    saved = asyncio.run(store.saveMany([("dailySteps", exampleRow("dailySteps"))]))
    assert saved[0]["updatedAt"] == store.clock()  # stamped here, like on the phone
    assert cloud.rows["dailySteps"][saved[0]["id"]]["steps"] == 14000
    assert store.rows("dailySteps") == saved


def testAnEditBeatsTheVersionItReplaces(cloud, store):
    """The PC's clock is behind the phone's edit: the PC's edit is still stamped after it."""
    put(cloud, "dailySteps", updatedAt=dt.datetime(2026, 10, 12, 18, 3, tzinfo=dt.UTC))
    asyncio.run(store.fetch())
    (current,) = store.rows("dailySteps")
    (saved,) = asyncio.run(store.saveMany([("dailySteps", dict(current, steps=9000))]))
    assert saved["updatedAt"] == current["updatedAt"] + dt.timedelta(microseconds=1)
    assert cloud.rows["dailySteps"][saved["id"]]["steps"] == 9000


def testAFailedWriteChangesNothing(cloud, store):
    cloud.offline = True
    with pytest.raises(CloudError) as problem:
        asyncio.run(store.saveMany([("dailySteps", exampleRow("dailySteps"))]))
    assert store.rows("dailySteps") == []
    assert describeCloudError(problem.value).startswith("No connection to the cloud right now. Nothing was changed")


def testVersionsMustFit(cloud, store):
    cloud.minAppSchema = appSchema + 1
    with pytest.raises(VersionMismatch, match="newer version"):
        asyncio.run(store.fetch())
    cloud.minAppSchema, cloud.schemaVersion = 1, appSchema - 1
    with pytest.raises(VersionMismatch, match=f"upgrade {appSchema:03d}"):
        asyncio.run(store.fetch())


def testSigningOutForgetsEverything(cloud, store):
    put(cloud, "bodyWeight")
    asyncio.run(store.fetch())
    store.clear()
    assert store.rows("bodyWeight") == []
    assert asyncio.run(store.fetch()) == 1  # everything again, from the start
