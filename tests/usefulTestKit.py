"""Shared helpers for the tests: valid example rows for every table and a clock the tests control.

Not a test file itself (pytest only collects test*.py). Importable because pyproject.toml puts tests/
on the path.
"""

import datetime as dt
import uuid
from typing import Any

from ambrosia.tables import tablesByName as dietTablesByName
from gym.tables import appTables, tablesByName as gymTablesByName
from usefulShared.tables import Table, dayRowId, newRowId

tablesByName = {**gymTablesByName, **dietTablesByName}  # every table of both apps (the shared ones are the same)

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
        "bodyWeight": {"date": dt.date(2026, 10, 16), "weightKg": 81.2, "weighedAt": None},
        "dailySteps": {"date": dt.date(2026, 10, 12), "steps": 14000},
        "backups": {"madeAt": updatedAt, "fileName": "gymBackup.zip", "driveFileId": None, "sizeBytes": 2048,
                    "schemaVersion": 1, "madeBy": "phone"},
        # Ambrosia's (apps/diet/docs/plan.md 4e)
        "foods": {"source": "openFoodFacts", "barcode": "3017620422003", "usdaId": None, "name": "Nutella",
                  "brand": "Ferrero", "unit": "g", "kcal": 539.0, "proteinG": 6.3, "fatG": 30.9, "carbsG": 57.5,
                  "servingG": 15.0, "packG": 400.0},
        "foodLogs": {"date": dt.date(2026, 10, 26), "meal": "breakfast", "loggedAt": updatedAt,
                     "foodId": str(uuid.UUID(int=77)), "portion": "servings", "portionCount": 2.0, "grams": 30.0,
                     "name": "Nutella", "brand": "Ferrero", "unit": "g", "kcal": 539.0, "proteinG": 6.3, "fatG": 30.9,
                     "carbsG": 57.5},
        "water": {"date": dt.date(2026, 10, 26), "ml": 1500},
        "dietTargets": {"importedAt": updatedAt, "effectiveDate": dt.date(2026, 10, 26),
                        "targetsJson": {"format": "ambrosiaTargets", "name": "Bulk from 26 Oct"}},
        "targetChanges": {"checkDate": dt.date(2026, 12, 6), "fromDate": dt.date(2026, 12, 6),
                          "targetsImportId": str(uuid.UUID(int=88)), "reason": "bigMissLow", "kcalChange": 250,
                          "macro": "carbs", "macroChangeG": 63, "blockAvgKg": 81.13, "blockWeighIns": 2,
                          "comparedStart": dt.date(2026, 10, 26), "comparedAvgKg": 81.25, "comparedWeighIns": 2,
                          "rateKgPerWeek": None},
        "dietBackups": {"madeAt": updatedAt, "fileName": "Ambrosia-backup.zip", "driveFileId": None,
                        "sizeBytes": 1024, "schemaVersion": 3, "madeBy": "phone"},
    }[tableName]
    values.update(columns)
    row = {"userId": userId, "updatedAt": updatedAt, "deleted": False, "cloudUpdatedAt": None, **values}
    if "id" not in row:
        row["id"] = (dayRowId(table, userId, **{name: row[name] for name in table.dayKey}) if table.dayKey
                     else newRowId())
    return {name: row[name] for name in table.columnNames}


def everyTable() -> tuple[Table, ...]:
    return appTables
