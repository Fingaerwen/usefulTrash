"""Ambrosia's phone app on the cloud stand-in (plan 3b phone mode, 14b, apps/diet/docs/plan.md 4e, 4g): signing in, the
first download with Talon's rows, food synced to the cloud and Talon's tables never sent, no internet, a cloud still
waiting for upgrade 003, signing out, the bulk check's Apply waiting for a sync and Not now kept on the phone, and the
Problems page."""

import asyncio
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from ambrosiaStandIn import FakeOpenFoodFacts, PhoneServices, bulkInCloud, inCloud
from cloudStandIn import CloudStandIn
from driveStandIn import DriveStandIn
from screenTestKit import draw, find, press, useLoop, visibleTexts
from usefulTestKit import FakeClock, userA

from ambrosia.phoneApp import PhoneApp
from ambrosia.rules.foods import Food, Values
from ambrosia.screens.root import AmbrosiaApp
from ambrosia.sources.openFoodFacts import OpenFoodFacts
from usefulShared.backup.backupFile import readBackupZip
from usefulShared.backup.driveApi import DriveApi
from usefulShared.platform.appLog import AppLog

repoRoot = Path(__file__).resolve().parents[2]
config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClientId"}
sixthDec = dt.date(2026, 12, 6)  # a Sunday: the first big-miss check (4g)
targetsFile = json.loads((repoRoot / "apps/diet/plans/exampleTargets.json").read_text())
oats = Food("", "usda", "Oats, whole grain, rolled", Values(379, 13.2, 6.5, 67.7), usdaId=173904)


class Phone:
    """One phone with Ambrosia: its folder, its saved sign-in and its event loop, so it can be "restarted"."""

    def __init__(self, folder: Path, cloud: CloudStandIn, clock: FakeClock):
        self.folder, self.cloud, self.clock = folder, cloud, clock
        self.services = PhoneServices(userA)
        self.drive = DriveStandIn()
        self.loop = asyncio.new_event_loop()
        useLoop(self.loop)
        self.app = self.restart()

    def restart(self) -> PhoneApp:
        net = FakeOpenFoodFacts()
        self.app = PhoneApp(config, str(self.folder), self.services, AppLog(str(self.folder), self.clock), self.clock,
                            lambda: self.clock().date(), cloud=self.cloud, drive=DriveApi(self.drive),
                            foodSource=OpenFoodFacts("0.1-alpha", net, clock=lambda: 1e12))
        self.run(self.app.start())
        return self.app

    def run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    def texts(self) -> list[str]:
        return visibleTexts(draw(AmbrosiaApp, self.app, self.app.model))

    def close(self) -> None:
        if self.app.syncLoop is not None:
            self.app.syncLoop.stop()
        if self.app.store is not None:
            self.app.store.close()
        self.loop.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(dt.datetime(2026, 12, 6, 11, 0, tzinfo=dt.UTC))


@pytest.fixture
def cloud(clock) -> CloudStandIn:
    """The cloud, with yesterday's backup in it, so no backup is due in the tests that aren't about backups."""
    standIn = CloudStandIn(clock)
    standIn.signUpsAllowedFor = {userA}
    inCloud(standIn, "dietBackups", madeAt=clock() - dt.timedelta(days=1))
    return standIn


def noBackupYet(cloud: CloudStandIn) -> None:
    cloud.rows["dietBackups"].clear()


@pytest.fixture
def phone(tmp_path, cloud, clock):
    device = Phone(tmp_path, cloud, clock)
    yield device
    device.close()


def bulk(cloud: CloudStandIn, **options) -> None:
    bulkInCloud(cloud, targetsFile, **options)


def signedIn(phone: Phone) -> Phone:
    """Signs in through the screen. Background sync is then stopped, so tests decide when rounds run."""
    press(find(draw(AmbrosiaApp, phone.app, phone.app.model), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "main", phone.app.model.notice
    phone.app.syncLoop.stop()
    return phone


# --- Starting and signing in --------------------------------------------------------------------

def testFirstStartAsksToSignIn(phone):
    assert phone.app.model.screen == "signIn"
    assert "Ambrosia" in phone.texts()
    assert find(draw(AmbrosiaApp, phone.app, phone.app.model), "Sign in with Google", "Button")


def testSignInDownloadsYourRowsAndTalonsThenShowsToday(phone, cloud):
    """The first download fetches Ambrosia's tables and the three of Talon's it reads (4e): today is a training day
    by Talon's plan."""
    plan = json.loads((repoRoot / "plans/examplePlan.json").read_text())
    inCloud(cloud, "plans", planJson=plan, effectiveDate=dt.date(2026, 10, 12))
    bulk(cloud)
    signedIn(phone)
    app = phone.app
    assert app.store.meta("firstDownloadDone") is not None
    assert len(app.store.rows("bodyWeight")) == 6 and len(app.store.rows("plans")) == 1
    assert app.model.targets.name == "Bulk from 26 Oct"
    assert "Today" in phone.texts()


def testARestartKeepsYouSignedIn(phone, cloud):
    signedIn(phone)
    phone.app.syncLoop.stop()
    phone.app.store.close()
    app = phone.restart()
    assert app.model.screen == "main" and app.userId == userA
    app.syncLoop.stop()


def testACloudWithoutUpgrade003SaysSo(phone, cloud):
    """Until you paste upgrade 003, the first download stops and says what's missing (UP1.1)."""
    cloud.schemaVersion = 2
    press(find(draw(AmbrosiaApp, phone.app, phone.app.model), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "downloading"
    assert "needs cloud upgrade 003" in phone.app.model.notice


# --- Saving and syncing -------------------------------------------------------------------------

def testFoodGoesToTheCloudAndTalonsTablesNeverDo(phone, cloud):
    bulk(cloud)
    signedIn(phone)
    app = phone.app
    phone.run(app.actions.logFood(app.localToday(), "breakfast", oats, "grams", 80))
    phone.run(app.addWater())
    assert app.model.waiting == 3  # the food, its log and the water
    outcome = phone.run(app.syncNow())
    assert (outcome.status, outcome.sent) == ("done", 3) and app.model.waiting == 0
    assert len(cloud.rows["foodLogs"]) == 1 and len(cloud.rows["foods"]) == 1 and len(cloud.rows["water"]) == 1
    sent = {call.split()[1] for call in cloud.calls if call.startswith("upsert")}
    assert sent == {"foods", "foodLogs", "water"}


def testWithoutInternetEverythingWaitsOnThePhone(phone, cloud):
    signedIn(phone)
    app = phone.app
    cloud.offline = True
    phone.run(app.actions.logFood(app.localToday(), "lunch", oats, "grams", 60))
    assert phone.run(app.syncNow()).status == "offline" and app.model.waiting == 2
    assert "Sunday 6 Dec · training day · 2 waiting" in phone.texts()  # changes not sent yet (SC1.1)
    cloud.offline = False
    assert phone.run(app.syncNow()).status == "done" and app.model.waiting == 0


def testSigningOutKeepsWhatsWaiting(phone, cloud):
    signedIn(phone)
    app = phone.app
    cloud.offline = True
    phone.run(app.addWater())
    phone.run(app.signOut())
    assert app.model.screen == "signIn" and "1 change(s) not sent yet" in app.model.notice
    assert app.store.waiting().count == 1


# --- The bulk check (4g) ------------------------------------------------------------------------

def testTheBigMissShowsOnTheCheckSunday(phone, cloud):
    bulk(cloud)
    signedIn(phone)
    view = phone.app.model.bulkCheck
    assert view.suggestion.reason == "bigMissLow" and view.suggestion.kcal == 250
    texts = phone.texts()
    assert "Bulk check: Add 250 kcal a day?" in texts
    assert "−0.20 kg against 4 weeks earlier: lower, a big miss." in texts
    assert "23 Nov - 6 Dec: 79.80 kg, 2 weigh-ins" in texts and "26 Oct - 8 Nov: 80.00 kg, 2 weigh-ins" in texts


def testApplyWaitsForTodaysSyncThenAddsTheChange(phone, cloud, clock):
    """A sync from yesterday isn't enough: a weigh-in logged late in Talon could be missing."""
    bulk(cloud)
    signedIn(phone)
    app = phone.app
    app.store.setMeta("lastSyncAt", "2026-12-05T11:00:00.000000+00:00")
    app.refresh()
    assert not app.model.applyReady
    phone.run(app.applySuggestion())
    assert "waits until Ambrosia has synced today" in app.model.notice
    assert app.state.changes == []
    phone.run(app.syncNow())
    assert app.model.applyReady
    phone.run(app.applySuggestion())
    assert app.model.notice == "Added 250 kcal a day from today."
    [change] = app.state.changes
    assert (change.kcalChange, change.macroChangeG, change.fromDate, change.checkDate) == (250, 63, sixthDec, sixthDec)
    assert app.model.today.targets.kcal == 3450 and app.model.bulkCheck.suggestion is None
    assert phone.run(app.syncNow()).sent == 1
    [stored] = cloud.rows["targetChanges"].values()
    assert (stored["reason"], stored["blockAvgKg"], stored["comparedAvgKg"], stored["rateKgPerWeek"]) == (
        "bigMissLow", 79.8, 80.0, None)


def testUndoTakesTheChangeBackAndTheSuggestionReturns(phone, cloud):
    bulk(cloud)
    signedIn(phone)
    app = phone.app
    phone.run(app.syncNow())
    phone.run(app.applySuggestion())
    phone.run(app.undoChange(sixthDec))
    assert app.state.changes == [] and app.model.today.targets.kcal == 3200
    assert app.model.bulkCheck.suggestion is not None


def testNotNowStaysOnThisPhone(phone, cloud):
    bulk(cloud)
    signedIn(phone)
    phone.app.dismissSuggestion()
    assert phone.app.model.bulkCheck.suggestion is None
    assert "Bulk check: Add 250 kcal a day?" not in phone.texts()
    phone.app.store.close()
    app = phone.restart()
    app.syncLoop.stop()
    assert app.model.bulkCheck.suggestion is None and app.model.bulkCheck.check.chosen.kcal == 250


# --- The automatic backup (AM5.6) ---------------------------------------------------------------

def testTheFirstSyncOfAStartBacksUpToAmbrosiasOwnFolder(phone, cloud):
    """Every 30 days: Ambrosia's six tables to its own Drive folder, beside its history file with food.csv and
    days.csv, recorded in dietBackups. Talon's backups table stays Talon's."""
    noBackupYet(cloud)
    bulk(cloud)
    signedIn(phone)
    app = phone.app
    phone.run(app.actions.logFood(app.localToday(), "breakfast", oats, "grams", 80))
    phone.run(app.syncNow())
    phone.run(app.backupTask)
    assert phone.drive.folders() == ["Ambrosia backups"]
    [backup] = phone.drive.zips("Ambrosia-backup-")
    manifest, tables = readBackupZip(backup["content"])
    assert manifest["appName"] == "Ambrosia" and manifest["schemaVersion"] == 3 and manifest["madeBy"] == "phone"
    assert set(tables) == {"foods", "foodLogs", "water", "dietTargets", "targetChanges", "dietBackups"}
    assert len(tables["foodLogs"]) == 1 and len(tables["dietTargets"]) == 1
    [history] = phone.drive.history("Ambrosia-history.zip")
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(history["content"])) as archive:
        assert "Oats, whole grain, rolled" in archive.read("food.csv").decode()
        assert archive.read("days.csv").decode().splitlines()[1].startswith("2026-12-06,training,303,")
    [row] = app.store.rows("dietBackups")
    assert row["fileName"] == backup["name"] and row["madeBy"] == "phone"
    assert app.store.rows("dietBackups") and "backups" not in app.store.tables
    phone.run(app.syncNow())
    assert len(cloud.rows["dietBackups"]) == 1 and "backups" not in cloud.rows


def testABackupWithin30DaysIsntRepeated(phone, cloud):
    noBackupYet(cloud)
    signedIn(phone)
    phone.run(phone.app.syncNow())
    phone.run(phone.app.backupTask)
    phone.app.syncLoop.stop()
    phone.app.store.close()
    app = phone.restart()
    app.syncLoop.stop()
    phone.run(app.syncNow())
    phone.run(app.backupTask)
    assert len(phone.drive.zips("Ambrosia-backup-")) == 1


# --- Problems (12d) -----------------------------------------------------------------------------

def testProblemsSaysTheVersionSchemaAndSync(phone, cloud):
    signedIn(phone)
    phone.run(phone.app.syncNow())
    phone.app.openProblems()
    lines = phone.app.model.problems
    assert lines[0].startswith("Ambrosia 0.1-alpha · schema 3")
    assert lines[1].startswith("Sync: up to date") and "Last backup: 5 Dec 2026 (phone) · 1 day ago" in lines
    phone.run(phone.app.copyProblems())
    assert phone.services.clipboard.text.startswith("Ambrosia 0.1-alpha")
    phone.app.closeProblems()
    assert phone.app.model.screen == "main"


def testThePhonesCodeNeedsNothingFromTalon():
    """The APK holds Ambrosia's own folder and the shared package only: nothing may import the gym app's code."""
    result = subprocess.run([sys.executable, "-c", "import ambrosia.phoneApp, ambrosia.screens.root; print('ok')"],
                            capture_output=True, text=True, timeout=60,
                            env={"PYTHONPATH": f"{repoRoot / 'apps/diet/src'}:{repoRoot / 'shared/src'}"})
    assert result.stdout.strip() == "ok", result.stderr[-2000:]
