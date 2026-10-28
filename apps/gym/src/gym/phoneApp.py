"""The phone app (plan 3b, phone mode): the phone's database, sync and sign-in. Every button on the phone
ends up here or in appBase.py. The screens only read the model and call these methods.

Start-up: upgrade the phone's database if needed (14c), restore the saved session (T1.1), then the
first download if this phone has none yet (14b), then Today with sync running in the background.
"""

import asyncio
import datetime as dt
import os
import sqlite3
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from gym.appBase import AppBase
from gym.model import SyncFacts
from gym.phoneSteps import phoneSteps
from usefulShared.signIn.signInFlow import signInWithGoogle
from gym.tables import appSchema, appTables
from usefulShared.backup.backupJob import backupDue, makeBackup, withFreshToken
from usefulShared.backup.driveApi import DriveApi, DriveError
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi
from usefulShared.platform.appLog import AppLog
from usefulShared.signIn.sessionKeeper import SecretStore, SessionKeeper
from usefulShared.store.phoneStore import PhoneDatabaseError, PhoneStore, Waiting, runPhoneSteps
from usefulShared.sync.syncEngine import SyncEngine, SyncLoop, SyncOutcome

databaseName = "gymTracker.sqlite3"
notSyncedAfter = dt.timedelta(days=3)  # the "Not synced" banner (G9.2b)
creatineAt = (8, 0)  # the daily creatine reminder (WD3.8)
weighInAt = (5, 7, 0)  # the weekly weigh-in reminder: Friday (ISO weekday 5) at 07:00 (G9.1, NT1.2)


class PhoneServices(Protocol):
    """The phone's own abilities, from our extensions and Flet (fakes in tests)."""

    googleSignIn: Any  # nativeGoogleSignIn: getIdToken(serverClientId, hashedNonce), clearSignInState()
    secretStore: SecretStore  # secureStore: the session, encrypted with a phone-locked key (T1.1)
    clipboard: Any  # Flet's Clipboard: set(text)
    filePicker: Any  # Flet's FilePicker: pick_files(...)
    notifier: Any  # weighInNotify: requestPermission(), scheduleDaily(...), scheduleWeekly(...), scheduleRest(...)


class PhoneApp(AppBase):
    """Phone mode: owns the database, the session and sync."""

    def __init__(self, config: dict[str, str], folder: str, services: PhoneServices, log: AppLog,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 localToday: Callable[[], dt.date] = dt.date.today, cloud: Any = None, drive: Any = None):
        super().__init__(config, services, log, clock, localToday)
        self.folder = folder
        self.injectedCloud = cloud  # None: the real Supabase project. Tests pass a stand-in
        self.drive = drive or DriveApi()  # Google Drive, for the automatic backup (F14.1). Tests pass a stand-in
        self.backupTask: asyncio.Task | None = None  # the backup runs beside the app, after a start's first sync
        self.store: PhoneStore | None = None
        self.cloud: Any = None
        self.engine: SyncEngine | None = None
        self.syncLoop: SyncLoop | None = None
        self.lastOutcome = SyncOutcome("none")
        self.remindersTask: asyncio.Task | None = None  # setting the reminders runs beside the app (it may ask you)

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
        """After sign-in or a restored session: make sure the database is this account's, download
        everything if this phone has nothing yet, then show Today and start syncing."""
        if self.store.claimFor(self.session.userId()):
            self.log.info("signIn", "a different account signed in, so this phone's data was cleared")
        self.startActions()
        self.refresh()
        if self.store.meta("firstDownloadDone") is None:
            await self.firstDownload()
            return
        self.model.screen = "main"
        self.syncLoop.start()
        self.startReminders()

    def startReminders(self) -> None:
        """Sets the reminders in the background: Android's question about notifications waits for your
        answer, and start-up (and its measured time) mustn't wait with it."""
        self.remindersTask = asyncio.get_running_loop().create_task(self.scheduleReminders())

    async def scheduleReminders(self) -> None:
        """The daily creatine reminder at 08:00 (WD3.8) and the Friday weigh-in at 07:00 (G9.1, NT1.2), set
        again at every start (each replaces itself). Android 13+ asks once whether the app may notify. A no
        just means no reminders, never an error."""
        try:
            if not await self.services.notifier.requestPermission():
                self.log.info("reminders", "notifications aren't allowed, so there are no reminders")
                return
            hour, minute = creatineAt
            await self.services.notifier.scheduleDaily(hour, minute, "Creatine", "Time for your creatine")
        except Exception as problem:  # the app works the same without it
            self.log.problem("reminders", "The creatine reminder couldn't be set.", type(problem).__name__)
            return
        try:
            weekday, hour, minute = weighInAt
            await self.services.notifier.scheduleWeekly(weekday, hour, minute, "Weigh-in", "Time to weigh in")
        except Exception as problem:
            self.log.problem("reminders", "The weigh-in reminder couldn't be set.", type(problem).__name__)

    async def restAlert(self, seconds: int | None) -> None:
        """The rest timer's alert (RT1.1): a notification when the rest is over, even with the screen off, in
        its own "Rest timer" channel. None cancels it (and takes away one that's showing)."""
        try:
            if seconds is None:
                await self.services.notifier.cancelRest()
            else:
                await self.services.notifier.scheduleRest(seconds, "Rest over", "Time for your next set.")
        except Exception as problem:  # the timer on screen works the same without it
            self.log.problem("reminders", "The rest timer's alert couldn't be set.", type(problem).__name__)

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
        self.startReminders()

    # --- Signing in and out ------------------------------------------------------------------

    async def signIn(self) -> None:
        """Google's account picker → Supabase session (signInFlow.py), then this phone's data."""
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
        """Each sync round's result: log what matters, update banners and Today."""
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

    # --- The automatic backup (F14.1) ----------------------------------------------------------

    async def backUpIfDue(self) -> None:
        """When the app opens and the last backup (from any device) is 30+ days old: every table, deleted
        rows included, zipped to your Google Drive, the last 3 kept. The first time, Google asks once whether
        the app may keep files in your Drive. A no or a failure is only logged, and it's tried again next start."""
        try:
            if not backupDue(self.store.rows("backups"), self.clock()):
                return
            googleSignIn = self.services.googleSignIn
            account = str((self.session.session.get("user") or {}).get("email", ""))

            async def getToken() -> str:
                answer = await googleSignIn.getDriveAccess(True, account)
                if answer.get("status") != "ok" or not answer.get("accessToken"):
                    raise DriveError(0, str(answer.get("status")), str(answer.get("errorType") or ""))
                return answer["accessToken"]

            async def dropToken(token: str) -> None:
                await googleSignIn.clearDriveToken(token)

            rows = {table.name: self.store.rows(table.name) for table in appTables}
            readable = self.state.historyFiles(self.localToday())
            row = await withFreshToken(getToken, dropToken, lambda token: makeBackup(
                self.drive, token, rows, appTables, appSchema, self.session.userId(), self.clock(), "phone", readable))
            await self.saveRows([("backups", row)])
            self.log.info("backup", f"backed up to Google Drive: {row['fileName']}, {row['sizeBytes']:,} bytes")
        except Exception as problem:  # the app works the same without it
            self.log.problem("backup", "The backup to Google Drive didn't work. It's tried again next time the app "
                             "opens.", f"{type(problem).__name__}: {problem}"[:300])

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

    def summarySeenFor(self) -> dt.date | None:
        """Kept on this phone, so the summary banner stays gone once seen (BN1.1)."""
        seen = self.store.meta("summarySeenFor") if self.store is not None else None
        return dt.date.fromisoformat(seen) if seen else None

    def markSummarySeen(self, monday: dt.date) -> None:
        if self.store is not None:
            self.store.setMeta("summarySeenFor", monday.isoformat())

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
