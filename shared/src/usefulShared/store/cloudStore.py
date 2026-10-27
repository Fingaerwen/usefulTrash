"""The PC view's store (plan 3b and 14b, CS1.1): every row loaded from the cloud into memory at sign-in,
edits written straight to the cloud, and changes made elsewhere fetched every minute. Nothing is kept in
the browser. If a write fails, nothing changes on screen and the error says why.

Same rules as the phone: the edit time is stamped here (now, or just after the version it replaces),
and the cloud's trigger keeps whichever edit is newest.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.sync.fetchChanges import fetchChanges
from usefulShared.sync.syncEngine import Session, SyncCloud
from usefulShared.tables import Table, checkRow, editTime, toCloud


class VersionMismatch(Exception):
    """The cloud and this app don't fit together (UP1.1). The message says which one needs updating."""


class CloudStore:
    """Rows in memory, the cloud behind them."""

    def __init__(self, cloud: SyncCloud, session: Session, tables: Sequence[Table], appSchema: int,
                 clock: Callable[[], dt.datetime]):
        self.cloud = cloud
        self.session = session
        self.tables = {table.name: table for table in tables}
        self.appSchema = appSchema
        self.clock = clock
        self._rows: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in self.tables}
        self._cursors: dict[str, dt.datetime | None] = {name: None for name in self.tables}

    def rows(self, tableName: str) -> list[dict[str, Any]]:
        return list(self._rows[tableName].values())

    def clear(self) -> None:
        """Signing out forgets everything (the PC view keeps nothing)."""
        self._rows = {name: {} for name in self.tables}
        self._cursors = {name: None for name in self.tables}

    async def checkVersions(self, accessToken: str) -> None:
        """The same check as the phone's sync (UP1.1): minAppSchema <= this app <= the cloud."""
        schemaVersion, minAppSchema = await self.cloud.readCloudInfo(accessToken)
        if self.appSchema < minAppSchema:
            raise VersionMismatch("The cloud needs a newer version of the PC view. Reload the page to get it.")
        if self.appSchema > schemaVersion:
            raise VersionMismatch(f"This PC view needs cloud upgrade {self.appSchema:03d}; the cloud is at "
                                  f"{schemaVersion:03d}.")

    async def fetch(self, onProgress: Callable[[int], None] | None = None) -> int:
        """Fetches what changed since last time (everything the first time). Returns rows fetched."""
        accessToken = await self.session.freshAccessToken()
        await self.checkVersions(accessToken)
        fetched = 0
        for table in self.tables.values():
            def apply(rows: list[dict[str, Any]], cursor: dt.datetime, name: str = table.name) -> None:
                nonlocal fetched
                stored = self._rows[name]
                for row in rows:
                    current = stored.get(row["id"])
                    if current is None or row["updatedAt"] >= current["updatedAt"]:
                        stored[row["id"]] = row
                self._cursors[name] = cursor
                fetched += len(rows)
                if onProgress is not None:
                    onProgress(fetched)

            await fetchChanges(self.cloud, table, self._cursors[table.name], accessToken, apply)
        return fetched

    async def saveMany(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Stamps and checks the edits, then writes them to the cloud, one request per table. Memory
        changes only after the cloud has them. Raises CloudError (nothing changed) or ValueError."""
        now = self.clock()
        prepared: dict[str, list[dict[str, Any]]] = {}
        for tableName, row in edits:
            table = self.tables[tableName]
            existing = self._rows[tableName].get(row["id"])
            saved = dict(row, updatedAt=editTime(now, existing["updatedAt"] if existing else None),
                         cloudUpdatedAt=existing["cloudUpdatedAt"] if existing else None)
            checkRow(table, saved)
            prepared.setdefault(tableName, []).append(saved)
        accessToken = await self.session.freshAccessToken()
        for tableName, rows in prepared.items():
            await self.cloud.upsertRows(tableName, [toCloud(self.tables[tableName], row) for row in rows], accessToken)
        for tableName, rows in prepared.items():
            for row in rows:
                self._rows[tableName][row["id"]] = row
        return [row for rows in prepared.values() for row in rows]


def describeCloudError(problem: CloudError) -> str:
    """A failed write in plain words, for the PC view's notice."""
    if problem.isTemporary:
        return "No connection to the cloud right now. Nothing was changed. Try again in a moment."
    if problem.errorCode == "P0001" and problem.message.startswith("futureEdit"):
        return "The cloud refused this: your PC's clock seems to be ahead. Nothing was changed."
    return f"The cloud refused this ({problem.errorCode}). Nothing was changed."
