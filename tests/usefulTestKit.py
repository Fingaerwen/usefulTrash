"""Shared helpers for the tests: valid example rows for every table and a clock the tests control.

Not a test file itself (pytest only collects test*.py). Importable because pyproject.toml puts tests/
on the path.
"""

import datetime as dt
import uuid
from typing import Any

from gym.tables import appTables, tablesByName
from usefulShared.tables import Table, dayRowId, newRowId

userA = str(uuid.UUID(int=1))
userB = str(uuid.UUID(int=2))
startOfTests = dt.datetime(2026, 10, 12, 7, 0, tzinfo=dt.UTC)


class FakeClock:
    """A clock that only moves when a test says so."""

    def __init__(self, now: dt.datetime = startOfTests):
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **delta: float) -> dt.datetime:
        self.now += dt.timedelta(**delta)
        return self.now


def exampleRow(tableName: str, userId: str = userA, updatedAt: dt.datetime = startOfTests, **columns: Any) -> dict:
    """A valid row for the table. Keyword arguments override columns. One-per-day rows get their real ID."""
    table = tablesByName[tableName]
    values: dict[str, Any] = {
        "plans": {"importedAt": updatedAt, "effectiveDate": dt.date(2026, 10, 12), "startStep": 0,
                  "planJson": {"planId": "pushPullLegs"}, "archived": False},
        "sessions": {"date": dt.date(2026, 10, 12), "planImportId": str(uuid.UUID(int=99)), "stepIndex": 0,
                     "finishedAt": None},
        "exerciseLogs": {"date": dt.date(2026, 10, 12), "exerciseId": "benchPress", "targetReps": 9,
                         "targetWeightKg": 82.5, "sets": [{"reps": 9, "weightKg": 82.5}], "minutes": None,
                         "skipped": False, "declinedSuggestion": False},
        "exerciseWeights": {"exerciseId": "benchPress", "weekday": 0, "weightKg": 82.5,
                            "fromDate": dt.date(2026, 10, 12)},
        "exerciseSteps": {"exerciseId": "benchPress", "incrementKg": 2.5, "fromDate": dt.date(2026, 10, 12)},
        "deloads": {"startDate": dt.date(2026, 10, 19)},
        "bodyWeight": {"date": dt.date(2026, 10, 16), "weightKg": 81.2},
        "dailySteps": {"date": dt.date(2026, 10, 12), "steps": 14000},
        "backups": {"madeAt": updatedAt, "fileName": "gymBackup.zip", "driveFileId": None, "sizeBytes": 2048,
                    "schemaVersion": 1, "madeBy": "phone"},
    }[tableName]
    values.update(columns)
    row = {"userId": userId, "updatedAt": updatedAt, "deleted": False, "cloudUpdatedAt": None, **values}
    if "id" not in row:
        row["id"] = (dayRowId(table, userId, **{name: row[name] for name in table.dayKey}) if table.dayKey
                     else newRowId())
    return {name: row[name] for name in table.columnNames}


def everyTable() -> tuple[Table, ...]:
    return appTables
