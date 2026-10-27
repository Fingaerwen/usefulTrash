"""Sync between the phone's database and the cloud (plan 14b, SY2.1, SY2.2, UP1.1).

A round renews the session if needed, checks versions, sends the outbox, then fetches what changed
elsewhere. Rounds never overlap. No internet just ends a round early: everything is already saved on
the phone, and the next round tries again (at the latest a minute later, SY2.2). A change the cloud
refuses is set aside with the cloud's reason (shown on the Problems page, 12d) instead of blocking
the changes behind it.
"""

import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.sync.fetchChanges import fetchChanges
from usefulShared.tables import Table, momentText, toCloud

if TYPE_CHECKING:  # only for type hints: the PC view imports this module, and its browser Python has no SQLite
    from usefulShared.store.phoneStore import PhoneStore

sendBatchSize = 200  # rows per request when sending
maxBatchesPerRound = 50  # a round never runs forever, even if rows keep changing while it sends


class Session(Protocol):
    """What sync needs from the sign-in (usefulShared.signIn.sessionKeeper.SessionKeeper)."""

    async def freshAccessToken(self) -> str: ...

    async def renewNow(self) -> None: ...


class SyncCloud(Protocol):
    """The cloud calls sync makes (SupabaseApi has them, tests use a stand-in)."""

    async def readCloudInfo(self, accessToken: str) -> tuple[int, int]: ...

    async def upsertRows(self, table: str, rows: Sequence[dict], accessToken: str) -> None: ...

    async def fetchRows(self, table: str, columns: Sequence[str], since: str, after: tuple[str, str] | None,
                        limit: int, accessToken: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    """How a round went, for the app's status and the Problems page (12d)."""

    status: str  # done, offline, signedOut, appTooOld, cloudTooOld, failed or busy (a round was running)
    sent: int = 0
    fetched: int = 0
    problem: str = ""  # the cloud's code and message when something failed. Never row values or tokens


class SyncEngine:
    """Runs sync rounds for one phone database."""

    def __init__(self, store: "PhoneStore", cloud: SyncCloud, session: Session, tables: Sequence[Table],
                 appSchema: int, clock: Callable[[], dt.datetime]):
        self.store = store
        self.cloud = cloud
        self.session = session
        self.tables = {table.name: table for table in tables}
        self.appSchema = appSchema
        self.clock = clock
        self._running = False
        self._sent = 0
        self._fetched = 0

    async def runRound(self, onProgress: Callable[[int], None] | None = None) -> SyncOutcome:
        """One sync round. onProgress gets the number of rows fetched so far (first download, 14b)."""
        if self._running:
            return SyncOutcome("busy")
        self._running = True
        self._sent = self._fetched = 0
        try:
            try:
                return await self._round(onProgress)
            except CloudError as problem:
                if not problem.isSessionProblem or problem.errorCode == "notSignedIn":
                    raise
                # The cloud refused the access token although it looked fresh (say the phone's clock is
                # off): renew the session once and try again.
                await self.session.renewNow()
                return await self._round(onProgress)
        except CloudError as problem:
            return self._outcomeFor(problem)
        finally:
            self._running = False

    async def _round(self, onProgress: Callable[[int], None] | None) -> SyncOutcome:
        accessToken = await self.session.freshAccessToken()
        # Version check (UP1.1): sync only if minAppSchema <= this app's schema <= the cloud's.
        schemaVersion, minAppSchema = await self.cloud.readCloudInfo(accessToken)
        if self.appSchema < minAppSchema:
            return SyncOutcome("appTooOld", problem=f"The cloud needs a newer app (schema {minAppSchema} or later; "
                                                    f"this app is {self.appSchema}). Update the app.")
        if self.appSchema > schemaVersion:
            return SyncOutcome("cloudTooOld", problem=f"This app needs cloud upgrade {self.appSchema:03d}; the cloud "
                                                      f"is at {schemaVersion:03d}.")
        await self._send(accessToken)
        await self._fetch(accessToken, onProgress)
        self.store.setMeta("lastSyncAt", momentText(self.clock()))
        return SyncOutcome("done", self._sent, self._fetched)

    def _outcomeFor(self, problem: CloudError) -> SyncOutcome:
        described = f"{problem.statusCode} {problem.errorCode}: {problem.message}"
        if problem.errorCode == "notSignedIn":
            return SyncOutcome("signedOut", self._sent, self._fetched)
        status = "offline" if problem.isTemporary else "failed"
        return SyncOutcome(status, self._sent, self._fetched, described)

    # --- Sending -----------------------------------------------------------------------------

    async def _send(self, accessToken: str) -> None:
        """Sends the outbox in batches, oldest first. Each table's rows go in one request."""
        for _ in range(maxBatchesPerRound):
            changes = self.store.changesToSend(sendBatchSize)
            if not changes:
                return
            for tableName, rows in _byTable(changes).items():
                await self._sendBatch(self.tables[tableName], rows, accessToken)

    async def _sendBatch(self, table: Table, rows: list[dict[str, Any]], accessToken: str) -> None:
        try:
            await self.cloud.upsertRows(table.name, [toCloud(table, row) for row in rows], accessToken)
        except (CloudError, ValueError) as problem:
            if isinstance(problem, CloudError) and (problem.isTemporary or problem.isSessionProblem):
                raise  # the round ends. Everything stays queued
            # The cloud refused the batch (all or nothing): send one by one to find which rows it refuses.
            for row in rows:
                await self._sendOne(table, row, accessToken)
            return
        self.store.markSent(table.name, [(row["id"], row["updatedAt"]) for row in rows])
        self._sent += len(rows)

    async def _sendOne(self, table: Table, row: dict[str, Any], accessToken: str) -> None:
        try:
            await self.cloud.upsertRows(table.name, [toCloud(table, row)], accessToken)
        except CloudError as problem:
            if problem.isTemporary or problem.isSessionProblem:
                raise
            self.store.markRefused(table.name, row["id"], row["updatedAt"], f"{problem.errorCode}: {problem.message}")
            return
        except ValueError as problem:  # the row can't be put into the cloud's form (can't happen via save)
            self.store.markRefused(table.name, row["id"], row["updatedAt"], f"badRow: {problem}")
            return
        self.store.markSent(table.name, [(row["id"], row["updatedAt"])])
        self._sent += 1

    # --- Fetching ----------------------------------------------------------------------------

    async def _fetch(self, accessToken: str, onProgress: Callable[[int], None] | None) -> None:
        for table in self.tables.values():
            def apply(rows: list[dict[str, Any]], cursor: dt.datetime, tableName: str = table.name) -> None:
                self.store.applyFetched(tableName, rows, cursor)
                self._fetched += len(rows)
                if onProgress is not None:
                    onProgress(self._fetched)

            await fetchChanges(self.cloud, table, self.store.fetchCursor(table.name), accessToken, apply)


class SyncLoop:
    """Decides when rounds run (14b): at start, a few seconds after each saved change, every minute
    while the app is open, and when it comes back on screen. Each outcome goes to onOutcome."""

    def __init__(self, engine: SyncEngine, onOutcome: Callable[[SyncOutcome], None], everySec: float = 60,
                 afterChangeSec: float = 3):
        self.engine = engine
        self.onOutcome = onOutcome
        self.everySec = everySec
        self.afterChangeSec = afterChangeSec
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._changeTimer: asyncio.TimerHandle | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    def stop(self) -> None:
        if self._changeTimer is not None:
            self._changeTimer.cancel()
            self._changeTimer = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def changed(self) -> None:
        """A change was saved: sync a few seconds from now (several quick changes share one round)."""
        if self._changeTimer is None:
            self._changeTimer = asyncio.get_running_loop().call_later(self.afterChangeSec, self._changeTimerRang)

    def resumed(self) -> None:
        """The app is back on screen: sync now."""
        self._wake.set()

    def _changeTimerRang(self) -> None:
        self._changeTimer = None
        self._wake.set()

    async def _run(self) -> None:
        while True:
            self._wake.clear()
            try:
                outcome = await self.engine.runRound()
            except Exception as problem:  # a bug must not stop sync for good: report it and carry on
                outcome = SyncOutcome("failed", problem=f"unexpected {type(problem).__name__}: {problem}"[:300])
            self.onOutcome(outcome)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.everySec)
            except TimeoutError:
                pass


def _byTable(changes: list[tuple[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Groups (table, row) pairs by table, keeping their order."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for tableName, row in changes:
        grouped.setdefault(tableName, []).append(row)
    return grouped
