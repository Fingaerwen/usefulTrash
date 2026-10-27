"""Tests for the PC view (gym/pcApp.py and its screens) with the cloud stand-in: sign-in loads everything,
the Plans tab imports straight to the cloud, a failed write changes nothing, the phone's changes show up
after a fetch, and the website's code never needs SQLite."""

import asyncio
import dataclasses
import datetime as dt
import io
import json
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path

import pytest
from cloudStandIn import CloudStandIn
from driveStandIn import DriveStandIn
from screenTestKit import draw, find, press, useLoop, visibleTexts
from usefulTestKit import FakeClock, exampleRow, userA

from gym.pcApp import PcApp
from gym.screens.root import GymApp
from gym.tables import appSchema, tablesByName
from usefulShared.backup.driveApi import DriveApi
from usefulShared.platform.appLog import AppLog
from usefulShared.tables import newRowId, toCloud

repoRoot = Path(__file__).resolve().parents[2]
monday = dt.date(2026, 10, 12)
config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClientId"}


class FakeGoogle:
    async def getIdToken(self, serverClientId, hashedNonce):
        return {"status": "ok", "idToken": f"googleIdToken:{userA}:{hashedNonce}"}

    async def clearSignInState(self):
        return {"status": "ok"}


@dataclasses.dataclass
class PickedFile:
    name: str
    bytes: bytes


class FakePicker:
    def __init__(self):
        self.files = []
        self.saved: tuple[str, bytes] | None = None

    async def pick_files(self, **options):
        return self.files

    async def save_file(self, file_name=None, src_bytes=None, **options):
        self.saved = (file_name, src_bytes)  # in the browser: a download


class FakePrefs:
    """This site's local storage, as Flet's SharedPreferences sees it."""

    def __init__(self):
        self.values: dict[str, str] = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value
        return True

    async def remove(self, key):
        self.values.pop(key, None)
        return True


class FakeGoogleWindow:
    """The second window with Google's Drive permission page: answers like driveToken.html would."""

    def __init__(self, prefs: FakePrefs):
        self.prefs = prefs
        self.opened: list[str] = []
        self.answer: dict | None = None  # None: allow, with the request's state

    async def launch_url(self, url, web_only_window_name=None, **options):
        self.opened.append(url)
        state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        self.prefs.values["driveToken"] = json.dumps(self.answer or {"state": state, "accessToken": "driveToken1",
                                                                      "expiresIn": 3599, "error": ""})


class FakeClipboard:
    async def set(self, value):
        self.text = value


@dataclasses.dataclass
class Services:
    googleSignIn: FakeGoogle
    clipboard: FakeClipboard
    filePicker: FakePicker
    prefs: FakePrefs
    urlLauncher: FakeGoogleWindow


class Browser:
    def __init__(self, cloud):
        self.cloud = cloud
        prefs = FakePrefs()
        self.services = Services(FakeGoogle(), FakeClipboard(), FakePicker(), prefs, FakeGoogleWindow(prefs))
        self.drive = DriveStandIn()
        self.clock = FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC))
        self.loop = asyncio.new_event_loop()
        useLoop(self.loop)
        self.app = PcApp(config, self.services, AppLog(None, self.clock), self.clock, lambda: monday, cloud=cloud,
                         drive=DriveApi(self.drive))
        self.run(self.app.start())

    def run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    def screen(self):
        return draw(GymApp, self.app, self.app.model)

    def texts(self):
        return visibleTexts(self.screen())

    def close(self):
        self.app._stopRefreshing()
        self.loop.run_until_complete(asyncio.sleep(0))
        self.loop.close()


@pytest.fixture
def cloud():
    standIn = CloudStandIn(FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC)))
    standIn.signUpsAllowedFor = {userA}
    return standIn


@pytest.fixture
def browser(cloud):
    tab = Browser(cloud)
    yield tab
    tab.close()


def planInCloud(cloud):
    planJson = json.loads((repoRoot / "plans" / "examplePlan.json").read_text())
    row = {"id": newRowId(), "userId": userA, "updatedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "deleted": False, "cloudUpdatedAt": None, "importedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "effectiveDate": monday, "startStep": 0, "planJson": planJson, "archived": False}
    cloud.storeDirectly("plans", toCloud(tablesByName["plans"], row))


def signedIn(browser):
    press(find(browser.screen(), "Sign in with Google", "Button"))
    assert browser.app.model.screen == "main", browser.app.model.notice
    browser.app._stopRefreshing()
    return browser


def testSignInLoadsEverythingThenShowsToday(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    assert "Push" in browser.texts() and "Monday · 0 of 3 this week" in browser.texts()
    browser.app.model.tab = "plans"
    texts = browser.texts()
    assert "Active: Push Pull Legs (example) (v1) · since 12 Oct · 3/week" in texts


def testImportingAPlanWritesStraightToTheCloud(browser, cloud):
    signedIn(browser)
    browser.app.model.tab = "plans"
    assert "No plan yet." in browser.texts()
    browser.services.filePicker.files = [PickedFile("examplePlan.json",
                                                    (repoRoot / "plans" / "examplePlan.json").read_bytes())]
    press(find(browser.screen(), "Import a plan file…", "Button"))
    press(find(browser.screen(), "Import", "Button"))
    assert len(cloud.rows["plans"]) == 1
    assert "Active: Push Pull Legs (example) (v1) · since 12 Oct · 3/week" in browser.texts()


def testAFailedWriteChangesNothingOnScreen(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "today"
    cloud.offline = True
    press(find(browser.screen(), "Bench Press: done as targeted", "IconButton"))
    assert browser.app.model.today.exercises[0].status == "todo"
    assert ("No connection to the cloud right now. Nothing was changed. Try again in a moment."
            in browser.texts())


def testThePhonesChangesShowUpAfterAFetch(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    cloud.clock.advance(minutes=10)
    cloud.storeDirectly("dailySteps", toCloud(tablesByName["dailySteps"], exampleRow("dailySteps", date=monday)))
    browser.run(browser.app.fetchNow())
    texts = browser.texts()
    assert texts[texts.index("STEPS TODAY") + 1] == "14,000"


def testCloudNotUpgradedYetSaysSo(browser, cloud):
    cloud.schemaVersion = appSchema - 1
    press(find(browser.screen(), "Sign in with Google", "Button"))
    assert browser.app.model.screen == "downloading"
    assert any(f"needs cloud upgrade {appSchema:03d}" in text for text in browser.texts())


def testSigningOutForgetsEverything(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.run(browser.app.signOut())
    assert browser.app.model.screen == "signIn" and not browser.app.session.isSignedIn()
    assert browser.app.store.rows("plans") == []


def testProgressAndWeekTabsAreThereToo(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "progress"
    assert "Bench Press" in browser.texts() and "now 80 kg × 8" in browser.texts()
    browser.app.model.tab = "week"
    assert "This week" in browser.texts() and "12–18 Oct" in browser.texts() and "0 of 3" in browser.texts()
    assert browser.app.canEnterStepsOn(monday - dt.timedelta(days=30))  # the PC view takes any day (SC4.1)
    browser.app.model.tab = "charts"  # SC8.1: the PC view has Charts and Weight too
    assert "Charts" in browser.texts() and browser.app.model.chart.exercise.name == "Bench Press"
    browser.app.model.tab = "weight"
    assert "Weight" in browser.texts() and "Fri 9 Oct" in browser.texts()


def testTheWebsitesCodeNeverNeedsSQLite():
    """The PC view runs Python in the browser, which may have no SQLite: none of its code may import it."""
    script = (
        "import sys\n"
        "class NoSQLite:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'sqlite3' or name.startswith('_sqlite3'):\n"
        "            raise ImportError('no SQLite in the browser')\n"
        "sys.meta_path.insert(0, NoSQLite())\n"
        "import main, gym.pcApp, gym.screens.root\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                            env={"PYTHONPATH": f"{repoRoot / 'apps/gym/src'}:{repoRoot / 'shared/src'}"})
    assert result.stdout.strip() == "ok", result.stderr[-2000:]


def testThePcViewsHistoryTabEditsAnyDay(browser, cloud):
    """HI1.1, SC6.1: a month at a time, any day. Edit lays the day out like Today."""
    planInCloud(cloud)
    signedIn(browser)
    app = browser.app
    app.localToday = lambda: monday + dt.timedelta(days=40)  # 21 Nov
    app.refresh()
    app.model.tab = "history"
    assert "November 2026" in browser.texts() and len(app.model.historyDays) == 21
    app.showHistoryMonth(-1)
    assert "October 2026" in browser.texts() and len(app.model.historyDays) == 31
    app.showHistoryMonth(-1)
    assert app.model.historyMonth == dt.date(2026, 10, 1)  # not before the plan's first month
    app.editDay(monday)
    assert app.model.historyView is not None and app.model.historyView.date == monday


# --- Backup (F14.1, EX1.1, BK1.1) ----------------------------------------------------------------

def testExportCsvSavesTheBackupAndReadableSets(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    press(find(browser.screen(), "Bench Press: done as targeted", "IconButton"))
    browser.run(browser.app.exportCsv())
    name, content = browser.services.filePicker.saved
    assert name == "GymTracker-export-2026-10-12.zip"
    archive = zipfile.ZipFile(io.BytesIO(content))
    assert {"manifest.json", "plans.csv", "exerciseLogs.csv", "sets.csv"} <= set(archive.namelist())
    sets = archive.read("sets.csv").decode().splitlines()
    assert sets[0] == "date,exercise,exerciseId,set,reps,kg,unit,minutes"
    assert sets[1:] == [f"2026-10-12,Bench Press,benchPress,{n},8,80,kg," for n in range(1, 5)]
    assert "Exported GymTracker-export-2026-10-12.zip" in browser.app.model.backupStatus


def testBackUpNowWithGooglesPermissionFromTheSecondWindow(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "backup"
    texts = browser.texts()
    assert texts[texts.index("LAST BACKUP") + 1] == "none yet"
    press(find(browser.screen(), "Back up now", "Button"))
    (url,) = browser.services.urlLauncher.opened
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert (query["redirect_uri"], query["response_type"], query["scope"], query["client_id"]) == (
        ["https://fingaerwen.github.io/usefulTrash/driveToken.html"], ["token"],
        ["https://www.googleapis.com/auth/drive.file"], ["testClientId"])
    (row,) = [row for row in cloud.rows["backups"].values()]
    assert row["madeBy"] == "pcView" and len(browser.drive.zips()) == 1
    assert browser.services.prefs.values == {}  # the handed-over token is gone from the site's storage
    texts = browser.texts()
    assert any(text.startswith("Backed up to your Google Drive: GymTracker-backup-") for text in texts)
    assert any(text.startswith("12 Oct 2026 (PC view)") for text in texts)
    assert "driveToken1" not in "\n".join(browser.app.problemsLines())


def testBackUpNowIgnoresAnAnswerForAnotherRequest(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.services.urlLauncher.answer = {"state": "someoneElses", "accessToken": "driveToken1"}
    browser.run(browser.app.backUpNow())
    assert not cloud.rows.get("backups") and browser.drive.zips() == []
    assert browser.app.model.backupStatus.startswith("No permission came back from Google")


def testAWarningAfter60DaysWithoutABackup(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.run(browser.app.backUpNow())
    browser.clock.advance(days=61)
    cloud.clock.advance(days=61)
    browser.app.refresh()
    from gym.pcApp import backupWarning
    assert backupWarning in browser.texts()
    browser.app.openBanner(backupWarning)
    assert browser.app.model.tab == "backup"


# --- Switching back to an earlier plan and archiving (SW1.1, SW1.2) -----------------------------

def twoPlansInCloud(cloud):
    """Full Body from 14 Sep, then Push Pull Legs from 28 Sep: on Monday 12 Oct, Full Body is an earlier plan."""
    for name, effective in (("Full Body", dt.date(2026, 9, 14)), ("Push Pull Legs (example)", dt.date(2026, 9, 28))):
        planJson = dict(json.loads((repoRoot / "plans" / "examplePlan.json").read_text()), name=name)
        moment = dt.datetime.combine(effective, dt.time(15, 0), tzinfo=dt.UTC)
        row = {"id": newRowId(), "userId": userA, "updatedAt": moment, "deleted": False, "cloudUpdatedAt": None,
               "importedAt": moment, "effectiveDate": effective, "startStep": 0, "planJson": planJson,
               "archived": False}
        cloud.storeDirectly("plans", toCloud(tablesByName["plans"], row))


def testSwitchingBackToAnEarlierPlanAsksFirst(browser, cloud):
    twoPlansInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "plans"
    texts = browser.texts()
    assert "Active: Push Pull Legs (example) (v1) · since 28 Sep · 3/week" in texts
    assert "Earlier: Full Body (v1) · 14 Sep – 27 Sep" in texts
    press(find(browser.screen(), "Switch back to Full Body (v1)", "Container"))
    assert "Switch to Full Body (v1) from today?" in browser.texts()
    press(find(browser.screen(), "Cancel", "Button"))
    assert "Switch to Full Body (v1) from today?" not in browser.texts() and len(cloud.rows["plans"]) == 2
    press(find(browser.screen(), "Switch back to Full Body (v1)", "Container"))
    press(find(browser.screen(), "Switch", "Button"))
    assert len(cloud.rows["plans"]) == 3  # a new import of the same plan: its first stretch stays as it was
    texts = browser.texts()
    assert "Switched to Full Body (v1). It takes effect today." in texts
    assert "Active: Full Body (v1) · since 12 Oct · 3/week" in texts
    assert "Earlier: Full Body (v1) · 14 Sep – 27 Sep" in texts
    assert "Earlier: Push Pull Legs (example) (v1) · 28 Sep – 11 Oct" in texts


def testSwitchingAfterAWorkoutTodayTakesEffectTomorrow(browser, cloud):
    twoPlansInCloud(cloud)
    signedIn(browser)
    browser.run(browser.app.check(browser.app.model.today.exercises[0]))
    browser.app.model.tab = "plans"
    press(find(browser.screen(), "Switch back to Full Body (v1)", "Container"))
    assert "Switch to Full Body (v1) from tomorrow, since you've logged a workout today?" in browser.texts()
    press(find(browser.screen(), "Switch", "Button"))
    texts = browser.texts()
    assert "Switched to Full Body (v1). It takes effect tomorrow." in texts
    assert "From 13 Oct: Full Body (v1)" in texts
    assert "Active: Push Pull Legs (example) (v1) · since 28 Sep · 3/week" in texts


def testArchivingTucksAPlanAwayAndUnarchiveBringsItBack(browser, cloud):
    twoPlansInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "plans"
    press(find(browser.screen(), "Archive Full Body (v1)", "Container"))
    texts = browser.texts()
    assert "Earlier: Full Body (v1) · 14 Sep – 27 Sep" not in texts and "ARCHIVED (1)" in texts
    assert [row["archived"] for row in cloud.rows["plans"].values()].count(True) == 1
    assert len(browser.app.state.plans) == 2  # its weeks still count in Week, History and the charts
    from screenTestKit import redraw

    from gym.screens.plans import PlansTab
    tab = draw(PlansTab, browser.app, browser.app.model)
    press(find(tab, "Show archived plans", "IconButton"))
    redraw(tab)  # the fold is the tab's own state, kept by a redraw
    assert "Full Body (v1) · 14 Sep – 27 Sep" in visibleTexts(tab)
    press(find(tab, "Unarchive Full Body (v1)", "Container"))
    texts = browser.texts()
    assert "Earlier: Full Body (v1) · 14 Sep – 27 Sep" in texts and "ARCHIVED (1)" not in texts
    assert not any(row["archived"] for row in cloud.rows["plans"].values())


def testTheActivePlanHasNoSwitchOrArchive(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "plans"
    texts = browser.texts()
    assert "Switch" not in texts and "Archive" not in texts
