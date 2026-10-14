"""Tests for the PC view (gym/pcApp.py and its screens) with the cloud stand-in: sign-in loads everything,
the Plans tab imports straight to the cloud, a failed write changes nothing, the phone's changes show up
after a fetch, and the website's code never needs SQLite."""

import asyncio
import dataclasses
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cloudStandIn import CloudStandIn
from screenTestKit import draw, find, press, useLoop, visibleTexts
from usefulTestKit import FakeClock, exampleRow, userA

from gym.pcApp import PcApp
from gym.screens.root import GymApp
from gym.tables import appSchema, tablesByName
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

    async def pick_files(self, **options):
        return self.files


class FakeClipboard:
    async def set(self, value):
        self.text = value


@dataclasses.dataclass
class Services:
    googleSignIn: FakeGoogle
    clipboard: FakeClipboard
    filePicker: FakePicker


class Browser:
    def __init__(self, cloud):
        self.cloud = cloud
        self.services = Services(FakeGoogle(), FakeClipboard(), FakePicker())
        self.clock = FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC))
        self.loop = asyncio.new_event_loop()
        useLoop(self.loop)
        self.app = PcApp(config, self.services, AppLog(None, self.clock), self.clock, lambda: monday, cloud=cloud)
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
    assert "Push · day 1 of 3 · week 0/4" in browser.texts()
    browser.app.model.tab = "plans"
    texts = browser.texts()
    assert "Active: Push Pull Legs (example) (v1) · since 12 Oct · 4/week" in texts


def testImportingAPlanWritesStraightToTheCloud(browser, cloud):
    signedIn(browser)
    browser.app.model.tab = "plans"
    assert "No plan yet." in browser.texts()
    browser.services.filePicker.files = [PickedFile("examplePlan.json",
                                                    (repoRoot / "plans" / "examplePlan.json").read_bytes())]
    press(find(browser.screen(), "Import a plan file…", "Button"))
    press(find(browser.screen(), "Import", "Button"))
    assert len(cloud.rows["plans"]) == 1
    assert "Active: Push Pull Legs (example) (v1) · since 12 Oct · 4/week" in browser.texts()


def testAFailedWriteChangesNothingOnScreen(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    browser.app.model.tab = "today"
    cloud.offline = True
    press(find(browser.screen(), "Bench Press: done as targeted", "IconButton"))
    assert browser.app.model.today.exercises[0].status == "todo"
    assert ("No connection to the cloud right now. Nothing was changed; try again in a moment."
            in browser.texts())


def testThePhonesChangesShowUpAfterAFetch(browser, cloud):
    planInCloud(cloud)
    signedIn(browser)
    cloud.clock.advance(minutes=10)
    cloud.storeDirectly("dailySteps", toCloud(tablesByName["dailySteps"], exampleRow("dailySteps", date=monday)))
    browser.run(browser.app.fetchNow())
    assert "Steps today: 14,000" in browser.texts()


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
