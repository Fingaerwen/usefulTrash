"""Tests for tools/restoreBackup.py without a database: what it refuses, and how it writes values. The
restore itself runs on a throwaway local Postgres in tests/cloud/testCloudScripts.py."""

import datetime as dt
import io
import json
import zipfile

import pytest
import restoreBackup
from usefulTestKit import exampleRow, userA

from gym.tables import appSchema, appTables
from usefulShared.backup.backupFile import makeBackupZip

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
    with pytest.raises(ValueError, match="isn't a Gym Tracker backup"):
        restoreBackup.restoreSql(buffer.getvalue())


def testTheCommandLine(tmp_path, capsys):
    path = tmp_path / "backup.zip"
    path.write_bytes(backup())
    assert restoreBackup.main([str(path)]) == 0
    assert capsys.readouterr().out.startswith("-- Restore of a Gym Tracker backup made 2026-10-24")
    assert restoreBackup.main([]) == 2 and restoreBackup.main([str(path), "--everything"]) == 2
    assert restoreBackup.main([str(tmp_path / "missing.zip")]) == 1
