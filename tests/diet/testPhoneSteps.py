"""Ambrosia's phone database steps (ambrosia/phoneSteps.py, plan 14c): one per cloud upgrade, building exactly the
tables in ambrosia/tables.py, and saving and reading every one of them."""

import sqlite3

from usefulTestKit import FakeClock, exampleRow, userA

from ambrosia.phoneSteps import phoneSteps
from ambrosia.tables import appSchema, appTables
from usefulShared.store.phoneStore import PhoneStore, runPhoneSteps


def testOneStepPerCloudUpgrade():
    assert len(phoneSteps) == appSchema


def testStepsBuildExactlyTheAppTables(tmp_path):
    path = str(tmp_path / "ambrosia.sqlite3")
    assert runPhoneSteps(path, phoneSteps) == 3
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


def testEveryTableSavesAndReadsItsRows(tmp_path):
    path = str(tmp_path / "ambrosia.sqlite3")
    runPhoneSteps(path, phoneSteps)
    store = PhoneStore(path, appTables, FakeClock())
    store.claimFor(userA)
    for table in appTables:
        saved = store.save(table.name, exampleRow(table.name))
        assert store.row(table.name, saved["id"]) == saved
    assert store.waiting().count == len(appTables)
