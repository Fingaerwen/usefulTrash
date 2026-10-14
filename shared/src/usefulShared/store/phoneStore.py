"""The phone's database (plan 14, 14b, 14c; CS1.1).

Your rows live in the same tables as in the cloud, plus three phone-only tables: `outbox` (changes
waiting to be sent), `syncState` (how far fetching has got) and `meta` (whose data this is). Every
edit goes into its table and the outbox in one transaction, so a saved change can't be lost before
it's sent. The store runs on the app's main loop only, so it needs no locks (3b). Not encrypted: gym
data isn't sensitive (T1.1); the sign-in session is kept elsewhere, encrypted.

Edit times and cloud stamps are kept as fixed-width UTC text, so comparing the text compares the times.
"""

import contextlib
import datetime as dt
import os
import shutil
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from usefulShared.tables import Table, editTime, fromLocal, momentText, toLocal

Clock = Callable[[], dt.datetime]


class PhoneDatabaseError(Exception):
    """The phone's database couldn't be opened or upgraded. The message says why, without row values."""


@dataclass(frozen=True, slots=True)
class Waiting:
    """What the outbox holds: for "N waiting" (SC1.1), the 3-day banner (G9.2b) and the Problems page."""

    count: int  # changes not sent yet, refused ones included
    oldestQueuedAt: dt.datetime | None  # when the oldest of them was made
    refused: tuple[tuple[str, str, str], ...]  # (table, row id, the cloud's reason) for each refused change


def runPhoneSteps(path: str, steps: Sequence[Sequence[str]]) -> int:
    """Brings the database file at `path` up to date (14c) and returns how many steps ran.

    Steps already run are skipped: the file's user_version counts them. Before running any step on an
    existing database the file is copied; the steps run in one transaction, and if anything fails the
    copy is put back, so nothing is lost.
    """
    existed = os.path.exists(path) and os.path.getsize(path) > 0
    database = sqlite3.connect(path, isolation_level=None)
    try:
        done = database.execute("pragma user_version").fetchone()[0]
    except sqlite3.DatabaseError as problem:
        raise PhoneDatabaseError(f"The phone's database can't be read: {problem}") from None
    finally:
        database.close()
    if done > len(steps):
        raise PhoneDatabaseError("The phone's database is from a newer version of the app. Update the app.")
    if done == len(steps):
        return 0

    copyPath = path + ".beforeUpgrade"
    if existed:
        shutil.copyfile(path, copyPath)
    database = sqlite3.connect(path, isolation_level=None)
    number = done
    try:
        database.execute("begin immediate")
        for number in range(done + 1, len(steps) + 1):
            for statement in steps[number - 1]:
                database.execute(statement)
        database.execute(f"pragma user_version = {len(steps)}")
        database.execute("commit")
    except Exception as problem:
        if database.in_transaction:
            database.execute("rollback")
        database.close()
        if existed:
            shutil.copyfile(copyPath, path)  # the rollback should have done it; the copy makes sure
        raise PhoneDatabaseError(f"Upgrading the phone's database failed at step {number}: {problem}") from None
    database.close()
    if existed:
        os.remove(copyPath)
    return len(steps) - done


class PhoneStore:
    """The phone's database: reading rows, saving edits, and what sync needs (outbox, fetch cursors)."""

    def __init__(self, path: str, tables: Sequence[Table], clock: Clock):
        self.tables = {table.name: table for table in tables}
        self.clock = clock
        self._db = sqlite3.connect(path, isolation_level=None)  # transactions are started explicitly
        self._db.execute("pragma synchronous = full")  # a saved edit survives the phone switching off

    def close(self) -> None:
        self._db.close()

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """All or nothing: everything inside is saved together, or not at all."""
        self._db.execute("begin immediate")
        try:
            yield self._db
            self._db.execute("commit")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("rollback")
            raise

    # --- Reading -----------------------------------------------------------------------------

    def rows(self, tableName: str) -> list[dict[str, Any]]:
        """Every row of a table, deleted ones included (the rules leave those out)."""
        table = self.tables[tableName]
        cursor = self._db.execute(f'select {_columnList(table)} from "{table.name}" order by "id"')
        return [fromLocal(table, values) for values in cursor]

    def row(self, tableName: str, rowId: str) -> dict[str, Any] | None:
        table = self.tables[tableName]
        values = self._db.execute(f'select {_columnList(table)} from "{table.name}" where "id" = ?', (rowId,)).fetchone()
        return fromLocal(table, values) if values else None

    # --- Saving an edit (the one write path, CS1.1) ------------------------------------------

    def save(self, tableName: str, row: dict[str, Any]) -> dict[str, Any]:
        """Saves an edit and queues it for sending, in one transaction. Returns the row as saved.

        The edit time is stamped here: now, or just after the version it replaces if the clock is
        behind that, so the edit always wins over what it was made from (F11.1). The cloud's stamp is
        kept from the stored version. Raises ValueError for a malformed row or another account's row.
        """
        table = self.tables[tableName]
        owner = self.owner()
        if owner is not None and row.get("userId") != owner:
            raise ValueError("this phone's database holds another account's data")
        existing = self.row(tableName, row["id"])
        if existing is not None and existing["userId"] != row["userId"]:
            raise ValueError(f"{tableName}: a row's owner never changes")
        saved = dict(row)
        saved["updatedAt"] = editTime(self.clock(), existing["updatedAt"] if existing else None)
        saved["cloudUpdatedAt"] = existing["cloudUpdatedAt"] if existing else None
        values = toLocal(table, saved)  # checks every column first
        with self._transaction() as db:
            db.execute(_replaceSql(table), values)
            db.execute(
                'insert into "outbox" ("tableName", "rowId", "updatedAt", "queuedAt") values (?, ?, ?, ?) '
                'on conflict ("tableName", "rowId") do update set "updatedAt" = excluded."updatedAt", '
                '"refusedReason" = null',
                (tableName, saved["id"], momentText(saved["updatedAt"]), momentText(self.clock())),
            )
        return saved

    # --- The outbox (sending) ----------------------------------------------------------------

    def waiting(self) -> Waiting:
        count, oldest = self._db.execute('select count(*), min("queuedAt") from "outbox"').fetchone()
        refused = self._db.execute(
            'select "tableName", "rowId", "refusedReason" from "outbox" where "refusedReason" is not null '
            'order by "queuedAt"').fetchall()
        return Waiting(count, dt.datetime.fromisoformat(oldest) if oldest else None, tuple(map(tuple, refused)))

    def changesToSend(self, limit: int) -> list[tuple[str, dict[str, Any]]]:
        """The oldest changes waiting to be sent, as (table, row as it is now), refused ones left out."""
        entries = self._db.execute(
            'select "tableName", "rowId" from "outbox" where "refusedReason" is null '
            'order by "queuedAt", "tableName", "rowId" limit ?', (limit,)).fetchall()
        changes = []
        for tableName, rowId in entries:
            row = self.row(tableName, rowId) if tableName in self.tables else None
            if row is None:  # can't happen through save(); an entry without its row has nothing to send
                with self._transaction() as db:
                    db.execute('delete from "outbox" where "tableName" = ? and "rowId" = ?', (tableName, rowId))
                continue
            changes.append((tableName, row))
        return changes

    def markSent(self, tableName: str, sent: Sequence[tuple[str, dt.datetime]]) -> None:
        """The cloud has these (row id, edit time) versions. Each leaves the outbox only if the row
        hasn't been edited again since (14b); otherwise the newer edit still waits."""
        with self._transaction() as db:
            db.executemany('delete from "outbox" where "tableName" = ? and "rowId" = ? and "updatedAt" = ?',
                           [(tableName, rowId, momentText(updatedAt)) for rowId, updatedAt in sent])

    def markRefused(self, tableName: str, rowId: str, updatedAt: dt.datetime, reason: str) -> None:
        """The cloud refused this version of the row; it isn't sent again until it's edited or retried."""
        with self._transaction() as db:
            db.execute('update "outbox" set "refusedReason" = ? where "tableName" = ? and "rowId" = ? '
                       'and "updatedAt" = ?', (reason[:500], tableName, rowId, momentText(updatedAt)))

    def sendRefusedAgain(self) -> int:
        """Problems page: try the refused changes again (say, after fixing the phone's clock)."""
        with self._transaction() as db:
            return db.execute('update "outbox" set "refusedReason" = null where "refusedReason" is not null').rowcount

    # --- Fetching ----------------------------------------------------------------------------

    def fetchCursor(self, tableName: str) -> dt.datetime | None:
        """The newest cloud stamp fetched so far in a table; None before the first download."""
        found = self._db.execute('select "cloudUpdatedAt" from "syncState" where "tableName" = ?',
                                 (tableName,)).fetchone()
        return dt.datetime.fromisoformat(found[0]) if found else None

    def applyFetched(self, tableName: str, rows: Sequence[dict[str, Any]], cursor: dt.datetime) -> int:
        """Takes in rows fetched from the cloud and moves the table's fetch cursor, in one transaction.
        Returns how many rows changed.

        A fetched row replaces the phone's only if it's newer, so the same change arriving twice is
        harmless (14b). A waiting edit that's older than the cloud's version has lost (the newest edit
        wins) and leaves the outbox; one the cloud already has (same edit time) leaves it too.
        """
        table = self.tables[tableName]
        owner = self.owner()
        changed = 0
        with self._transaction() as db:
            for row in rows:
                if owner is not None and row["userId"] != owner:
                    continue  # row-level security makes this impossible; never mix accounts anyway
                existing = self.row(tableName, row["id"])
                editText = momentText(row["updatedAt"])
                if existing is None or row["updatedAt"] > existing["updatedAt"]:
                    db.execute(_replaceSql(table), toLocal(table, row))
                    db.execute('delete from "outbox" where "tableName" = ? and "rowId" = ? and "updatedAt" <= ?',
                               (tableName, row["id"], editText))
                    changed += 1
                elif row["updatedAt"] == existing["updatedAt"]:
                    if existing["cloudUpdatedAt"] != row["cloudUpdatedAt"]:
                        db.execute(f'update "{tableName}" set "cloudUpdatedAt" = ? where "id" = ?',
                                   (momentText(row["cloudUpdatedAt"]), row["id"]))
                    db.execute('delete from "outbox" where "tableName" = ? and "rowId" = ? and "updatedAt" = ?',
                               (tableName, row["id"], editText))
            db.execute(
                'insert into "syncState" ("tableName", "cloudUpdatedAt") values (?, ?) on conflict ("tableName") '
                'do update set "cloudUpdatedAt" = max("cloudUpdatedAt", excluded."cloudUpdatedAt")',
                (tableName, momentText(cursor)),
            )
        return changed

    # --- Whose data, and other small facts ---------------------------------------------------

    def meta(self, key: str) -> str | None:
        found = self._db.execute('select "value" from "meta" where "key" = ?', (key,)).fetchone()
        return found[0] if found else None

    def setMeta(self, key: str, value: str) -> None:
        with self._transaction() as db:
            db.execute('insert into "meta" ("key", "value") values (?, ?) '
                       'on conflict ("key") do update set "value" = excluded."value"', (key, value))

    def owner(self) -> str | None:
        """The account whose data this database holds; None until the first sign-in."""
        return self.meta("userId")

    def claimFor(self, userId: str) -> bool:
        """Records whose data this is at sign-in. If a different account signs in, everything is cleared
        first (14b), so two accounts' data never mix. Returns True if data was cleared."""
        owner = self.owner()
        if owner == userId:
            return False
        with self._transaction() as db:
            if owner is not None:
                for tableName in self.tables:
                    db.execute(f'delete from "{tableName}"')
                db.execute('delete from "outbox"')
                db.execute('delete from "syncState"')
                db.execute('delete from "meta"')
            db.execute('insert into "meta" ("key", "value") values (?, ?)', ("userId", userId))
        return owner is not None


def _columnList(table: Table) -> str:
    return ", ".join(f'"{name}"' for name in table.columnNames)


def _replaceSql(table: Table) -> str:
    """Writes a whole row, replacing the one with the same id."""
    placeholders = ", ".join("?" for _ in table.columns)
    return f'insert or replace into "{table.name}" ({_columnList(table)}) values ({placeholders})'
