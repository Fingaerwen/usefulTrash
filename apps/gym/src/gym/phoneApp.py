"""The phone app (plan 3b, phone mode): the phone's database, sync, sign-in and the model the screens
draw. Every button on the phone ends up here; the screens only read the model and call these methods.

Start-up: upgrade the phone's database if needed (14c), restore the saved session (T1.1), then the
first download if this phone has none yet (14b), then Today with sync running in the background.
"""

import datetime as dt
import os
import sqlite3
from collections.abc import Callable
from typing import Any, Protocol

import flet as ft

from gym.actions import ActionRefused, GymActions
from gym.model import AppModel, LogFacts, SyncFacts, problemsReport
from gym.phoneSteps import phoneSteps
from gym.planImporter import answerQuestions, finishImport, startImport
from gym.rules.today import ExerciseLine, SetDone
from gym.state import GymState
from gym.tables import appSchema, appTables
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi, makeNoncePair
from usefulShared.platform.appLog import AppLog
from usefulShared.signIn.sessionKeeper import SecretStore, SessionKeeper
from usefulShared.store.phoneStore import PhoneDatabaseError, PhoneStore, runPhoneSteps
from usefulShared.sync.syncEngine import SyncEngine, SyncLoop, SyncOutcome

databaseName = "gymTracker.sqlite3"
notSyncedAfter = dt.timedelta(days=3)  # the "Not synced" banner (G9.2b)


class PhoneServices(Protocol):
    """The phone's own abilities, from our extensions and Flet (fakes in tests)."""

    googleSignIn: Any  # nativeGoogleSignIn: getIdToken(serverClientId, hashedNonce), clearSignInState()
    secretStore: SecretStore  # secureStore: the session, encrypted with a phone-locked key (T1.1)
    clipboard: Any  # Flet's Clipboard: set(text)
    filePicker: Any  # Flet's FilePicker: pick_files(...)


class PhoneApp:
    """Phone mode: owns the database, the session, sync and the model."""

    def __init__(self, config: dict[str, str], folder: str, services: PhoneServices, log: AppLog,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 localToday: Callable[[], dt.date] = dt.date.today, cloud: Any = None):
        self.config = config  # the public identifiers only (K2a): Supabase address, publishable key, client ID
        self.folder = folder
        self.services = services
        self.log = log
        self.clock = clock
        self.localToday = localToday  # your phone's calendar date (16.4c)
        self.injectedCloud = cloud  # None: the real Supabase project; tests pass a stand-in
        self.model = AppModel()
        self.state = GymState()
        self.store: PhoneStore | None = None
        self.session: SessionKeeper | None = None
        self.cloud: SupabaseApi | None = None
        self.engine: SyncEngine | None = None
        self.syncLoop: SyncLoop | None = None
        self.actions: GymActions | None = None
        self.lastOutcome = SyncOutcome("none")
        self._trainAnywayOn: dt.date | None = None  # Train anyway applies to the day it was pressed

    # --- Start-up ----------------------------------------------------------------------------

    async def start(self) -> None:
        """Opens everything and decides the first screen."""
        if not all(self.config.get(name) for name in ("supabaseUrl", "supabasePublishableKey", "googleWebClientId")):
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
        self.log.knownSecrets = lambda: (session.session.get("access_token", ""), session.session.get("refresh_token", ""))
        self.engine = SyncEngine(self.store, self.cloud, self.session, appTables, appSchema, self.clock)
        self.syncLoop = SyncLoop(self.engine, self._onSyncOutcome)

        restored = await self.session.restore()
        if restored == "restored":
            await self._signedIn()
        else:
            if restored in ("unreadable", "error"):
                self.log.problem("signIn", "The saved sign-in couldn't be read, so you need to sign in again.",
                                 self.session.lastProblem)
                self.model.notice = "Please sign in again."
            self.model.screen = "signIn"

    def _fail(self, why: str) -> None:
        self.model.failure = why
        self.model.screen = "failed"

    async def _signedIn(self) -> None:
        """After sign-in or a restored session: make sure the database is this account's, download
        everything if this phone has nothing yet, then show Today and start syncing."""
        if self.store.claimFor(self.session.userId()):
            self.log.info("signIn", "a different account signed in, so this phone's data was cleared")
        self.actions = GymActions(_SavingRows(self), self.state, self.session.userId(), self.clock)
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
        self.model.busy = ""
        if outcome.status != "done":
            self.log.problem("sync", "The first download didn't finish.", outcome.problem or outcome.status)
            self.model.notice = ("No internet: the first download needs it. Tap Try again when you're online."
                                 if outcome.status == "offline" else f"The first download didn't finish: {outcome.problem}")
            return
        self.store.setMeta("firstDownloadDone", self.clock().isoformat())
        self.log.info("sync", f"first download: {outcome.fetched} rows")
        self.refresh()
        self.model.screen = "main"
        self.syncLoop.start()

    # --- Signing in and out ------------------------------------------------------------------

    async def signIn(self) -> None:
        """Google's account picker → ID token → Supabase session (AU1c). The same ID token with a wrong
        nonce must be refused first, so sign-in never works if replay protection was switched off (F9)."""
        if self.model.busy:
            return
        self.model.busy, self.model.notice = "Waiting for Google…", ""
        try:
            rawNonce, hashedNonce = makeNoncePair()
            answer = await self.services.googleSignIn.getIdToken(self.config["googleWebClientId"], hashedNonce)
            status = answer.get("status")
            if status == "cancelled":
                return
            if status != "ok":
                self.log.problem("signIn", "Google sign-in didn't work.",
                                 f"{answer.get('errorType', status)}: {answer.get('message', '')}")
                self.model.notice = "Google sign-in didn't work. Details are on the Problems page."
                return
            idToken = answer["idToken"]
            self.model.busy = "Signing in…"
            if not await self._wrongNonceIsRefused(idToken):
                return
            session = await self.cloud.signInWithGoogleIdToken(idToken, rawNonce)
            if not await self.session.save(session):
                self.log.problem("signIn", "The sign-in couldn't be saved on the phone; you'll need to sign in "
                                           "again next time.", self.session.lastProblem)
            self.log.info("signIn", "signed in")
        except CloudError as problem:
            self.log.problem("signIn", "Signing in didn't work.", f"{problem.statusCode} {problem.errorCode}: "
                                                                   f"{problem.message}")
            self.model.notice = ("No internet: signing in needs it." if problem.isTemporary else
                                 "This Google account isn't allowed in this app." if problem.errorCode == "signup_disabled"
                                 else "Signing in didn't work. Details are on the Problems page.")
            return
        finally:
            self.model.busy = ""
        await self._signedIn()

    async def _wrongNonceIsRefused(self, idToken: str) -> bool:
        """The replay check: Supabase must refuse this ID token with a nonce it wasn't made for."""
        wrongNonce, _ = makeNoncePair()
        try:
            accidental = await self.cloud.signInWithGoogleIdToken(idToken, wrongNonce)
        except CloudError as problem:
            if problem.isTemporary:
                raise  # a network problem proves nothing about the nonce check
            return True
        try:
            await self.cloud.signOut(accidental["access_token"])
        except (CloudError, KeyError, TypeError):
            pass
        self.log.problem("signIn", "Sign-in was stopped for safety: the cloud accepted a wrong nonce.",
                         "check Supabase: Authentication > Providers > Google > Skip nonce checks must be off")
        self.model.notice = "Sign-in was stopped for safety. Details are on the Problems page."
        return False

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
        except Exception as problem:  # the account picker just won't show next time; nothing else depends on it
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
            self.log.info("sync", "no internet; trying every minute", outcome.problem)
        if not self.session.isSignedIn():
            self.syncLoop.stop()
            self.model.notice = "You were signed out. Please sign in again."
            self.model.screen = "signIn"
            return
        self.refresh()

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

    # --- Today -------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Works out the facts again from the database and redraws what changed."""
        if self.store is None:
            return
        self.state.load({table.name: self.store.rows(table.name) for table in appTables})
        today = self.localToday()
        if self._trainAnywayOn != today:
            self._trainAnywayOn, self.model.trainAnyway = None, False
        self.model.today = self.state.today(today, self.model.trainAnyway)
        waiting = self.store.waiting()
        self.model.waiting = waiting.count
        self.model.banners = self._banners(waiting)

    def _banners(self, waiting) -> tuple[str, ...]:
        banners = []
        if self.lastOutcome.status == "appTooOld":
            banners.append("Update the app: the cloud needs a newer version. Your entries are kept until then.")
        elif self.lastOutcome.status == "cloudTooOld":
            banners.append(f"The cloud needs upgrade {appSchema:03d} before this app can sync.")
        if waiting.refused:
            banners.append("The cloud refused a change. See Problems (⋮).")
        if waiting.oldestQueuedAt is not None and self.clock() - waiting.oldestQueuedAt >= notSyncedAfter:
            banners.append("Not synced for 3 days. Check your internet, or see Problems (⋮).")
        return tuple(banners)

    def trainAnyway(self) -> None:
        """Rest day: show the next workout instead (19.1c-2). Nothing is saved until something is logged."""
        self._trainAnywayOn, self.model.trainAnyway = self.localToday(), True
        self.refresh()

    async def check(self, line: ExerciseLine) -> None:
        await self._act(self.actions.checkExercise(self.model.today, line))

    async def saveSets(self, line: ExerciseLine, sets: list[SetDone], minutes: int | None = None) -> None:
        await self._act(self.actions.saveSets(self.model.today, line, sets, minutes))

    async def skip(self, line: ExerciseLine) -> None:
        await self._act(self.actions.skipExercise(self.model.today, line))

    async def finish(self) -> None:
        await self._act(self.actions.finishWorkout(self.model.today))

    async def setSteps(self, steps: int | None) -> None:
        await self._act(self.actions.setSteps(self.localToday(), steps))

    async def _act(self, action) -> None:
        """Runs an action; a refused entry shows why, anything unexpected goes to the log."""
        try:
            await action
        except ActionRefused as refused:
            self.model.notice = str(refused)
        except Exception as problem:
            self.log.crash(problem, "today")
            self.model.notice = "That didn't work. Details are on the Problems page."

    # --- Problems page (12d) -----------------------------------------------------------------

    def openProblems(self) -> None:
        self.model.problems = self._problemsReport()
        self.model.screen = "problems"

    def closeProblems(self) -> None:
        self.model.screen = "main" if self.session is not None and self.session.isSignedIn() else "signIn"

    async def copyProblems(self) -> None:
        await self.services.clipboard.set("\n".join(self.model.problems))
        self.model.notice = "Copied."

    def clearProblems(self) -> None:
        self.log.clear()
        self.model.problems = self._problemsReport()

    def tryRefusedAgain(self) -> None:
        if self.store is not None and self.store.sendRefusedAgain():
            self.syncLoop.resumed()
        self.refresh()
        self.model.problems = self._problemsReport()

    def _problemsReport(self) -> tuple[str, ...]:
        waiting = self.store.waiting() if self.store else None
        lastSync = self.store.meta("lastSyncAt") if self.store else None
        sync = SyncFacts(self.lastOutcome.status, self.lastOutcome.problem,
                         dt.datetime.fromisoformat(lastSync) if lastSync else None,
                         waiting.count if waiting else 0, waiting.oldestQueuedAt if waiting else None,
                         waiting.refused if waiting else ())
        consoleLog = os.path.join(os.getenv("FLET_APP_STORAGE_CACHE", ""), "console.log")
        check = self.log.check([consoleLog])
        recent = tuple((entry.at, entry.area, entry.plainWords, entry.technical) for entry in self.log.entries(limit=20))
        return problemsReport(appSchema, sync, LogFacts(check.lines, check.tokenShapedStrings, check.knownSecretsFound,
                                                        recent), self.clock(), len(self.state.unreadablePlans))

    # --- Plan import, the phone's fallback (G2b-2) -------------------------------------------

    async def pickPlanFile(self) -> None:
        files = await self.services.filePicker.pick_files(file_type=ft.FilePickerFileType.CUSTOM,
                                                          allowed_extensions=["json"], with_data=True)
        if not files:
            return
        picked = files[0]
        today = self.localToday()
        self.model.planImport = startImport(picked.name, picked.bytes or b"", self.state.known, today,
                                            workoutLoggedToday=self.model.today is not None and self.model.today.workoutExists)
        self.model.screen = "importPlan"

    def answerPlanQuestions(self, sameAs: list[bool]) -> None:
        self.model.planImport = answerQuestions(self.model.planImport, sameAs)

    async def finishPlanImport(self, startStep: int) -> None:
        flow = self.model.planImport
        row = finishImport(flow, startStep, self.session.userId(), self.clock())
        await self._act(_SavingRows(self).saveRows([("plans", row)]))
        when = "today" if flow.takesEffect == self.localToday() else "tomorrow"
        self.model.notice = f"Plan imported. It takes effect {when}."
        self.closePlanImport()

    def closePlanImport(self) -> None:
        self.model.planImport = None
        self.model.screen = "main"


class _SavingRows:
    """The store the actions use on the phone: save in one transaction, redraw, and sync a few seconds later."""

    def __init__(self, app: PhoneApp):
        self.app = app

    async def saveRows(self, edits) -> list[dict[str, Any]]:
        saved = self.app.store.saveMany(edits)
        self.app.refresh()
        self.app.syncLoop.changed()
        return saved
