"""Tests for reading Talon's rows as facts (usefulShared.training.workouts), the reader Talon and Ambrosia share,
and which days had a finished workout that counts, for Ambrosia's water (apps/diet/docs/plan.md AM12.4). Days are
counted from Monday 12 Oct 2026."""

import datetime as dt

from usefulShared.tables import dayRowId, exerciseLogs, sessions
from usefulShared.training.workouts import finishedWorkoutDays, importedPlans, readSets
from usefulTestKit import exampleRow, userA

monday = dt.date(2026, 10, 12)
moment = dt.datetime(2026, 10, 12, 8, tzinfo=dt.UTC)


def machine(exerciseId: str) -> dict:
    return {"exerciseId": exerciseId, "name": exerciseId.capitalize(), "equipment": "machine", "sets": 3,
            "repsMin": 8, "repsMax": 12, "weightKg": 40, "incrementKg": 2.5}


rest = {"title": "Rest", "restDay": True}
planJson = {"planId": "test", "name": "Test", "version": 1, "weeklyTarget": 2, "week": [
    {"day": "monday", "title": "Ten", "exercises": [machine(f"ten{number}") for number in range(10)]},
    dict(rest, day="tuesday"), dict(rest, day="wednesday"), dict(rest, day="thursday"),
    {"day": "friday", "title": "Three", "exercises": [machine("three0"), machine("three1"), machine("wrist")]},
    dict(rest, day="saturday"), dict(rest, day="sunday")]}


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def planRow(**columns) -> dict:
    return exampleRow("plans", **{"id": "11111111-1111-1111-1111-111111111111", "effectiveDate": monday,
                                  "importedAt": moment, "startStep": 0, "planJson": planJson, **columns})


def sessionRow(n: int, finished: bool, **columns) -> dict:
    return exampleRow("sessions", **{"id": dayRowId(sessions, userA, date=day(n)), "date": day(n),
                                     "planImportId": planRow()["id"], "stepIndex": day(n).weekday(),
                                     "finishedAt": moment if finished else None, **columns})


def logRow(n: int, exerciseId: str, skipped: bool = False, **columns) -> dict:
    return exampleRow("exerciseLogs", **{
        "id": dayRowId(exerciseLogs, userA, date=day(n), exerciseId=exerciseId), "date": day(n),
        "exerciseId": exerciseId, "sets": [] if skipped else [{"reps": 8, "weightKg": 40}] * 3, "minutes": None,
        "skipped": skipped, "declinedSuggestion": False, **columns})


def mondayLogs(doneCount: int) -> list[dict]:
    """Monday's session has ten exercises: the first doneCount done, the rest skipped."""
    return [logRow(0, f"ten{number}", skipped=number >= doneCount) for number in range(10)]


def finished(rows: dict, today: dt.date) -> set[dt.date]:
    return finishedWorkoutDays({"plans": [planRow()], **rows}, today)


def testAFinishedWorkoutThatCountsIsADay():
    assert finished({"sessions": [sessionRow(0, True)], "exerciseLogs": mondayLogs(7)}, day(0)) == {day(0)}


def testNotBeforeFinishThenAtMidnight():
    """Past 70% it counts in Talon at once, but the water waits for Finish or the day being over (R5a)."""
    rows = {"sessions": [sessionRow(0, False)], "exerciseLogs": mondayLogs(10)}
    assert finished(rows, day(0)) == set()
    assert finished(rows, day(1)) == {day(0)}


def testMoreThan30PercentSkippedIsNoDay():
    rows = {"sessions": [sessionRow(0, True)], "exerciseLogs": mondayLogs(6)}
    assert finished(rows, day(0)) == set() and finished(rows, day(3)) == set()


def testAWorkoutTakenAwayIsNoDay():
    """Taking back its last entry or Delete this workout marks the session deleted: the day goes (AM12.5)."""
    rows = {"sessions": [sessionRow(0, True, deleted=True)],
            "exerciseLogs": [dict(row, deleted=True) for row in mondayLogs(10)]}
    assert finished(rows, day(0)) == set()


def testADayAheadCountsOnceFinished():
    """Talon logs a day ahead under its own date (DY1.1): finished there, it's that day."""
    rows = {"sessions": [sessionRow(4, True)], "exerciseLogs": [logRow(4, "three0"), logRow(4, "three1"),
                                                                logRow(4, "wrist")]}
    assert finished(rows, day(0)) == {day(4)}
    unfinished = {"sessions": [sessionRow(4, False)], "exerciseLogs": rows["exerciseLogs"]}
    assert finished(unfinished, day(0)) == set()


def testAPlanItCantReadIsLeftOutAndItsIdKept():
    plans, unreadable = importedPlans([planRow(), planRow(id="22222222-2222-2222-2222-222222222222",
                                                          planJson={"week": "nonsense"})])
    assert [imported.start.planImportId for imported in plans] == [planRow()["id"]]
    assert unreadable == ["22222222-2222-2222-2222-222222222222"]


def testMalformedSetsAreLeftOut():
    sets = readSets([{"reps": 8, "weightKg": 40}, {"reps": "8"}, "x", {"reps": 6, "weightKg": 20, "dropReps": 6,
                                                                       "dropKg": 10}])
    assert [(entry.reps, entry.weightKg, entry.dropReps, entry.dropKg) for entry in sets] == [
        (8, 40.0, None, None), (6, 20.0, 6, 10.0)]
