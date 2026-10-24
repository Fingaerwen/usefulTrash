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
from driveStandIn import DriveStandIn
from screenTestKit import draw, find, press, type_, useLoop, visibleTexts
from usefulTestKit import FakeClock, userA, userB

from gym.model import appVersion
from usefulShared.backup.driveApi import DriveApi
from gym.phoneApp import PhoneApp
from gym.screens.root import GymApp
from gym.tables import appSchema, tablesByName
from usefulShared.platform.appLog import AppLog
from usefulShared.signIn.sessionKeeper import MemoryStore
from usefulShared.tables import newRowId, toCloud

repoRoot = Path(__file__).resolve().parents[2]
monday = dt.date(2026, 10, 12)
config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClientId"}


class FakeGoogle:
    """Google's account picker: hands out an ID token carrying the hashed nonce, like the real one; and Google
    Play services' Drive permission (F14.1), with a token that expires when the test says so."""

    def __init__(self, account: str = userA):
        self.account = account
        self.answer: dict | None = None  # set to act out "cancelled" or an error
        self.driveToken = "driveToken1"
        self.driveAnswer: dict | None = None  # set to act out a refusal

    async def getDriveAccess(self, interactive: bool, accountEmail: str = "") -> dict:
        return self.driveAnswer or {"status": "ok", "accessToken": self.driveToken}

    async def clearDriveToken(self, accessToken: str) -> dict:
        self.driveToken = "driveToken2"  # Play services hands out a new one next time
        return {"status": "ok"}

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


class FakeNotifier:
    """weighInNotify: remembers the daily reminder it was asked for."""

    def __init__(self):
        self.allowed = True
        self.daily: tuple | None = None
        self.weekly: tuple | None = None

    async def requestPermission(self) -> bool:
        return self.allowed

    async def scheduleDaily(self, hour: int, minute: int, title: str, body: str) -> str:
        self.daily = (hour, minute, title, body)
        return f"2026-10-13 {hour:02d}:{minute:02d}"

    async def scheduleWeekly(self, isoWeekday: int, hour: int, minute: int, title: str, body: str) -> str:
        self.weekly = (isoWeekday, hour, minute, title, body)
        return f"2026-10-16 {hour:02d}:{minute:02d}"


@dataclasses.dataclass
class Services:
    googleSignIn: FakeGoogle
    secretStore: MemoryStore
    clipboard: FakeClipboard
    filePicker: FakePicker
    notifier: FakeNotifier = dataclasses.field(default_factory=FakeNotifier)


class Phone:
    """One phone: its folder, its saved sign-in and its event loop, so it can be "restarted"."""

    def __init__(self, folder: Path, cloud: CloudStandIn):
        self.folder = folder
        self.cloud = cloud
        self.services = Services(FakeGoogle(), MemoryStore(), FakeClipboard(), FakePicker())
        self.drive = DriveStandIn()
        self.clock = FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC))
        self.loop = asyncio.new_event_loop()
        useLoop(self.loop)
        self.app = self.restart()

    def restart(self) -> PhoneApp:
        self.app = PhoneApp(config, str(self.folder), self.services, AppLog(str(self.folder), self.clock), self.clock,
                            lambda: monday, cloud=self.cloud, drive=DriveApi(self.drive))
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


def planInCloud(cloud: CloudStandIn, userId: str = userA, planJson: dict | None = None) -> None:
    """A plan imported earlier on the PC: Push Pull Legs from the example file, starting today."""
    planJson = planJson or json.loads((repoRoot / "plans" / "examplePlan.json").read_text())
    row = {"id": newRowId(), "userId": userId, "updatedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "deleted": False, "cloudUpdatedAt": None, "importedAt": dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.UTC),
           "effectiveDate": monday, "startStep": 0, "planJson": planJson, "archived": False}
    cloud.storeDirectly("plans", toCloud(tablesByName["plans"], row))


def checkEverything(phone: Phone) -> None:
    """[✓] on each of today's exercises: a whole workout, which counts (WD4.1)."""
    for index in range(len(phone.app.model.today.exercises)):
        phone.run(phone.app.check(phone.app.model.today.exercises[index]))


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
    assert "Push · Monday · week 0/3" in texts
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
    assert "Workout finished ✓ · 2,560 kg" in texts and "skipped (not done when finished)" in texts
    assert phone.run(phone.app.syncNow()).status == "done"
    assert "2 waiting" not in phone.texts()
    phone.run(phone.app.backupTask)  # the first sync of a start brings the backup (F14.1): its row is sent next
    phone.run(phone.app.syncNow())
    assert phone.app.model.waiting == 0


def testTappingCheckAgainTakesItBack(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    press(find(phone.screen(), "Bench Press: take back", "IconButton"))
    assert phone.app.model.today.exercises[0].status == "todo" and not phone.app.model.today.workoutExists


def testTappingAnExercisesNameShowsItsHowTo(phone, cloud):
    """SC7.1: tapping the name unfolds the plan's how-to under the exercise, and tapping it again folds
    it away. The example plan's Bench Press has one; Dips has none."""
    from screenTestKit import redraw

    from gym.screens.today import ExerciseRow
    planInCloud(cloud)
    signedIn(phone)
    benchLine, _, dipsLine, _ = phone.app.model.today.exercises
    row = draw(ExerciseRow, phone.app, benchLine)
    assert "How to" not in visibleTexts(row)
    press(find(row, "Bench Press: how to", "Container"))
    redraw(row)
    texts = visibleTexts(row)
    assert texts[texts.index("How to"):] == [
        "How to", "1.", "Lie back with your eyes under the bar, feet flat on the floor",
        "2.", "Grip a little wider than your shoulders", "3.", "Unrack, lower to mid-chest, pause, press back up",
        "Form", "•", "Shoulder blades squeezed together and down", "•", "Wrists straight over the elbows",
        "•", "Bum stays on the bench"]
    assert ("Setup: Flat bench in a rack; bar at the height of your straight arms, safety pins just below chest "
            "height") in texts
    assert "“pause at bottom”" in texts  # the one-line notes stay on the row
    press(find(row, "Bench Press: hide how to", "Container"))
    redraw(row)
    assert "How to" not in visibleTexts(row)

    dipsRow = draw(ExerciseRow, phone.app, dipsLine)
    press(find(dipsRow, "Dips: how to", "Container"))
    redraw(dipsRow)
    assert "Your plan has no how-to for this exercise." in visibleTexts(dipsRow)


def testALongEntrySharesTheRowWithTheName(phone, cloud):
    """Sets that differ are written with the weight once, and an exercise's name and entry share the row
    equally: a long entry (an ab machine's 6 sets) wraps instead of pushing [✓] off a phone's screen."""
    import flet as ft

    from gym.rules.today import SetDone
    from gym.screens.today import ExerciseRow
    planInCloud(cloud)
    signedIn(phone)
    bench = phone.app.model.today.exercises[0]
    phone.run(phone.app.saveSets(bench, [SetDone(reps, 80) for reps in (8, 8, 7, 6)]))
    row = draw(ExerciseRow, phone.app, phone.app.model.today.exercises[0])
    entry, name = find(row, "8 · 8 · 7 · 6 @ 80 kg", "Text"), find(row, "Bench Press", "Text")
    assert entry.expand and entry.text_align == ft.TextAlign.RIGHT
    assert name.max_lines == 2 and name.overflow == ft.TextOverflow.ELLIPSIS


def testUndoOnANewWeightFromTheScreen(phone, cloud):
    """UN1.1: a step up shows ↑new with "undo ↑"; undo shows the last weight at the top, with "redo ↑"."""
    from gym.rules.today import SetDone
    from gym.screens.today import ExerciseRow
    planInCloud(cloud)
    signedIn(phone)
    phone.run(phone.app.saveSets(phone.app.model.today.exercises[0], [SetDone(12, 80)] * 4))  # the top of 8–12
    phone.app.localToday = lambda: monday + dt.timedelta(days=7)
    phone.app.refresh()
    row = draw(ExerciseRow, phone.app, phone.app.model.today.exercises[0])
    assert "4×8 @ 82.5 kg ↑new" in visibleTexts(row)
    press(find(row, "undo ↑", "TextButton"))
    row = draw(ExerciseRow, phone.app, phone.app.model.today.exercises[0])
    assert "4×12 @ 80 kg" in visibleTexts(row) and find(row, "redo ↑", "TextButton")
    assert not phone.app.model.today.workoutExists


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


def testRestDayAndTheFlexDay(phone, cloud):
    """WD1.1: today's weekday decides; a rest day is rest, and Saturday makes up what was missed."""
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    checkEverything(phone)  # Push today (Monday)
    app.localToday = lambda: monday + dt.timedelta(days=1)  # Tuesday: a rest day
    app.refresh()
    texts = phone.texts()
    assert "Rest day · next: Pull" in texts and "Train anyway" not in texts
    app.localToday = lambda: monday + dt.timedelta(days=5)  # Saturday: Wednesday's Pull was missed
    app.refresh()
    assert "Pull · Saturday, for Wednesday · week 1/3" in phone.texts() and "Deadlift" in phone.texts()


def testADayWithOver30PercentSkippedIsMissed(phone, cloud):
    """WD4.1: a workout counts with at most 30% of its exercises skipped or not done; otherwise its day is
    missed, so the flex day makes it up. Monday's Push has 4 exercises: 1 left out counts, 2 don't."""
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    press(find(phone.screen(), "Lateral Raise: done as targeted", "IconButton"))
    phone.run(app.skip(app.model.today.exercises[2]))  # Dips skipped
    press(find(phone.screen(), "Finish workout", "Button"))  # and the walk left untouched: 2 of 4 not done
    assert "Push · Monday · week 0/3" in phone.texts()
    app.localToday = lambda: monday + dt.timedelta(days=5)
    app.refresh()
    assert "Push · Saturday, for Monday · week 0/3" in phone.texts()
    app.model.tab = "week"
    assert "Mo ✗" in phone.texts()

    app.localToday = lambda: monday
    app.model.tab = "today"
    app.refresh()
    press(find(phone.screen(), "Dips: done as targeted", "IconButton"))  # 3 of 4: it counts now
    assert "Push · Monday · week 1/3" in phone.texts()
    app.localToday = lambda: monday + dt.timedelta(days=5)
    app.refresh()
    assert "Pull · Saturday, for Wednesday · week 1/3" in phone.texts()


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
    assert any(text.startswith(f"Gym Tracker {appVersion} · schema {appSchema}") for text in texts)
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
    assert "Mon · Push" in texts and "Sun · Rest" in texts and "It takes effect today." in texts
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


# --- Progression, Progress, Week, deloads (plan 7, SC3.1, SC4.1, WD2.1, WD2.4) ----------------

def fieldLabelled(root, text: str):
    """A text field by its label (the kit's find goes by a filled-in field's value first)."""
    from screenTestKit import walk
    (field,) = [control for control in walk(root) if type(control).__name__ == "TextField" and control.label == text]
    return field


def testSettingAWeightFromToday(phone, cloud):
    from screenTestKit import redraw
    from gym.screens.today import ExerciseRow
    planInCloud(cloud)
    signedIn(phone)
    bench = phone.app.model.today.exercises[0]
    row = draw(ExerciseRow, phone.app, bench)
    press(find(row, "✎ weight", "TextButton"))
    redraw(row)
    assert fieldLabelled(row, "Mondays, kg").value == "80" and fieldLabelled(row, "Step, kg").value == "2.5"
    from gym.screens.today import WeightEditor
    editor = draw(WeightEditor, phone.app, bench.exercise, bench.trackDay, bench.targetWeightKg, bench.stepKg,
                  lambda: None)
    type_(fieldLabelled(editor, "Mondays, kg"), "85")
    type_(fieldLabelled(editor, "Step, kg"), "5")
    redraw(editor)
    press(find(editor, "Save", "Button"))
    bench = phone.app.model.today.exercises[0]
    assert (bench.targetWeightKg, bench.targetReps, bench.stepKg) == (85, 8, 5)
    assert phone.app.store.waiting().count == 2  # the weight and the step, waiting to be sent


def testAnExerciseStillAtThePlansOneKiloAsksForItsWeight(phone, cloud):
    """Your plans give every weight as 1 kg, a placeholder (PF2): Today shows "? kg", ✓ opens ▾ sets with the
    kg empty (PF3), and the weight typed in set 1 counts for the sets below (PF4)."""
    from screenTestKit import redraw, walk
    from gym.rules.today import SetDone
    from gym.screens.today import ExerciseRow, SetsEditor

    def kgFields(root):
        return [control for control in walk(root) if type(control).__name__ == "TextField" and control.label == "kg"]

    planJson = json.loads((repoRoot / "plans" / "examplePlan.json").read_text())
    planJson["week"][0]["exercises"][0]["weightKg"] = 1  # Monday's bench press
    planInCloud(cloud, planJson=planJson)
    signedIn(phone)
    bench = phone.app.model.today.exercises[0]
    row = draw(ExerciseRow, phone.app, bench)
    assert "4×8 @ ? kg" in visibleTexts(row)
    press(find(row, "Bench Press: enter the weight", "IconButton"))
    redraw(row)
    assert [field.value for field in kgFields(row)] == [""] * 4 and phone.app.store.waiting().count == 0
    editor = draw(SetsEditor, phone.app, bench, lambda: None)  # on its own: a redrawn row starts it afresh
    press(find(editor, "Save", "Button"))
    redraw(editor)
    assert "Weight: type a number, like 82.5." in visibleTexts(editor)  # set 1 needs one
    type_(kgFields(editor)[0], "60")
    redraw(editor)
    press(find(editor, "Save", "Button"))
    assert phone.app.model.today.exercises[0].logged.sets == (SetDone(8, 60),) * 4
    assert not phone.app.state.training(monday).needsWeight(bench.exercise, 0, now=True)  # next time: 60 kg


def testAMistypedStepSaysWhichField(phone, cloud):
    from screenTestKit import redraw, visibleTexts
    from gym.screens.today import WeightEditor
    planInCloud(cloud)
    signedIn(phone)
    bench = phone.app.model.today.exercises[0]
    editor = draw(WeightEditor, phone.app, bench.exercise, bench.trackDay, bench.targetWeightKg, bench.stepKg,
                  lambda: None)
    type_(fieldLabelled(editor, "Step, kg"), "a lot")
    redraw(editor)
    press(find(editor, "Save", "Button"))
    redraw(editor)
    assert "Step: type a number, like 2.5." in visibleTexts(editor)
    assert phone.app.store.waiting().count == 0  # nothing saved, the weight included


def testProgressListAndAnExercisesPage(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))  # 4×8 @ 80 kg
    phone.app.model.tab = "progress"
    texts = phone.texts()
    assert "Bench Press" in texts and "now 80 kg × 9" in texts and "PR 80 kg" in texts
    press(find(phone.screen(), "Bench Press: open", "Container"))
    texts = phone.texts()
    assert "PRs: heaviest 80 kg · 1RM ~101 kg · 8 reps @ 80 kg" in texts
    assert "Now Mon 80 kg × 9" in texts and "12 Oct  4×8 @ 80 kg · 2,560 kg" in texts
    press(find(phone.screen(), "Back", "IconButton"))
    assert phone.app.model.detail is None


def testWeekTabAndStepsForAnEarlierDay(phone, cloud):
    from gym.screens.week import DaySteps
    planInCloud(cloud)
    signedIn(phone)
    checkEverything(phone)
    phone.app.model.tab = "week"
    texts = phone.texts()
    assert "Week 12–18 Oct" in texts and "1 of 3" in texts and "Mo ✓" in texts
    phone.app.localToday = lambda: monday + dt.timedelta(days=2)
    phone.app.refresh()
    from screenTestKit import redraw
    stepsEntry = draw(DaySteps, phone.app, monday, None, lambda: None)
    type_(find(stepsEntry, "Steps on 12 Oct", "TextField"), "9,500")
    redraw(stepsEntry)
    press(find(stepsEntry, "Save", "Button"))
    assert phone.app.state.steps[monday] == 9500
    assert ("Cardio", "110 min (15 gym + 95 from steps)") in __import__(  # Monday's walk + the steps
        "gym.rules.stats", fromlist=["weekLines"]).weekLines(phone.app.model.week)


def byTooltip(root, text: str):
    """The one control with this tooltip (for buttons whose words, like "Save", repeat)."""
    from screenTestKit import walk
    (control,) = [control for control in walk(root) if getattr(control, "tooltip", None) == text]
    return control


def banner(root, text: str):
    """The banner showing this text (the tappable box around it)."""
    from screenTestKit import walk
    (box,) = [control for control in walk(root) if type(control).__name__ == "Container"
              and getattr(control.content, "value", None) == text and control.on_click is not None]
    return box


def testTheWeightTab(phone, cloud):
    """SC5.1: Friday preselected (Monday 12 Oct: the 9th), ◂ ▸ for another day, Save, then the chart and the
    last weigh-ins."""
    from screenTestKit import redraw
    planInCloud(cloud)
    signedIn(phone)
    phone.app.model.tab = "weight"
    assert "Fri 9 Oct" in phone.texts() and "No weigh-ins in this span yet." in phone.texts()
    from gym.screens.weight import WeightPage
    page = draw(WeightPage, phone.app, phone.app.model, phone.app.model.weight)
    type_(fieldLabelled(page, "kg"), "82,4")  # a comma works too
    redraw(page)
    press(find(page, "Save", "Button"))
    press(find(page, "Later day", "IconButton"))
    redraw(page)
    type_(fieldLabelled(page, "kg"), "82")
    redraw(page)
    press(find(page, "Save", "Button"))
    assert phone.app.state.weights == {dt.date(2026, 10, 9): 82.4, dt.date(2026, 10, 10): 82.0}
    texts = phone.texts()
    assert "Last 2:  82.4 · 82.0   (↓ 0.4 kg)" in texts and any(text.startswith("kg  ") for text in texts)


def testTheChartsTab(phone, cloud):
    """SC8.1: the plan's first exercise at the start, another picked from the list, a tap writes a session
    out."""
    from screenTestKit import redraw, walk
    from gym.rules.today import SetDone
    from gym.screens.charts import ExerciseChart
    planInCloud(cloud)
    signedIn(phone)
    phone.run(phone.app.saveSets(phone.app.model.today.exercises[0], [SetDone(9, 80), SetDone(8, 80)]))
    phone.app.model.tab = "charts"
    texts = phone.texts()
    assert "kg" in texts and "reps" in texts and "12 Oct" in texts and "Tap a chart to see that session." in texts
    assert phone.app.model.chart.exercise.name == "Bench Press"
    chart = draw(ExerciseChart, phone.app.model.chart)
    (detector, _) = [control for control in walk(chart) if type(control).__name__ == "GestureDetector"]
    detector.on_tap_down(type("Tap", (), {"local_position": type("At", (), {"x": 150.0, "y": 50.0})()})())
    redraw(chart)
    assert "12 Oct · 9 · 8 @ 80 kg" in visibleTexts(chart)
    phone.app.showChart("dips")
    assert phone.app.model.chart.exercise.name == "Dips" and "Nothing logged in this span yet." in phone.texts()


def testBannersForTheSummaryAndTheWeighIn(phone, cloud):
    """18.4a, BN1.1: next Monday last week's summary until it's seen (and it stays seen after a restart);
    on Friday the weigh-in until today's weight is in. Tapping one opens its tab."""
    from gym.rules.stats import summaryBanner, weighInBanner
    planInCloud(cloud)
    signedIn(phone)
    phone.app.localToday = lambda: monday + dt.timedelta(days=7)
    phone.app.refresh()
    assert summaryBanner in phone.texts()
    press(banner(phone.screen(), summaryBanner))
    assert phone.app.model.tab == "week" and "Week 12–18 Oct" in phone.texts()
    assert summaryBanner not in phone.texts()
    phone.restart()
    phone.app.localToday = lambda: monday + dt.timedelta(days=7)
    phone.app.refresh()
    assert summaryBanner not in phone.texts()

    phone.app.localToday = lambda: monday + dt.timedelta(days=11)  # Friday
    phone.app.refresh()
    press(banner(phone.screen(), weighInBanner))
    assert phone.app.model.tab == "weight"
    phone.run(phone.app.setBodyWeight(monday + dt.timedelta(days=11), 81.0))
    assert weighInBanner not in phone.texts()


def testHistoryOnThePhoneEditsTheLastSevenDays(phone, cloud):
    """HI1.1, HI1.2: ⋮ → History lists every day, a month at a time; the last 7 open with Edit, laid out like
    Today, and what's logged there goes on that day, its steps and weigh-in too; Delete this workout takes the
    workout away. Older days open with View, read-only."""
    from screenTestKit import redraw
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    app.localToday = lambda: monday + dt.timedelta(days=2)  # Wednesday
    app.refresh()
    menu = find(phone.screen(), "More", "PopupMenuButton")
    press(next(item for item in menu.items if item.content == "History"))
    assert app.model.screen == "history" and len(app.model.historyDays) == 14  # every day of October so far (HI1.2)
    texts = phone.texts()
    assert "Push · missed" in texts and "before your plan" in texts  # Monday's Push; the plan began on the 12th
    press(byTooltip(phone.screen(), "View Wed 7 Oct"))  # older than 7 days: read-only on the phone
    assert "Older than 7 days: edit it in the PC view." in phone.texts()
    press(find(phone.screen(), "◂ Days", "TextButton"))
    press(byTooltip(phone.screen(), "Edit Mon 12 Oct"))
    assert "Push · Mon 12 Oct" in phone.texts()
    press(find(phone.screen(), "Bench Press: done as targeted", "IconButton"))
    assert monday in app.state.logs and app.state.logs[monday]["benchPress"].done
    assert app.model.today.date == monday + dt.timedelta(days=2) and not app.model.today.workoutExists  # today untouched
    from gym.screens.history import DayEditor
    editor = draw(DayEditor, app, app.model, app.model.historyView)
    type_(fieldLabelled(editor, "Steps"), "9,500")
    type_(fieldLabelled(editor, "Weight, kg"), "81,6")
    redraw(editor)
    press(byTooltip(editor, "Save the steps"))
    press(byTooltip(editor, "Save the weigh-in"))
    assert app.state.steps[monday] == 9500 and app.state.weights[monday] == 81.6
    press(find(phone.screen(), "Delete this workout", "OutlinedButton"))
    assert monday not in {workout.date for workout in app.state.workouts}
    press(find(phone.screen(), "◂ Days", "TextButton"))
    press(find(phone.screen(), "Back", "IconButton"))
    assert app.model.screen == "main"


def testTheDiaryOnThePhone(phone, cloud):
    """DI1.1: History → Months: each exercise's month and the body weight; a tap unfolds its monthly chart."""
    from gym.rules.today import SetDone
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    phone.run(app.saveSets(app.model.today.exercises[0], [SetDone(9, 80), SetDone(8, 80)]))
    phone.run(app.setBodyWeight(monday, 81.0))
    app.openHistory()
    app.showHistoryMode("months")
    texts = phone.texts()
    assert "October 2026" in texts and "Bench Press" in texts and "80 kg" in texts
    assert "best 9 · 8 @ 80 kg · 1 session" in texts and "Body weight" in texts and "1 weigh-in" in texts
    from screenTestKit import walk
    (entry,) = [control for control in walk(phone.screen()) if getattr(control, "tooltip", None) == "Bench Press: show its months"]
    press(entry)
    from gym.screens.history import DiaryEntry
    assert app.state.monthlyPoints("benchPress") == ((dt.date(2026, 10, 1), 80),)


def backedUp(phone) -> list[dict]:
    return [row for row in phone.app.store.rows("backups") if not row["deleted"]]


def testTheAutomaticBackupAfterTheFirstSync(phone, cloud):
    """F14.1: after a start's first sync, when the last backup is 30+ days old: every table zipped to the
    app's Drive folder, a backups row, and the last 3 kept; within 30 days nothing happens."""
    import io
    import zipfile
    planInCloud(cloud)
    signedIn(phone)
    phone.run(phone.app.syncNow())
    phone.run(phone.app.backupTask)
    (row,) = backedUp(phone)
    (file,) = phone.drive.zips()
    assert row["driveFileId"] == file["id"] and row["madeBy"] == "phone" and row["sizeBytes"] == len(file["content"])
    names = zipfile.ZipFile(io.BytesIO(file["content"])).namelist()
    assert "manifest.json" in names and "plans.csv" in names and "exerciseLogs.csv" in names
    folder = phone.drive.files[file["parents"][0]]
    assert folder["name"] == "Gym Tracker backups"
    phone.app.openProblems()
    assert "Last backup: 12 Oct 2026 (phone) · today" in phone.texts()

    phone.restart()  # a new start within 30 days: no backup
    phone.app.syncLoop.stop()
    phone.run(phone.app.syncNow())
    phone.run(phone.app.backupTask)
    assert len(phone.drive.zips()) == 1
    for month in range(1, 4):  # 31 days on, three more times: the last 3 stay
        phone.clock.advance(days=31)
        cloud.clock.advance(days=31)
        phone.restart()
        phone.app.syncLoop.stop()
        phone.run(phone.app.syncNow())
        phone.run(phone.app.backupTask)
    assert len(backedUp(phone)) == 4 and len(phone.drive.zips()) == 3
    (history,) = phone.drive.history()  # BK1.2: one history file beside them, never rotated out
    archive = zipfile.ZipFile(io.BytesIO(history["content"]))
    assert json.loads(archive.read("manifest.json"))["kind"] == "history"
    assert {"sets.csv", "weighIns.csv", "steps.csv", "diary.csv", "plans.csv"} <= set(archive.namelist())


def testABackupRetriesOnceWithAFreshDriveToken(phone, cloud):
    """Phase 0 check 7's rule: Drive refuses an expired token, Play services hands out a new one."""
    planInCloud(cloud)
    signedIn(phone)
    phone.drive.validTokens = {"driveToken2"}  # the first token has expired
    phone.run(phone.app.syncNow())
    phone.run(phone.app.backupTask)
    assert len(backedUp(phone)) == 1


def testAFailedBackupIsOnlyLogged(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    phone.services.googleSignIn.driveAnswer = {"status": "cancelled"}  # you didn't allow Drive
    phone.run(phone.app.syncNow())
    phone.run(phone.app.backupTask)
    assert backedUp(phone) == [] and phone.app.model.notice == ""
    assert "The backup to Google Drive didn't work" in (phone.folder / "appLog.txt").read_text()


def testHistorysAllTimeView(phone, cloud):
    """DI1.2: every exercise's full chart with its PRs, then the body weight's."""
    from gym.rules.today import SetDone
    planInCloud(cloud)
    signedIn(phone)
    app = phone.app
    phone.run(app.saveSets(app.model.today.exercises[0], [SetDone(9, 80), SetDone(8, 80)]))
    phone.run(app.setBodyWeight(monday, 81.0))
    app.openHistory()
    app.showHistoryMode("all")
    texts = phone.texts()
    assert "Bench Press" in texts and any(text.startswith("PRs: heaviest 80 kg") for text in texts)
    assert "Body weight" in texts and "1 weigh-in · lowest 81 kg · highest 81 kg" in texts
    assert "Dips" not in texts  # nothing logged for it yet


def testStartingAndStoppingADeloadByHand(phone, cloud):
    planInCloud(cloud)
    signedIn(phone)
    menu = find(phone.screen(), "More", "PopupMenuButton")
    press(next(item for item in menu.items if item.content == "Start a deload"))
    texts = phone.texts()
    assert any(text.startswith("Deload week until Sun 18 Oct") for text in texts)
    assert "2×5 @ 80 kg" in texts  # half the sets, 3 reps short
    menu = find(phone.screen(), "More", "PopupMenuButton")
    press(next(item for item in menu.items if item.content == "Stop the deload"))
    assert "4×8 @ 80 kg" in phone.texts()


def testStartUpDoesntWaitForTheNotificationQuestion(phone, cloud):
    """Android's "allow notifications?" waits for your answer; Today shows meanwhile, and the start time
    isn't counting your answer."""
    planInCloud(cloud)
    answered = asyncio.Event()

    async def notAnsweredYet() -> bool:
        await asyncio.wait_for(answered.wait(), timeout=5)  # a start-up that waited would give up here
        return True

    phone.services.notifier.requestPermission = notAnsweredYet
    signedIn(phone)  # the first start: the first download, then Today
    for start in ("first", "later"):  # later: this phone's data is already downloaded
        if start == "later":
            answered.clear()
            phone.services.notifier.daily = None
            phone.restart()
        assert phone.app.model.screen == "main", start
        assert phone.app.remindersTask is not None and not phone.app.remindersTask.done(), start
        answered.set()
        phone.run(phone.app.remindersTask)
        assert phone.services.notifier.daily == (8, 0, "Creatine", "Time for your creatine"), start


def testTheRemindersAreSetCreatineDailyAndTheWeighInOnFridays(phone, cloud):
    """WD3.8, G9.1, NT1.2: set after sign-in (and again at every start); a no to notifications is only logged."""
    planInCloud(cloud)
    signedIn(phone)
    phone.run(phone.app.remindersTask)  # it runs beside start-up, which doesn't wait for it
    assert phone.services.notifier.daily == (8, 0, "Creatine", "Time for your creatine")
    assert phone.services.notifier.weekly == (5, 7, 0, "Weigh-in", "Time to weigh in")
    phone.services.notifier.daily = phone.services.notifier.weekly = None
    phone.services.notifier.allowed = False
    phone.run(phone.app.scheduleReminders())
    assert phone.services.notifier.daily is None and phone.services.notifier.weekly is None
    assert "there are no reminders" in (phone.folder / "appLog.txt").read_text()
