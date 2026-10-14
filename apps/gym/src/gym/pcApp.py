"""The PC view (plan 3b, PC mode; SC6.1): the website on GitHub Pages. It signs in with Google's website
sign-in (6.1), loads everything from the cloud at sign-in, writes straight to the cloud (CS1.1) and
fetches every minute so the phone's changes show up without reloading (14b).

Nothing is kept in the browser: the session lives in this tab's memory only (check 6), so closing the
tab signs you out, and the log is memory only too (12d).
"""

import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from gym.appBase import AppBase
from gym.model import SyncFacts
from gym.signInFlow import signInWithGoogle
from gym.tables import appSchema, appTables
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi
from usefulShared.platform.appLog import AppLog
from usefulShared.signIn.sessionKeeper import MemoryStore, SessionKeeper
from usefulShared.store.cloudStore import CloudStore, VersionMismatch, describeCloudError

refreshEverySec = 60


class PcServices:
    """The browser's abilities: Google's button (our extension's web half), Flet's clipboard and file picker."""

    def __init__(self):
        from nativeGoogleSignIn import NativeGoogleSignIn

        self.googleSignIn = NativeGoogleSignIn()
        self.clipboard = ft.Clipboard()
        self.filePicker = ft.FilePicker()


class PcApp(AppBase):
    """PC mode: the cloud store in memory, refreshed every minute."""

    mode = "pc"
    menuItems = ("problems", "signOut")  # plans are imported from the Plans tab

    def __init__(self, config: dict[str, str], services: Any, log: AppLog,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 localToday: Callable[[], dt.date] = dt.date.today, cloud: Any = None):
        super().__init__(config, services, log, clock, localToday)
        self.injectedCloud = cloud
        self.cloud: Any = None
        self.store: CloudStore | None = None
        self.lastFetch = ("none", "")  # (status, problem) of the latest fetch, for Problems and banners
        self.lastFetchAt: dt.datetime | None = None
        self._refreshTask: asyncio.Task | None = None

    async def start(self) -> None:
        if not self.hasCloudSettings():
            self._fail("This build has no cloud settings. Rebuild it with tools/buildRelease.py.")
            return
        self.cloud = self.injectedCloud or SupabaseApi(self.config["supabaseUrl"], self.config["supabasePublishableKey"])
        self.session = SessionKeeper(self.cloud, MemoryStore())
        session = self.session
        self.log.knownSecrets = lambda: (session.session.get("access_token", ""),
                                         session.session.get("refresh_token", ""))
        self.store = CloudStore(self.cloud, self.session, appTables, appSchema, self.clock)
        self.model.screen = "signIn"  # nothing is kept in the browser, so each visit signs in

    # --- Signing in and out ------------------------------------------------------------------

    async def signIn(self) -> None:
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
        await self.session.save(result.session)  # this tab's memory only
        self.startActions()
        await self.load()

    async def load(self) -> None:
        """Loads everything, with a running count (14b), then shows the tabs."""
        self.model.screen, self.model.busy, self.model.downloaded = "downloading", "Loading your data…", 0

        def progress(count: int) -> None:
            self.model.downloaded = count

        try:
            await self.store.fetch(progress)
        except VersionMismatch as mismatch:
            self.model.notice = str(mismatch)
            return
        except CloudError as problem:
            self.log.problem("sync", "Loading from the cloud didn't work.", f"{problem.statusCode} {problem.errorCode}: "
                                                                             f"{problem.message}")
            self.model.notice = ("No connection to the cloud. Tap Try again." if problem.isTemporary
                                 else "Loading didn't work. Details are on the Problems page.")
            return
        finally:
            self.model.busy = ""
        self.lastFetch, self.lastFetchAt = ("done", ""), self.clock()
        self.refresh()
        self.model.screen = "main"
        self._startRefreshing()

    async def firstDownload(self) -> None:
        """The loading screen's Try again."""
        await self.load()

    async def signOut(self) -> None:
        self._stopRefreshing()
        try:
            await self.cloud.signOut(await self.session.freshAccessToken())
        except CloudError:
            pass
        await self.session.forget()
        try:
            await self.services.googleSignIn.clearSignInState()
        except Exception as problem:
            self.log.problem("signIn", "Google's chosen account couldn't be forgotten.", type(problem).__name__)
        self.store.clear()
        self.refresh()
        self.model.notice = "Signed out."
        self.model.screen = "signIn"

    # --- Fetching every minute (14b) ---------------------------------------------------------

    def _startRefreshing(self) -> None:
        if self._refreshTask is None:
            self._refreshTask = asyncio.get_running_loop().create_task(self._refreshLoop())

    def _stopRefreshing(self) -> None:
        if self._refreshTask is not None:
            self._refreshTask.cancel()
            self._refreshTask = None

    async def _refreshLoop(self) -> None:
        while True:
            await asyncio.sleep(refreshEverySec)
            try:
                await self.fetchNow()
            except Exception as problem:  # a bug must not stop fetching for good
                self.log.crash(problem, "sync")

    async def fetchNow(self) -> None:
        """Fetches what changed elsewhere and redraws."""
        try:
            await self.store.fetch()
            self.lastFetch, self.lastFetchAt = ("done", ""), self.clock()
        except VersionMismatch as mismatch:
            self.lastFetch = ("versions", str(mismatch))
        except CloudError as problem:
            self.lastFetch = ("offline" if problem.isTemporary else "failed",
                              f"{problem.statusCode} {problem.errorCode}: {problem.message}")
        if not self.session.isSignedIn():
            self._stopRefreshing()
            self.model.notice = "You were signed out. Please sign in again."
            self.model.screen = "signIn"
            return
        self.refresh()

    def onResume(self) -> None:
        if self.model.screen == "main":
            asyncio.get_running_loop().create_task(self.fetchNow())

    # --- What appBase needs ------------------------------------------------------------------

    def rowsByTable(self) -> dict[str, list[dict[str, Any]]] | None:
        if self.store is None:
            return None
        return {table.name: self.store.rows(table.name) for table in appTables}

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Straight to the cloud; the screen changes only once the cloud has it."""
        saved = await self.store.saveMany(edits)
        self.refresh()
        return saved

    def describeFailure(self, problem: Exception) -> str | None:
        if isinstance(problem, CloudError):
            self.log.problem("save", "The cloud didn't take a change.", f"{problem.statusCode} {problem.errorCode}: "
                                                                         f"{problem.message}")
            return describeCloudError(problem)
        if isinstance(problem, VersionMismatch):
            return str(problem)
        return None

    def afterRefresh(self) -> None:
        self.model.planLines = self.state.planLines(self.localToday())
        status, problem = self.lastFetch
        self.model.banners = (problem,) if status == "versions" else ()

    def syncFacts(self) -> SyncFacts:
        status, problem = self.lastFetch
        return SyncFacts(status, problem, self.lastFetchAt, 0, None, ())
