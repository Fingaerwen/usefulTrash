"""Tests for the table definitions and value conversions (plan 14): IDs that can't duplicate, edit
times that always move forward, and rows that survive the trip to SQLite and to the cloud unchanged."""

import datetime as dt

import pytest
from usefulTestKit import exampleRow, startOfTests, userA, userB

from gym.tables import appTables, exerciseLogs, plans, sessions, tablesByName
from usefulShared.tables import (
    bodyWeight,
    checkRow,
    dayRowId,
    editTime,
    fromCloud,
    fromLocal,
    toCloud,
    toLocal,
)

friday = dt.date(2026, 10, 16)


# --- IDs (DT1.1 / DT2.1) ------------------------------------------------------------------------

def testDayRowIdsNeverChange():
    """These exact IDs are in the cloud once you've logged: changing how they're made would duplicate rows."""
    assert dayRowId(bodyWeight, userA, date=friday) == "be055b0d-fdfa-5290-8a6f-eb9d25bde5f3"
    assert dayRowId(sessions, userA, date=friday) == "4b3cd21b-3fff-50d8-accf-b254a88d07fb"
    assert dayRowId(exerciseLogs, userA, date=friday, exerciseId="benchPress") == "258e2ba5-4a73-5950-a9a1-71f31c17f17f"


def testDayRowIdsDifferByTableUserDateAndExercise():
    ids = {
        dayRowId(bodyWeight, userA, date=friday),
        dayRowId(sessions, userA, date=friday),
        dayRowId(bodyWeight, userB, date=friday),
        dayRowId(bodyWeight, userA, date=friday + dt.timedelta(days=1)),
        dayRowId(exerciseLogs, userA, date=friday, exerciseId="benchPress"),
        dayRowId(exerciseLogs, userA, date=friday, exerciseId="dips"),
    }
    assert len(ids) == 6


def testDayRowIdsNeedTheirKey():
    with pytest.raises(ValueError):
        dayRowId(exerciseLogs, userA, date=friday)
    with pytest.raises(ValueError):
        dayRowId(plans, userA, date=friday)  # plan imports get random IDs


# --- Edit times (F11.1) -------------------------------------------------------------------------

def testEditTimeIsNow():
    assert editTime(startOfTests, previous=startOfTests - dt.timedelta(hours=1)) == startOfTests


def testEditAlwaysBeatsTheVersionItReplaces():
    """If the clock is behind the stored version (a clock set back, or the PC's clock ahead), the edit is
    stamped just after it, so it still wins."""
    later = startOfTests + dt.timedelta(minutes=3)
    assert editTime(startOfTests, previous=later) == later + dt.timedelta(microseconds=1)
    assert editTime(startOfTests, previous=startOfTests) == startOfTests + dt.timedelta(microseconds=1)


def testEditTimeIsInUtc():
    berlin = dt.timezone(dt.timedelta(hours=2))
    stamped = editTime(dt.datetime(2026, 10, 12, 9, 0, tzinfo=berlin))
    assert stamped == startOfTests and stamped.tzinfo == dt.UTC


# --- Round trips -------------------------------------------------------------------------------

@pytest.mark.parametrize("table", appTables, ids=lambda table: table.name)
def testRowsSurviveSQLiteAndTheCloud(table):
    row = exampleRow(table.name, cloudUpdatedAt=startOfTests + dt.timedelta(seconds=1))
    assert fromLocal(table, toLocal(table, row)) == row
    cloudCopy = dict(toCloud(table, row), cloudUpdatedAt="2026-10-12T07:00:01+00:00")
    assert fromCloud(table, cloudCopy) == row


def testTheCloudsStampIsNeverSent():
    assert "cloudUpdatedAt" not in toCloud(bodyWeight, exampleRow("bodyWeight"))


def testMomentsAreFixedWidthUtcText():
    """Fixed width, so moments sort correctly as text in SQLite (fetch cursors, the outbox)."""
    row = exampleRow("bodyWeight", updatedAt=dt.datetime(2026, 10, 12, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=2))))
    values = dict(zip(bodyWeight.columnNames, toLocal(bodyWeight, row)))
    assert values["updatedAt"] == "2026-10-12T07:00:00.000000+00:00"
    assert values["deleted"] == 0


def testCloudAnswersInPostgresFormatAreRead():
    """The Data API leaves out trailing zeros of fractions. Numeric comes as a JSON number."""
    data = toCloud(bodyWeight, exampleRow("bodyWeight"))
    data.update(updatedAt="2026-10-12T07:00:00.12+00:00", cloudUpdatedAt="2026-10-12T07:00:01+00:00", weightKg=81)
    row = fromCloud(bodyWeight, data)
    assert row["updatedAt"] == dt.datetime(2026, 10, 12, 7, 0, 0, 120000, tzinfo=dt.UTC)
    assert row["weightKg"] == 81.0 and isinstance(row["weightKg"], float)


# --- Checks ------------------------------------------------------------------------------------

@pytest.mark.parametrize(("column", "value"), [
    ("weightKg", True),  # a boolean isn't a number
    ("weightKg", 81.234),  # the cloud keeps 2 decimals and would round it
    ("weightKg", 1000.0),  # numeric(5,2) holds up to 999.99
    ("weightKg", float("nan")),
    ("date", dt.datetime(2026, 10, 16, 7, 0, tzinfo=dt.UTC)),  # a moment isn't a date
    ("updatedAt", dt.datetime(2026, 10, 16, 7, 0)),  # no time zone
    ("userId", "ABCDEF00-0000-0000-0000-000000000001"),  # UUIDs are kept in lower case
    ("deleted", 0),
    ("updatedAt", None),
])
def testWrongValuesAreRefused(column, value):
    row = exampleRow("bodyWeight")
    row[column] = value
    with pytest.raises(ValueError, match=f"bodyWeight.{column}"):
        checkRow(bodyWeight, row)


def testCheckNamesTheColumnButNeverTheValue():
    """Errors may end up in the log, so they never repeat a value."""
    row = exampleRow("bodyWeight", weightKg="81.2 kg secret")
    with pytest.raises(ValueError) as problem:
        checkRow(bodyWeight, row)
    assert "secret" not in str(problem.value)


def testMissingAndUnknownColumnsAreRefused():
    row = exampleRow("dailySteps")
    del row["steps"]
    with pytest.raises(ValueError, match="dailySteps.steps is missing"):
        checkRow(tablesByName["dailySteps"], row)
    with pytest.raises(ValueError, match="no column calories"):
        checkRow(tablesByName["dailySteps"], dict(exampleRow("dailySteps"), calories=5))


def testMalformedCloudRowsAreRefused():
    data = toCloud(bodyWeight, exampleRow("bodyWeight"))
    with pytest.raises(ValueError, match="has no cloudUpdatedAt"):
        fromCloud(bodyWeight, data)
    with pytest.raises(ValueError, match="bodyWeight.date can't be read"):
        fromCloud(bodyWeight, dict(data, cloudUpdatedAt="2026-10-12T07:00:01+00:00", date="16/10/2026"))
    with pytest.raises(ValueError, match="bodyWeight.deleted must be true or false"):
        fromCloud(bodyWeight, dict(data, cloudUpdatedAt="2026-10-12T07:00:01+00:00", deleted=0))


def testBooleansAreNotWholeNumbers():
    """Python counts True as 1, so it must be refused explicitly."""
    with pytest.raises(ValueError, match="dailySteps.steps must be a whole number"):
        checkRow(tablesByName["dailySteps"], exampleRow("dailySteps", steps=True))
