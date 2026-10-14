"""Tests for the phone app's controller and its screens together (gym/phoneApp.py, gym/screens/), with
the cloud stand-in and fake phone abilities: sign-in with the nonce check, the first download, Today's
buttons, Problems, signing out, and the plan file fallback. The screens are drawn for real (see
tests/screenTestKit.py) and their buttons pressed."""

import asyncio
import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest
from cloudStandIn import CloudStandIn
from screenTestKit import draw, find, press, type_, useLoop, visibleTexts
from usefulTestKit import FakeClock, userA, userB

from gym.phoneApp import PhoneApp
from gym.screens.root import GymApp
from gym.tables import tablesByName
from usefulShared.platform.appLog import AppLog
from usefulShared.signIn.sessionKeeper import MemoryStore
from usefulShared.tables import newRowId, toCloud

repoRoot = Path(__file__).resolve().parents[2]
monday = dt.date(2026, 10, 12)
config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClientId"}


class FakeGoogle:
    """Google's account picker: hands out an ID token carrying the hashed nonce, like the real one."""

    def __init__(self, account: str = userA):
        self.account = account
        self.answer: dict | None = None  # set to act out "cancelled" or an error

    async def getIdToken(self, serverClientId: str, hashedNonce: str) -> dict:
        return self.answer or {"status": "ok", "idToken": f"googleIdToken:{self.account}:{hashedNonce}"}

    async def clearSignInState(self) -> dict:
        return {"status": "ok"}


@dataclasses.dataclass
class PickedFile:
    name: str
    bytes: bytes


class FakePicker:
    def __init__(self):
        self.files: list[PickedFile] = []

    async def pick_files(self, **options) -> list[PickedFile]:
        return self.files


class FakeClipboard:
    def __init__(self):
        self.text = ""

    async def set(self, value: str) -> None:
        self.text = value


@dataclasses.dataclass
class Services:
    googleSignIn: FakeGoogle
    secretStore: MemoryStore
    clipboard: FakeClipboard
    filePicker: FakePicker


class Phone:
    """One phone: its folder, its saved sign-in and its event loop, so it can be "restarted"."""

    def __init__(self, folder: Path, cloud: CloudStandIn):
        self.folder = folder
        self.cloud = cloud
        self.services = Services(FakeGoogle(), MemoryStore(), FakeClipboard(), FakePicker())
        self.clock = FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC))
        self.loop = asyncio.new_event_loop()
        useLoop(self.loop)
        self.app = self.restart()

    def restart(self) -> PhoneApp:
        self.app = PhoneApp(config, str(self.folder), self.services, AppLog(str(self.folder), self.clock), self.clock,
                            lambda: monday, cloud=self.cloud)
        self.run(self.app.start())
        return self.app

    def run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    def screen(self):
        """The whole app as drawn right now."""
        return draw(GymApp, self.app, self.app.model)

    def texts(self) -> list[str]:
        return visibleTexts(self.screen())

    def close(self):
        if self.app.syncLoop is not None:
            self.app.syncLoop.stop()
        self.loop.run_until_complete(asyncio.sleep(0))
        self.loop.close()


@pytest.fixture
def cloud() -> CloudStandIn:
    standIn = CloudStandIn(FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC)))  # the phone's time too
    standIn.signUpsAllowedFor = {userA}
    return standIn


@pytest.fixture
def phone(tmp_path, cloud):
    device = Phone(tmp_path, cloud)
    yield device
    device.close()


def planInCloud(cloud: CloudStandIn, userId: str = userA) -> None:
    """A plan imported earlier on the PC: Push Pull Legs from the example file, starting today."""
    planJson = json.loads((repoRoot / "plans" / "examplePlan.json").read_text())
    row = {"id": newRowId(), "userId": userId, "updatedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "deleted": False, "cloudUpdatedAt": None, "importedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "effectiveDate": monday, "startStep": 0, "planJson": planJson, "archived": False}
    cloud.storeDirectly("plans", toCloud(tablesByName["plans"], row))


def signedIn(phone: Phone) -> Phone:
    """Signs in through the screen. Background sync is then stopped, so tests decide when rounds run."""
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "main", phone.app.model.notice
    phone.app.syncLoop.stop()
    return phone


# --- Starting and signing in --------------------------------------------------------------------

def testFirstStartAsksToSignIn(phone):
    assert phone.app.model.screen == "signIn"
    assert "Gym Tracker" in phone.texts()


def testSignInDownloadsEverythingThenShowsToday(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    texts = phone.texts()
    assert "Push · day 1 of 3 · week 0/4" in texts
    assert "Bench Press" in texts and "4×8 @ 80 kg" in texts
    assert phone.app.store.meta("firstDownloadDone") is not None


def testAWrongNonceAcceptedStopsSignInForSafety(phone, cloud):
    """If Supabase's nonce check were switched off, sign-in refuses to go on (F9)."""
    cloud.acceptsWrongNonce = True
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "signIn" and not phone.app.session.isSignedIn()
    assert "Sign-in was stopped for safety. Details are on the Problems page." in phone.texts()


def testAnotherGoogleAccountIsNotAllowed(phone, cloud):
    phone.services.googleSignIn.account = userB
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert "This Google account isn't allowed in this app." in phone.texts()


def testCancellingGooglesPickerChangesNothing(phone):
    phone.services.googleSignIn.answer = {"status": "cancelled"}
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "signIn" and phone.app.model.notice == "" and phone.app.model.busy == ""


def testFirstDownloadWithoutInternetOffersTryAgain(phone, cloud):
    """Signed in, then the connection drops before the download: Today waits, with Try again."""
    planInCloud(cloud)
    cloud.callsUntilOffline = 0  # sign-in itself goes through; the download's first request doesn't
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert phone.app.model.screen == "downloading"
    assert "No internet: the first download needs it. Tap Try again when you're online." in phone.texts()
    cloud.offline, cloud.callsUntilOffline = False, None
    press(find(phone.screen(), "Try again", "Button"))
    assert phone.app.model.screen == "main" and "Bench Press" in phone.texts()


def testAFolderThatCantBeOpenedShowsWhy(tmp_path, cloud):
    device = Phone(tmp_path / "missing", cloud)
    try:
        assert device.app.model.screen == "failed"
        assert any("can't be opened" in text for text in device.texts())
    finally:
        device.close()


def testRestartingKeepsYouSignedIn(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    phone.restart()
    assert phone.app.model.screen == "main"
    assert "Bench Press" in phone.texts()


# --- Today --------------------------------------------------------------------------------------

def testCheckThenFinishFromTheScreen(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    assert phone.app.model.today.exercises[0].status == "done"
    assert "2 waiting" in phone.texts()  # the workout day and the exercise, until sync sends them (SC1.1)
    press(find(phone.screen(), "Finish workout", "Button"))
    texts = phone.texts()
    assert "Workout finished ✓" in texts and "skipped (not done when finished)" in texts
    assert phone.run(phone.app.syncNow()).status == "done"
    assert "2 waiting" not in phone.texts() and phone.app.model.waiting == 0


def testTappingCheckAgainTakesItBack(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    press(find(phone.screen(), "Bench Press: take back", "IconButton"))
    assert phone.app.model.today.exercises[0].status == "todo" and not phone.app.model.today.workoutExists


def testStepsEditing(phone, cloud):
    from gym.screens.today import StepsLine
    planInCloud(cloud)
    signedIn(phone)
    stepsLine = draw(StepsLine, phone.app, None)
    press(find(stepsLine, "Enter steps", "IconButton"))
    from screenTestKit import redraw
    redraw(stepsLine)
    type_(find(stepsLine, "Steps today", "TextField"), "14.000")
    redraw(stepsLine)
    press(find(stepsLine, "Save", "Button"))
    assert phone.app.model.today.stepsToday == 14000


def testRestDayAndTrainAnyway(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))  # Push today (Monday)
    app.localToday = lambda: monday + dt.timedelta(days=1)  # Tuesday: the plan's Rest step
    app.refresh()
    assert "Rest day · next: Pull" in phone.texts()
    press(find(phone.screen(), "Train anyway", "OutlinedButton"))
    assert "Deadlift" in phone.texts()


def testARefusedEntryShowsWhy(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    from gym.rules.today import SetDone
    line = phone.app.model.today.exercises[0]
    phone.run(phone.app.saveSets(line, [SetDone(8, 82.555)]))
    assert "Weight must be a number from 0 to 1000 kg, with at most 2 decimals." in phone.texts()
    press(find(phone.screen(), "Close", "IconButton"))
    assert phone.app.model.notice == ""


# --- Problems, signing out ----------------------------------------------------------------------

def testProblemsPageCopiesAReportWithoutSecrets(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    menuItem = next(item for item in find(phone.screen(), "More", "PopupMenuButton").items if item.content == "Problems")
    press(menuItem)
    texts = phone.texts()
    assert "Problems" in texts
    assert any(text.startswith("Gym Tracker 0.1-alpha · schema 1") for text in texts)
    press(find(phone.screen(), "Copy", "Button"))
    copied = phone.services.clipboard.text
    session = phone.app.session.session
    assert copied and session["access_token"] not in copied and session["refresh_token"] not in copied
    assert "testAccount" not in copied  # the account's email address is never in the report
    assert "Log check:" in copied and "0 token-shaped strings" in copied
    press(find(phone.screen(), "Back", "IconButton"))
    assert phone.app.model.screen == "main"


def testSigningOutKeepsWhatsNotSentYet(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    cloud.offline = True
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    cloud.offline = False
    signOut = next(item for item in find(phone.screen(), "More", "PopupMenuButton").items if item.content == "Sign out")
    press(signOut)
    assert phone.app.model.screen == "signIn"
    assert phone.app.store.waiting().count >= 1
    assert any("not sent yet stay on this phone" in text for text in phone.texts())


def testWhenTheCloudEndsTheSignInYouAreAskedAgain(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    cloud.refreshTokens.clear()  # every refresh token is now dead
    phone.app.session.session["expires_at"] = 0  # so the next sync must renew
    phone.run(phone.app.syncNow())
    assert phone.app.model.screen == "signIn"
    assert "You were signed out. Please sign in again." in phone.texts()


# --- Plan file fallback (G2b-2) -----------------------------------------------------------------

def testImportingAPlanFileOnThePhone(phone, cloud):
    signedIn(phone)
    assert "Import your plan in the PC view." in phone.texts()
    phone.services.filePicker.files = [PickedFile("examplePlan.json",
                                                  (repoRoot / "plans" / "examplePlan.json").read_bytes())]
    press(find(phone.screen(), "Import a file", "OutlinedButton"))
    assert phone.app.model.screen == "importPlan"
    texts = phone.texts()
    assert "Start on:" in texts and "It takes effect today." in texts
    press(find(phone.screen(), "Import", "Button"))
    assert phone.app.model.screen == "main"
    assert "Plan imported. It takes effect today." in phone.texts()
    assert "Bench Press" in phone.texts()


def testABrokenPlanFileListsItsProblems(phone, cloud):
    signedIn(phone)
    phone.services.filePicker.files = [PickedFile("broken.json", b'{"planId": "x"}')]
    press(find(phone.screen(), "Import a file", "OutlinedButton"))
    texts = phone.texts()
    assert "• The plan: \"name\" is missing." in texts
    press(find(phone.screen(), "Cancel", "IconButton"))
    assert phone.app.model.screen == "main"


def testAPhoneClockFarAheadShowsABannerAndTheReason(phone, cloud):
    """The cloud refuses edits stamped over 5 minutes ahead of its clock (14): banner + Problems."""
    planInCloud(cloud)
    signedIn(phone)
    phone.clock.advance(hours=1)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    phone.run(phone.app.syncNow())
    assert "The cloud refused a change. See Problems (⋮)." in phone.texts()
    phone.app.openProblems()
    assert "Refused: Your phone's clock seems to be ahead. Set it to automatic time, then tap Try again." in phone.texts()
    phone.clock.advance(hours=-1)
    cloud.clock.advance(hours=1)  # the clock is right now (cloud and phone agree)
    press(find(phone.screen(), "Try again", "OutlinedButton"))
    phone.run(phone.app.syncNow())
    assert phone.app.model.waiting == 0 and phone.app.model.banners == ()


def testSignInRenewalAndSyncLeaveNoTokenInTheLog(phone, cloud):
    """12d: a full run (sign-in, a renewal, sync rounds, a refused change, going offline) must leave no
    token value in the log file. Every token the cloud ever issued is looked for in the raw file."""
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    phone.run(phone.app.syncNow())
    phone.app.session.session["expires_at"] = 0  # forces a renewal on the next round
    phone.clock.advance(hours=1)
    press(find(phone.screen(), "Dips: done as targeted", "IconButton"))  # refused: clock an hour ahead
    phone.run(phone.app.syncNow())
    cloud.offline = True
    phone.run(phone.app.syncNow())
    cloud.offline = False
    phone.run(phone.app.signOut())
    issued = list(cloud.signedIn) + [f"refresh{number}" for number in range(1, 20)]
    logText = (phone.folder / "appLog.txt").read_text()
    assert "sync" in logText and "signIn" in logText  # the run was logged…
    assert [token for token in issued if token in logText] == []  # …without a single token


def testTheNonceCheckIsNeverSkippedForAMomentWithoutInternet(phone, cloud):
    """If the wrong-nonce request is lost, nothing is proven: sign-in stops instead of going on unchecked."""
    cloud.dropNextSignIn = True
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert not phone.app.session.isSignedIn()
    assert "No internet: signing in needs it." in phone.texts()


def testAnotherAccountSigningInStartsFromNothing(phone, cloud):
    """14b: the phone's database is cleared if a different account ever signs in (sign-ups are off today)."""
    cloud.signUpsAllowedFor = {userA, userB}
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    phone.run(phone.app.signOut())
    phone.services.googleSignIn.account = userB
    press(find(phone.screen(), "Sign in with Google", "Button"))
    assert phone.app.store.owner() == userB
    assert phone.app.store.rows("plans") == [] and phone.app.store.rows("exerciseLogs") == []
    assert "Import your plan in the PC view." in phone.texts()


def testTheLogScrubsTheSessionsOwnTokens(phone, cloud):
    """Even if some code wrongly wrote a token into the log, the scrubber knows the current ones."""
    signedIn(phone)
    session = phone.app.session.session
    phone.app.log.problem("test", "a careless line", f"{session['access_token']} {session['refresh_token']}")
    logText = (phone.folder / "appLog.txt").read_text()
    assert session["access_token"] not in logText and session["refresh_token"] not in logText
