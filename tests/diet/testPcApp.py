"""Ambrosia's PC view on the cloud stand-in (plan 3b PC mode, apps/diet/docs/plan.md 4b, 4g, 14b): signing in loads
everything, entries go straight to the cloud and a failed write changes nothing, a cloud still waiting for upgrade
003 says so, Apply needs today's rows, Not now lives in the tab's memory, and signing out forgets everything."""

import asyncio
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from ambrosiaStandIn import FakeOpenFoodFacts, PcServices, PhoneServices, bulkInCloud
from cloudStandIn import CloudStandIn
from driveStandIn import DriveStandIn
from screenTestKit import draw, find, press, useLoop
from usefulTestKit import FakeClock, userA

from ambrosia.pcApp import PcApp
from ambrosia.rules.foods import Food, Values
from ambrosia.screens.root import AmbrosiaApp
from ambrosia.sources.openFoodFacts import OpenFoodFacts
from usefulShared.backup.backupFile import readBackupZip
from usefulShared.backup.driveApi import DriveApi
from usefulShared.platform.appLog import AppLog

repoRoot = Path(__file__).resolve().parents[2]
config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClientId"}
targetsFile = json.loads((repoRoot / "apps/diet/plans/exampleTargets.json").read_text())
oats = Food("", "usda", "Oats, whole grain, rolled", Values(379, 13.2, 6.5, 67.7), usdaId=173904)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(dt.datetime(2026, 12, 6, 11, 0, tzinfo=dt.UTC))  # Sunday 6 Dec: the first big-miss check


@pytest.fixture
def cloud(clock) -> CloudStandIn:
    standIn = CloudStandIn(clock)
    standIn.signUpsAllowedFor = {userA}
    bulkInCloud(standIn, targetsFile)
    return standIn


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    useLoop(loop)
    yield loop
    loop.run_until_complete(asyncio.sleep(0))  # lets the cancelled refresh tasks finish
    loop.close()


def pcView(cloud: CloudStandIn, clock: FakeClock, loop, drive: DriveStandIn | None = None) -> PcApp:
    """A browser tab with the PC view, signed in through its screen."""
    app = PcApp(config, PcServices(userA), AppLog(None, clock), clock, lambda: clock().date(), cloud=cloud,
                drive=DriveApi(drive or DriveStandIn()),
                foodSource=OpenFoodFacts("0.1-alpha", FakeOpenFoodFacts(), clock=lambda: 1e12))
    loop.run_until_complete(app.start())
    assert app.model.screen == "signIn"
    press(find(draw(AmbrosiaApp, app, app.model), "Sign in with Google", "Button"))
    app._stopRefreshing()
    return app


def testSignInLoadsEverythingFromTheCloud(cloud, clock, loop):
    app = pcView(cloud, clock, loop)
    assert app.model.screen == "main" and app.model.targets.name == "Bulk from 26 Oct"
    assert app.model.bulkCheck.suggestion.reason == "bigMissLow"


def testEntriesGoStraightToTheCloud(cloud, clock, loop):
    app = pcView(cloud, clock, loop)
    loop.run_until_complete(app.actions.logFood(app.localToday(), "dinner", oats, "grams", 90))
    assert len(cloud.rows["foodLogs"]) == 1 and app.model.today.eaten.kcal == pytest.approx(379 * 0.9)


def testAFailedWriteChangesNothingAndSaysWhy(cloud, clock, loop):
    app = pcView(cloud, clock, loop)
    cloud.offline = True
    loop.run_until_complete(app.addWater())
    assert app.model.notice.startswith("No connection to the cloud right now. Nothing was changed.")
    assert app.state.water == {} and "water" not in cloud.rows


def testACloudWithoutUpgrade003SaysSo(cloud, clock, loop):
    cloud.schemaVersion = 2
    app = PcApp(config, PhoneServices(userA), AppLog(None, clock), clock, lambda: clock().date(), cloud=cloud)
    loop.run_until_complete(app.start())
    press(find(draw(AmbrosiaApp, app, app.model), "Sign in with Google", "Button"))
    assert app.model.screen == "downloading" and "needs cloud upgrade 003" in app.model.notice


def testApplyNeedsTodaysRows(cloud, clock, loop):
    """Rows fetched yesterday aren't enough for Apply (4g). The minute's fetch brings them."""
    app = pcView(cloud, clock, loop)
    app.lastFetchAt = clock() - dt.timedelta(days=1)
    app.refresh()
    assert not app.model.applyReady
    loop.run_until_complete(app.fetchNow())
    assert app.model.applyReady
    loop.run_until_complete(app.applySuggestion())
    [stored] = cloud.rows["targetChanges"].values()
    assert (stored["kcalChange"], stored["macroChangeG"], stored["fromDate"]) == (250, 63, "2026-12-06")


def testNotNowIsForgottenWithTheTab(cloud, clock, loop):
    app = pcView(cloud, clock, loop)
    app.dismissSuggestion()
    assert app.model.bulkCheck.suggestion is None
    assert pcView(cloud, clock, loop).model.bulkCheck.suggestion is not None  # a new tab asks again


def testSigningOutForgetsEverything(cloud, clock, loop):
    app = pcView(cloud, clock, loop)
    loop.run_until_complete(app.signOut())
    assert app.model.screen == "signIn" and app.store.rows("foods") == [] and app.model.notice == "Signed out."


def testTheWebsitesCodeNeverNeedsSQLite():
    """The PC view runs Python in the browser, which may have no SQLite: none of its code may import it, the generic
    foods included."""
    script = (
        "import sys\n"
        "class NoSQLite:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'sqlite3' or name.startswith('_sqlite3'):\n"
        "            raise ImportError('no SQLite in the browser')\n"
        "sys.meta_path.insert(0, NoSQLite())\n"
        "import main, ambrosia.pcApp, ambrosia.screens.root\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                            env={"PYTHONPATH": f"{repoRoot / 'apps/diet/src'}:{repoRoot / 'shared/src'}"})
    assert result.stdout.strip() == "ok", result.stderr[-2000:]


# --- Backup: Back up now and Export CSV (AM5.6) ----------------------------------------------------

def testBackUpNowWithGooglesPermissionFromTheSecondWindow(cloud, clock, loop):
    import urllib.parse

    drive = DriveStandIn()
    app = pcView(cloud, clock, loop, drive)
    app.model.tab = "backup"
    press(find(draw(AmbrosiaApp, app, app.model), "Back up now", "Button"))
    (url,) = app.services.urlLauncher.opened
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["redirect_uri"] == ["https://fingaerwen.github.io/usefulTrash/driveToken.html"]
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"] and query["state"][0].startswith("ambrosia.")
    assert drive.folders() == ["Ambrosia backups"] and len(drive.zips("Ambrosia-backup-")) == 1
    [row] = cloud.rows["dietBackups"].values()
    assert row["madeBy"] == "pcView" and app.services.prefs.values == {}  # the token is gone from the site's storage
    assert app.model.backupStatus.startswith("Backed up to your Google Drive: Ambrosia-backup-2026-12-06-")


def testAnAnswerForTalonsPcViewIsLeftAlone(cloud, clock, loop, monkeypatch):
    """Both PC views share the site's storage: an answer under Talon's key isn't Ambrosia's to take."""
    import ambrosia.pcApp

    monkeypatch.setattr(ambrosia.pcApp, "handoverWaitSec", 1)
    app = pcView(cloud, clock, loop)
    app.services.urlLauncher.answer = {"state": "talonsRequest", "accessToken": "driveToken1", "error": ""}
    loop.run_until_complete(app.backUpNow())
    assert "driveToken" in app.services.prefs.values and "dietBackups" not in cloud.rows
    assert app.model.backupStatus.startswith("No permission came back from Google")


def testExportCsvSavesAmbrosiasTablesAndTheReadableFiles(cloud, clock, loop):
    import io
    import zipfile

    app = pcView(cloud, clock, loop)
    loop.run_until_complete(app.actions.logFood(app.localToday(), "dinner", oats, "grams", 90))
    loop.run_until_complete(app.exportCsv())
    [(name, content)] = app.services.filePicker.saved.items()
    assert name == "Ambrosia-export-2026-12-06.zip" and app.model.backupStatus.startswith("Exported Ambrosia-export-")
    manifest, tables = readBackupZip(content)
    assert manifest["appName"] == "Ambrosia" and "bodyWeight" not in tables and len(tables["foodLogs"]) == 1
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert {"food.csv", "days.csv"} <= set(archive.namelist())
