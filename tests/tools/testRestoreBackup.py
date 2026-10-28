"""Tests for tools/restoreBackup.py without a database: what it refuses, and how it writes values. The
restore itself runs on a throwaway local Postgres in tests/cloud/testCloudScripts.py."""

import datetime as dt
import io
import json
import zipfile

import pytest
import restoreBackup
from usefulTestKit import exampleRow, userA

from ambrosia.tables import dietTables
from gym.tables import appSchema, appTables
from usefulShared.backup.backupFile import makeBackupZip, mergeHistory

moment = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.UTC)


def backup(schemaVersion=appSchema) -> bytes:
    return makeBackupZip({"bodyWeight": [exampleRow("bodyWeight", userId=userA)]}, appTables, schemaVersion, moment,
                         "phone")


def testValuesBecomeTypedSqlAndEmptyCellsNull():
    assert restoreBackup.literal("Tom's", "text") == "'Tom''s'::text"
    assert restoreBackup.literal("", "numeric(5,2)") == "null"


def testOnlyTheBackupWinsOptionStampsTheRestoresTime():
    assert "now()" not in restoreBackup.restoreSql(backup())
    assert "now()" in restoreBackup.restoreSql(backup(), backupWins=True)


def testABackupFromANewerDataStructureIsRefused():
    with pytest.raises(ValueError, match="update the repo first"):
        restoreBackup.restoreSql(backup(appSchema + 1))


def testSomethingElsesZipIsRefused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"app": "other", "schemaVersion": 1, "rows": {}}))
    with pytest.raises(ValueError, match="isn't a usefulTrash backup"):
        restoreBackup.restoreSql(buffer.getvalue())


def testAnAmbrosiaBackupRestoresAmbrosiasOwnTables():
    """AM5.6: its manifest names Ambrosia, so its six tables are the ones restored."""
    rows = {table.name: [exampleRow(table.name, userId=userA)] for table in dietTables}
    sql = restoreBackup.restoreSql(makeBackupZip(rows, dietTables, 3, moment, "phone", appName="Ambrosia"))
    assert sql.startswith("-- Restore of an Ambrosia backup made 2026-10-24")
    assert all(f'insert into public."{table.name}"' in sql for table in dietTables)
    assert "done: 6 rows from the backup" in sql


def testABackupFromAnAppThisCodeDoesntKnowIsRefused():
    content = makeBackupZip({}, (), 3, moment, "phone", appName="Hermes")
    with pytest.raises(ValueError, match="from Hermes, which this code doesn't know"):
        restoreBackup.restoreSql(content)


def testTheCommandLine(tmp_path, capsys):
    path = tmp_path / "backup.zip"
    path.write_bytes(backup())
    assert restoreBackup.main([str(path)]) == 0
    assert capsys.readouterr().out.startswith("-- Restore of a Gym Tracker backup made 2026-10-24")
    assert restoreBackup.main([]) == 2 and restoreBackup.main([str(path), "--everything"]) == 2
    assert restoreBackup.main([str(tmp_path / "missing.zip")]) == 1


def testTheHistoryFileRestoresTheSameWay():
    """BK1.2: GymTracker-history.zip is a backup too. Its readable files are left aside."""
    history = mergeHistory(backup(), {"bodyWeight": [exampleRow("bodyWeight", userId=userA, weightKg=80.0)]},
                           appTables, appSchema, moment, "phone", {"sets.csv": "date\n"})
    sql = restoreBackup.restoreSql(history)
    assert "select 'done: 1 rows from the backup'" in sql and "80.0" in sql
