"""Ambrosia's phone app (plan 3b, phone mode): the phone's database, sync and sign-in, like Talon's. Every button on
the phone ends up here or in appBase.py. The screens only read the model and call these methods.

Start-up: upgrade the phone's database if needed (14c), restore the saved session (T1.1), then the first download
if this phone has none yet (14b), then Today with sync running in the background. After the first sync of each
start, the automatic backup runs if it's due (AM5.6).
"""

import asyncio
import datetime as dt
import os
import sqlite3
from collections.abc import Callable, Sequence
from typing import Any

from ambrosia.appBase import AmbrosiaBase
from ambrosia.phoneSteps import phoneSteps
from ambrosia.tables import appSchema, appTables
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi
from usefulShared.platform.appLog import AppLog
from usefulShared.platform.problems import SyncFacts
from usefulShared.signIn.sessionKeeper import SessionKeeper
from usefulShared.signIn.signInFlow import signInWithGoogle
from usefulShared.store.phoneStore import PhoneDatabaseError, PhoneStore, Waiting, runPhoneSteps
from usefulShared.sync.syncEngine import SyncEngine, SyncLoop, SyncOutcome

databaseName = "ambrosia.sqlite3"
notSyncedAfter = dt.timedelta(days=3)  # the "Not synced" banner (G9.2b)
dismissedKey = "bulkCheckDismissed"  # the check day whose suggestion got Not now on this phone (4g)


class PhoneApp(AmbrosiaBase):
    """Phone mode: owns the database, the session and sync."""

    def __init__(self, config: dict[str, str], folder: str, services: Any, log: AppLog,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 localToday: Callable[[], dt.date] = dt.date.today, cloud: Any = None, drive: Any = None,
                 **sources: Any):
        super().__init__(config, services, log, clock, localToday, **sources)
        self.folder = folder
        self.injectedCloud = cloud  # None: the real Supabase project. Tests pass a stand-in
        self.drive = drive  # Google Drive, for the automatic backup (AM5.6). Tests pass a stand-in
        self.backupTask: asyncio.Task | None = None  # the backup runs beside the app, after a start's first sync
        self.store: PhoneStore | None = None
        self.cloud: Any = None
        self.engine: SyncEngine | None = None
        self.syncLoop: SyncLoop | None = None
        self.lastOutcome = SyncOutcome("none")

    # --- Start-up ----------------------------------------------------------------------------

    async def start(self) -> None:
        """Opens everything and decides the first screen."""
        if not self.hasCloudSettings():
            self._fail("This build has no cloud settings. Rebuild it with tools/buildRelease.py.")
            return
        path = os.path.join(self.folder, databaseName)
        try:
            ran = runPhoneSteps(path, phoneSteps)
            if ran:
                self.log.info("start", f"phone database upgraded ({ran} step(s))")
            self.store = PhoneStore(path, appTables, self.clock)
        except (PhoneDatabaseError, OSError, sqlite3.Error) as problem:
            self.log.problem("start", "The phone's database couldn't be opened.", str(problem))
            self._fail(f"The phone's database couldn't be opened: {problem}")
            return
        self.cloud = self.injectedCloud or SupabaseApi(self.config["supabaseUrl"], self.config["supabasePublishableKey"])
        self.session = SessionKeeper(self.cloud, self.services.secretStore)
        session = self.session
        self.log.knownSecrets = lambda: (session.session.get("access_token", ""),
                                         session.session.get("refresh_token", ""))
        self.engine = SyncEngine(self.store, self.cloud, self.session, appTables, appSchema, self.clock)
        self.syncLoop = SyncLoop(self.engine, self._onSyncOutcome)

        restored = await self.session.restore()
        if restored == "restored":
            await self._signedIn()
            return
        if restored in ("unreadable", "error"):
            self.log.problem("signIn", "The saved sign-in couldn't be read, so you need to sign in again.",
                             self.session.lastProblem)
            self.model.notice = "Please sign in again."
        self.model.screen = "signIn"

    async def _signedIn(self) -> None:
        """After sign-in or a restored session: make sure the database is this account's, download everything if
        this phone has nothing yet, then show Today and start syncing."""
        if self.store.claimFor(self.session.userId()):
            self.log.info("signIn", "a different account signed in, so this phone's data was cleared")
        self.startActions(self.session.userId())
        self.refresh()
        if self.store.meta("firstDownloadDone") is None:
            await self.firstDownload()
            return
        self.model.screen = "main"
        self.syncLoop.start()

    async def firstDownload(self) -> None:
        """Everything is fetched before Today shows, with a running count (14b). Needs the internet."""
        self.model.screen, self.model.busy, self.model.downloaded = "downloading", "Downloading your data…", 0

        def progress(count: int) -> None:
            self.model.downloaded = count

        outcome = await self.engine.runRound(progress)
        self.lastOutcome = outcome
        self.model.busy = ""
        if outcome.status != "done":
            self.log.problem("sync", "The first download didn't finish.", outcome.problem or outcome.status)
            self.model.notice = ("No internet: the first download needs it. Tap Try again when you're online."
                                 if outcome.status == "offline" else
                                 f"The first download didn't finish: {outcome.problem or outcome.status}")
            return
        self.store.setMeta("firstDownloadDone", self.clock().isoformat())
        self.log.info("sync", f"first download: {outcome.fetched} rows")
        self.refresh()
        self.model.screen = "main"
        self.syncLoop.start()

    # --- Signing in and out ------------------------------------------------------------------

    async def signIn(self) -> None:
        """Google's account picker → Supabase session (usefulShared.signIn.signInFlow), then this phone's data."""
        if self.model.busy:
            return
        self.model.busy, self.model.notice = "Signing in…", ""
        try:
            result = await signInWithGoogle(self.services.googleSignIn, self.cloud, self.config["googleWebClientId"],
                                            self.log)
        finally:
            self.model.busy = ""
        if result.session is None:
            self.model.notice = result.notice
            return
        if not await self.session.save(result.session):
            self.log.problem("signIn", "The sign-in couldn't be saved on the phone. You'll need to sign in again "
                                       "next time.", self.session.lastProblem)
        await self._signedIn()

    async def signOut(self) -> None:
        """Signs out on this phone. Changes not sent yet stay on the phone and go out at the next sign-in (14b)."""
        self.syncLoop.stop()
        try:
            await self.cloud.signOut(await self.session.freshAccessToken())
        except CloudError:
            pass  # offline: the session simply ends on this phone
        await self.session.forget()
        try:
            await self.services.googleSignIn.clearSignInState()
        except Exception as problem:  # the account picker just won't show next time. Nothing depends on it
            self.log.problem("signIn", "Google's chosen account couldn't be forgotten.", type(problem).__name__)
        waiting = self.store.waiting().count
        self.log.info("signIn", "signed out")
        self.model.notice = (f"Signed out. {waiting} change(s) not sent yet stay on this phone until you sign in "
                             "again." if waiting else "Signed out.")
        self.model.screen = "signIn"

    # --- Sync --------------------------------------------------------------------------------

    def _onSyncOutcome(self, outcome: SyncOutcome) -> None:
        """Each sync round's result: log what matters, update banners and the screens."""
        previous, self.lastOutcome = self.lastOutcome, outcome
        if outcome.status in ("failed", "appTooOld", "cloudTooOld") and outcome.problem != previous.problem:
            self.log.problem("sync", "Sync stopped.", outcome.problem)
        elif outcome.status == "offline" and previous.status != "offline":
            self.log.info("sync", "no internet, trying every minute", outcome.problem)
        if not self.session.isSignedIn():
            self.syncLoop.stop()
            self.model.notice = "You were signed out. Please sign in again."
            self.model.screen = "signIn"
            return
        self.refresh()
        if outcome.status == "done" and self.backupTask is None:  # once per start, with everything synced first
            self.backupTask = asyncio.get_running_loop().create_task(self.backUpIfDue())

    async def backUpIfDue(self) -> None:
        """The automatic backup (AM5.6). Built with the backups."""

    async def syncNow(self) -> SyncOutcome:
        """One sync round right away, handled like the background ones."""
        outcome = await self.engine.runRound()
        self._onSyncOutcome(outcome)
        return outcome

    def onResume(self) -> None:
        """Back on screen: sync now, and Today may be a new day."""
        if self.syncLoop is not None and self.model.screen == "main":
            self.syncLoop.resumed()
            self.refresh()

    def tryRefusedAgain(self) -> None:
        """Problems page: send the refused changes again (say, after fixing the clock)."""
        if self.store is not None and self.store.sendRefusedAgain():
            self.syncLoop.resumed()
        self.refresh()
        self.model.problems = self.problemsLines()

    # --- What appBase needs ------------------------------------------------------------------

    def rowsByTable(self) -> dict[str, list[dict[str, Any]]] | None:
        if self.store is None:
            return None
        return {table.name: self.store.rows(table.name) for table in appTables}

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Saves in one transaction, redraws, and syncs a few seconds later."""
        saved = self.store.saveMany(edits)
        self.refresh()
        self.syncLoop.changed()
        return saved

    def afterRefresh(self) -> None:
        waiting = self.store.waiting()
        self.model.waiting = waiting.count
        self.model.banners = self._banners(waiting)

    def _banners(self, waiting: Waiting) -> tuple[str, ...]:
        banners = []
        if self.lastOutcome.status == "appTooOld":
            banners.append("Update the app: the cloud needs a newer version. Your entries are kept until then.")
        elif self.lastOutcome.status == "cloudTooOld":
            banners.append(f"The cloud needs upgrade {appSchema:03d} before this app can sync.")
        if waiting.refused:
            banners.append("The cloud refused a change. See Problems in the menu.")
        if waiting.oldestQueuedAt is not None and self.clock() - waiting.oldestQueuedAt >= notSyncedAfter:
            banners.append("Not synced for 3 days. Check your internet, or see Problems in the menu.")
        return tuple(banners)

    def syncedToday(self) -> bool:
        lastSync = self.store.meta("lastSyncAt") if self.store is not None else None
        return lastSync is not None and dt.datetime.fromisoformat(lastSync).astimezone().date() == self.localToday()

    def dismissedCheck(self) -> dt.date | None:
        """Kept on this phone, so Not now stays once tapped (4g, like Talon's BN1.1)."""
        dismissed = self.store.meta(dismissedKey) if self.store is not None else None
        return dt.date.fromisoformat(dismissed) if dismissed else None

    def rememberDismissed(self, checkDate: dt.date) -> None:
        if self.store is not None:
            self.store.setMeta(dismissedKey, checkDate.isoformat())

    def syncFacts(self) -> SyncFacts:
        if self.store is None:
            return SyncFacts(self.lastOutcome.status, self.lastOutcome.problem, None, 0, None, ())
        waiting = self.store.waiting()
        lastSync = self.store.meta("lastSyncAt")
        return SyncFacts(self.lastOutcome.status, self.lastOutcome.problem,
                         dt.datetime.fromisoformat(lastSync) if lastSync else None,
                         waiting.count, waiting.oldestQueuedAt, waiting.refused)

    def extraLogFiles(self) -> list[str]:
        """Flet's own console.log, which the Problems page's log check covers too (Phase 0's check)."""
        return [os.path.join(os.getenv("FLET_APP_STORAGE_CACHE", ""), "console.log")]
