"""Ambrosia's PC view (plan 3b, PC mode, 4b): the website on GitHub Pages, like Talon's. It signs in with Google's
website sign-in (6.1), loads everything from the cloud at sign-in, writes straight to the cloud (CS1.1) and fetches
every minute so the phone's changes show up without reloading (14b).

Nothing is kept in the browser: the session lives in this tab's memory only, so closing the tab signs you out, and
the log and Not now on the bulk check's suggestion are memory only too (12d). Both PC views share one browser
storage (4j), and Ambrosia keeps nothing in it.
"""

import asyncio
import datetime as dt
import json
import secrets
import urllib.parse
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from ambrosia.appBase import AmbrosiaBase
from ambrosia.tables import appSchema, appTables, dietTables
from usefulShared.backup.backupFile import makeBackupZip
from usefulShared.backup.backupJob import ambrosiaBackups, lastBackup, makeBackup, warnAfter
from usefulShared.backup.driveApi import DriveApi, DriveError, browserTransport
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi
from usefulShared.platform.appLog import AppLog
from usefulShared.platform.problems import SyncFacts
from usefulShared.signIn.sessionKeeper import MemoryStore, SessionKeeper
from usefulShared.signIn.signInFlow import signInWithGoogle
from usefulShared.store.cloudStore import CloudStore, VersionMismatch, describeCloudError

refreshEverySec = 60
backupWarning = "Your last backup is over 60 days old: see the Backup tab."  # plan 3.4
siteAddress = "https://fingaerwen.github.io/usefulTrash/"  # driveToken.html stays here, for both PC views (4c)
driveHandoverKey = "ambrosiaDriveToken"  # what site/driveToken.html leaves for a request whose state starts "ambrosia."
handoverWaitSec = 180  # how long Back up now waits for Google's answer


class PcServices:
    """The browser's abilities: Google's button (our extension's web half), Flet's clipboard, file picker, second
    window (for Google's Drive permission page) and this site's local storage (only for Drive's handover)."""

    def __init__(self):
        from nativeGoogleSignIn import NativeGoogleSignIn

        self.googleSignIn = NativeGoogleSignIn()
        self.clipboard = ft.Clipboard()
        self.filePicker = ft.FilePicker()
        self.urlLauncher = ft.UrlLauncher()
        self.prefs = ft.SharedPreferences()


class PcApp(AmbrosiaBase):
    """PC mode: the cloud store in memory, refreshed every minute."""

    mode = "pc"
    menuItems = ("importTargets", "problems", "signOut")  # History is a tab here (4b)

    def __init__(self, config: dict[str, str], services: Any, log: AppLog,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 localToday: Callable[[], dt.date] = dt.date.today, cloud: Any = None, drive: Any = None,
                 **sources: Any):
        super().__init__(config, services, log, clock, localToday, **sources)
        self.injectedCloud = cloud
        self.drive = drive or DriveApi(browserTransport)  # Back up now (AM5.6). Tests pass a stand-in
        self.cloud: Any = None
        self.store: CloudStore | None = None
        self.lastFetch = ("none", "")  # (status, problem) of the latest fetch, for Problems and banners
        self.lastFetchAt: dt.datetime | None = None
        self.dismissed: dt.date | None = None  # Not now, in this tab's memory
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
        self.startActions(self.session.userId())
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
        """Straight to the cloud. The screen changes only once the cloud has it."""
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
        status, problem = self.lastFetch
        backups = [row for row in self.state.rows.get("dietBackups", {}).values() if not row["deleted"]]
        last = lastBackup(backups)
        old = last is not None and self.clock() - last["madeAt"] >= warnAfter
        self.model.banners = ((problem,) if status == "versions" else ()) + ((backupWarning,) if old else ())

    def openBanner(self, banner: str) -> None:
        if banner == backupWarning:
            self.model.tab = "backup"

    def syncedToday(self) -> bool:
        """The PC view has today's rows once a fetch went through today."""
        return self.lastFetchAt is not None and self.lastFetchAt.astimezone().date() == self.localToday()

    def dismissedCheck(self) -> dt.date | None:
        return self.dismissed

    def rememberDismissed(self, checkDate: dt.date) -> None:
        self.dismissed = checkDate

    def syncFacts(self) -> SyncFacts:
        status, problem = self.lastFetch
        return SyncFacts(status, problem, self.lastFetchAt, 0, None, ())

    # --- Backup: Export CSV and Back up now (AM5.6, like Talon's EX1.1 and BK1.1) --------------

    def _ownRows(self) -> dict[str, list[dict[str, Any]]]:
        """Ambrosia's own tables as loaded, deleted rows included, so the file restores exactly (14b). Talon's tables
        are in Talon's backups."""
        return {table.name: list(self.state.rows.get(table.name, {}).values()) for table in dietTables}

    async def exportCsv(self) -> None:
        """Export CSV: the backup (one CSV per table, restorable) plus the readable food.csv and days.csv, in one zip
        saved to this PC."""
        content = makeBackupZip(self._ownRows(), dietTables, appSchema, self.clock(), "pcView",
                                self.state.historyFiles(self.localToday()), appName=ambrosiaBackups.app)
        name = f"Ambrosia-export-{self.localToday().isoformat()}.zip"
        try:
            await self.services.filePicker.save_file(file_name=name, src_bytes=content)
        except Exception as problem:
            self.log.problem("backup", "Export CSV didn't work.", f"{type(problem).__name__}: {problem}"[:300])
            self.model.backupStatus = "Export CSV didn't work. Details are on the Problems page."
            return
        self.model.backupStatus = f"Exported {name} ({len(content):,} bytes)."

    def driveConsentUrl(self, state: str) -> str:
        """Google's Drive permission page (files this app created only). It answers to site/driveToken.html."""
        account = str((self.session.session.get("user") or {}).get("email", "")) if self.session else ""
        query = {"client_id": self.config["googleWebClientId"], "redirect_uri": f"{siteAddress}driveToken.html",
                 "response_type": "token", "scope": "https://www.googleapis.com/auth/drive.file", "state": state,
                 "include_granted_scopes": "true", "prompt": "select_account"}
        if account:
            query["login_hint"] = account
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(query)

    async def backUpNow(self) -> None:
        """Back up now: Google's permission page opens in a second window. Its answer, a Drive token that lasts about
        an hour, comes back through the site's local storage (driveToken.html, under Ambrosia's own key), is removed
        from there at once and kept in memory only. Then the backup goes to Ambrosia's Drive folder as the phone's
        does, and its row is saved."""
        state = "ambrosia." + secrets.token_urlsafe(24)
        try:
            await self.services.prefs.remove(driveHandoverKey)  # nothing old can be taken for the answer
            self.model.backupStatus = "Waiting for Google's permission in the other window…"
            await self.services.urlLauncher.launch_url(self.driveConsentUrl(state), web_only_window_name="ambrosiaDrive")
            token = await self._awaitDriveToken(state)
            if token is None:
                self.model.backupStatus = ("No permission came back from Google (the window was closed, or it took "
                                           "over 3 minutes). Press Back up now to try again.")
                return
            row = await makeBackup(self.drive, token, self._ownRows(), dietTables, appSchema, self.session.userId(),
                                   self.clock(), "pcView", self.state.historyFiles(self.localToday()), ambrosiaBackups)
        except Exception as problem:
            reason = problem.reason if isinstance(problem, DriveError) else type(problem).__name__
            self.log.problem("backup", "Back up now didn't work.", f"{reason}: {problem}"[:300])
            self.model.backupStatus = "Back up now didn't work. Details are on the Problems page."
            return
        self.model.notice = ""
        await self._act(self.saveRows([("dietBackups", row)]))
        if not self.model.notice:
            self.model.backupStatus = f"Backed up to your Google Drive: {row['fileName']}."

    async def _awaitDriveToken(self, state: str) -> str | None:
        """Google's answer from driveToken.html, if it's for this request. None if it doesn't come."""
        for _ in range(handoverWaitSec):
            raw = await self.services.prefs.get(driveHandoverKey)
            if raw:
                await self.services.prefs.remove(driveHandoverKey)
                try:
                    handover = json.loads(raw)
                except (TypeError, ValueError):
                    return None
                if not isinstance(handover, dict) or handover.get("state") != state:
                    return None  # not the answer to this request
                if handover.get("error"):
                    self.log.info("backup", f"Google answered: {str(handover['error'])[:60]}")
                    return None
                return str(handover.get("accessToken") or "") or None
            await asyncio.sleep(1)
        return None
