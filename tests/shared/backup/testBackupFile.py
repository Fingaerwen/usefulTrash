"""Tests for the backup file and the history file (F14.1, BK1.2): what goes in, and that the history file
never loses a row."""

import datetime as dt
import io
import json
import zipfile

from usefulTestKit import exampleRow, userA

from gym.tables import appSchema, appTables
from usefulShared.backup.backupFile import makeBackupZip, mergeHistory, readBackupZip

moment = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.UTC)
later = moment + dt.timedelta(days=30)


def testABackupHoldsEveryTableAndItsManifest():
    rows = {"bodyWeight": [exampleRow("bodyWeight", userId=userA)]}
    manifest, tables = readBackupZip(makeBackupZip(rows, appTables, appSchema, moment, "phone", {"sets.csv": "x\n"}))
    assert manifest["schemaVersion"] == appSchema and manifest["rows"]["bodyWeight"] == 1
    assert set(tables) == {table.name for table in appTables} and tables["bodyWeight"][0]["weightKg"] == "81.2"


def testTheHistoryFileKeepsEveryRowEverBackedUp():
    """A row gone from the cloud since stays. A row in both keeps its newer edit."""
    gone = exampleRow("dailySteps", userId=userA, date=dt.date(2026, 10, 1), steps=5000)
    weighIn = exampleRow("bodyWeight", userId=userA, updatedAt=moment, weightKg=81.2)
    first = mergeHistory(None, {"dailySteps": [gone], "bodyWeight": [weighIn]}, appTables, appSchema, moment, "phone")
    edited = dict(weighIn, updatedAt=later, weightKg=80.4)
    second = mergeHistory(first, {"bodyWeight": [edited]}, appTables, appSchema, later, "phone", {"diary.csv": "d\n"})
    manifest, tables = readBackupZip(second)
    assert manifest["kind"] == "history"
    assert [row["steps"] for row in tables["dailySteps"]] == ["5000"]  # no longer in the cloud, still here
    assert [row["weightKg"] for row in tables["bodyWeight"]] == ["80.4"]  # the newer edit
    assert zipfile.ZipFile(io.BytesIO(second)).read("diary.csv") == b"d\n"
    older = mergeHistory(second, {"bodyWeight": [weighIn]}, appTables, appSchema, later, "phone")
    assert readBackupZip(older)[1]["bodyWeight"][0]["weightKg"] == "80.4"  # an older copy never wins


def testATableOnlyAnEarlierVersionKnewStays():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"app": "usefulTrash", "schemaVersion": 1, "rows": {"oldTable": 1}}))
        archive.writestr("oldTable.csv", "id,value\nrow1,kept\n")
    merged = mergeHistory(buffer.getvalue(), {}, appTables, appSchema, moment, "phone")
    assert readBackupZip(merged)[1]["oldTable"] == [{"id": "row1", "value": "kept"}]
