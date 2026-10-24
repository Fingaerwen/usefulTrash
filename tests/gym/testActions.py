"""Tests for Today's actions and the facts behind them (gym/actions.py, gym/state.py), on a real phone
database: ✓, sets, skip, Finish and steps, and what each does to the week."""

import asyncio
import dataclasses
import datetime as dt

import pytest
from usefulTestKit import FakeClock, userA

from gym.actions import ActionRefused, GymActions
from gym.phoneSteps import phoneSteps
from gym.rules.today import SetDone
from gym.state import GymState
from gym.tables import appTables
from usefulShared.store.phoneStore import PhoneStore, runPhoneSteps
from usefulShared.tables import newRowId

monday = dt.date(2026, 10, 12)
tuesday, saturday = monday + dt.timedelta(days=1), monday + dt.timedelta(days=5)
planFile = {
    "planId": "pushPullLegs", "name": "Push Pull Legs", "version": 1, "weeklyTarget": 2,
    "week": [
        {"day": "monday", "title": "Push", "exercises": [
            {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
             "sets": 4, "repsMin": 8, "repsMax": 12, "weightKg": 82.5},
            {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight", "sets": 3, "repsMin": 8, "repsMax": 12},
            {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15}]},
        {"day": "tuesday", "title": "Rest", "restDay": True},
        {"day": "wednesday", "title": "Pull", "exercises": [
            {"exerciseId": "deadlift", "name": "Deadlift", "equipment": "barbell", "body": "lower",
             "sets": 3, "repsMin": 5, "repsMax": 8, "weightKg": 140}]},
        {"day": "thursday", "title": "Rest", "restDay": True},
        {"day": "friday", "title": "Rest", "restDay": True},
        {"day": "saturday", "title": "Flex", "makeUp": ["monday", "wednesday"], "exercises": [
            {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15}]},
        {"day": "sunday", "title": "Rest", "restDay": True},
    ],
}


class App:
    """The pieces the phone app wires together: database, facts, actions."""

    def __init__(self, folder):
        path = str(folder / "gym.sqlite3")
        runPhoneSteps(path, phoneSteps)
        self.clock = FakeClock(dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.UTC))
        self.database = PhoneStore(path, appTables, self.clock)
        self.database.claimFor(userA)
        self.state = GymState()
        self.actions = GymActions(self, self.state, userA, self.clock)
        self.database.save("plans", {
            "id": newRowId(), "userId": userA, "deleted": False, "importedAt": self.clock(),
            "effectiveDate": monday, "startStep": 0, "planJson": planFile, "archived": False})
        self.reload()

    async def saveRows(self, edits):
        """The RowStore the actions use: save in one transaction, then work out the facts again."""
        saved = self.database.saveMany(edits)
        self.reload()
        return saved

    def reload(self):
        self.state.load({table.name: self.database.rows(table.name) for table in appTables})

    def do(self, action, *args):
        asyncio.run(action(*args))

    def today(self, date=monday):
        return self.state.today(date)


@pytest.fixture
def app(tmp_path) -> App:
    return App(tmp_path)


def line(view, exerciseId):
    return next(line for line in view.exercises if line.exercise.exerciseId == exerciseId)


def testCheckLogsTheTargetAndStartsTheWorkout(app):
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    view = app.today()
    bench = line(view, "benchPress")
    assert bench.status == "done" and bench.logged.sets == (SetDone(8, 82.5),) * 4
    assert view.workoutExists and not view.finished
    (session,) = app.database.rows("sessions")
    assert (session["planImportId"], session["stepIndex"], session["date"]) == (view.planImportId, 0, monday)
    assert app.database.waiting().count == 3  # the plan, the workout day and the exercise


def testCheckWontLogThePlansOneKiloPlaceholder(app):
    """Today opens ▾ sets instead (PF3); the action refuses too, so 1 kg never lands in your history."""
    view = app.today()
    placeholder = dataclasses.replace(line(view, "benchPress"), targetWeightKg=None, needsWeight=True)
    with pytest.raises(ActionRefused, match="▾ sets"):
        app.do(app.actions.checkExercise, view, placeholder)
    assert app.database.rows("exerciseLogs") == []


def testCheckingAgainTakesItBackAndTheWorkoutWithIt(app):
    """A mistaken tap mustn't count as a workout: with nothing left logged, the workout goes too."""
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    view = app.today()
    assert line(view, "benchPress").status == "todo" and not view.workoutExists
    assert app.today(saturday).title == "Push"  # Monday counts as missed, so Saturday makes it up


def testTakingBackOneOfTwoKeepsTheWorkout(app):
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    app.do(app.actions.skipExercise, app.today(), line(app.today(), "dips"))
    app.do(app.actions.checkExercise, app.today(), line(app.today(), "benchPress"))
    view = app.today()
    assert [entry.status for entry in view.exercises] == ["todo", "skipped", "todo"]
    assert view.workoutExists


def testSetsAsDone(app):
    view = app.today()
    app.do(app.actions.saveSets, view, line(view, "benchPress"), [SetDone(9, 82.5), SetDone(8, 82.5), SetDone(6, 80)])
    assert line(app.today(), "benchPress").logged.sets == (SetDone(9, 82.5), SetDone(8, 82.5), SetDone(6, 80.0))
    app.do(app.actions.saveSets, app.today(), line(app.today(), "dips"), [SetDone(12), SetDone(10)])
    assert line(app.today(), "dips").logged.sets == (SetDone(12), SetDone(10))
    app.do(app.actions.saveSets, app.today(), line(app.today(), "inclineWalk"), [], 20)
    assert line(app.today(), "inclineWalk").logged.minutes == 20


@pytest.mark.parametrize(("exerciseId", "sets", "message"), [
    ("benchPress", [SetDone(-1, 80)], "Reps must be a whole number"),
    ("benchPress", [SetDone(8, 82.555)], "at most 2 decimals"),
    ("benchPress", [SetDone(8, None)], "Weight must be a number"),
    ("dips", [SetDone(8, 10)], "no weight"),
])
def testImpossibleSetsAreRefusedInPlainWords(app, exerciseId, sets, message):
    view = app.today()
    with pytest.raises(ActionRefused, match=message):
        app.do(app.actions.saveSets, view, line(view, exerciseId), sets)
    assert app.database.rows("exerciseLogs") == []


def testCardioCheckLogsTheTargetMinutes(app):
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "inclineWalk"))
    logged = line(app.today(), "inclineWalk").logged
    assert (logged.minutes, logged.sets) == (15, ())


def testFinishAutoSkipsWhatsLeft(app):
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    app.do(app.actions.finishWorkout, app.today())
    view = app.today()
    assert view.finished and [entry.status for entry in view.exercises] == ["done", "autoSkipped", "autoSkipped"]
    (session,) = app.database.rows("sessions")
    assert session["finishedAt"] == app.clock()
    assert app.today(tuesday).weekDone == 1


def testLoggingAfterFinishAddsToTheSameWorkout(app):
    """One workout per day (DT1.1): later entries join it, and it stays finished."""
    view = app.today()
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    app.do(app.actions.finishWorkout, app.today())
    app.do(app.actions.checkExercise, app.today(), line(app.today(), "inclineWalk"))
    view = app.today()
    assert view.finished and line(view, "inclineWalk").status == "done"
    assert len(app.database.rows("sessions")) == 1


def testFinishingTwiceKeepsTheFirstTime(app):
    app.do(app.actions.checkExercise, app.today(), line(app.today(), "benchPress"))
    app.do(app.actions.finishWorkout, app.today())
    finishedAt = app.clock()
    app.clock.advance(minutes=30)
    app.do(app.actions.finishWorkout, app.today())
    assert app.database.rows("sessions")[0]["finishedAt"] == finishedAt


def testTakingBackTheLastEntryRemovesEvenAFinishedWorkout(app):
    app.do(app.actions.checkExercise, app.today(), line(app.today(), "benchPress"))
    app.do(app.actions.finishWorkout, app.today())
    app.do(app.actions.checkExercise, app.today(), line(app.today(), "benchPress"))
    assert not app.today().workoutExists
    assert app.today(tuesday).weekDone == 0


def testFinishWithNothingLoggedDoesNothing(app):
    app.do(app.actions.finishWorkout, app.today())
    assert app.database.rows("sessions") == []


def testTheFlexDayLogsTheSessionItMakesUp(app):
    """WD1.1: Monday was missed, so Saturday's workout is Monday's Push, and it's saved as Monday's."""
    view = app.today(saturday)
    assert (view.title, view.makesUp) == ("Push", "Monday")
    app.do(app.actions.checkExercise, view, line(view, "benchPress"))
    (session,) = app.database.rows("sessions")
    assert (session["date"], session["stepIndex"]) == (saturday, 0)
    assert app.today(saturday).makesUp == "Monday"
    sunday = app.today(saturday + dt.timedelta(days=1))
    assert sunday.isRestDay and sunday.nextWorkoutTitle == "Push"


def testStepsEnteredReplacedAndCleared(app):
    app.do(app.actions.setSteps, monday, 14000)
    app.do(app.actions.setSteps, monday, 15200)
    assert app.today().stepsToday == 15200 and len(app.database.rows("dailySteps")) == 1
    app.do(app.actions.setSteps, monday, None)
    assert app.today().stepsToday is None
    with pytest.raises(ActionRefused, match="from 0 to 200,000"):
        app.do(app.actions.setSteps, monday, 250000)


def testStepsAreNeverAWorkout(app):
    app.do(app.actions.setSteps, monday, 14000)
    assert not app.today().workoutExists
    assert app.today(tuesday).weekDone == 0


def testAPlanThatCantBeReadIsListedNotFatal(app):
    app.database.save("plans", {"id": newRowId(), "userId": userA, "deleted": False, "importedAt": app.clock(),
                                "effectiveDate": monday, "startStep": 0, "planJson": {"name": "broken"},
                                "archived": False})
    app.reload()
    assert len(app.state.unreadablePlans) == 1 and app.today().title == "Push"


# --- Progression on Today (plan 7), weights and steps set in the app (WD2.1, WD3.7) -------------

def nextMonday(n: int = 1) -> dt.date:
    return monday + dt.timedelta(days=7 * n)


def testTodaysTargetsComeFromProgression(app):
    view = app.today()
    app.do(app.actions.saveSets, view, line(view, "benchPress"), [SetDone(9, 82.5), SetDone(9, 82.5),
                                                                  SetDone(10, 82.5), SetDone(9, 82.5)])
    nextWeek = line(app.today(nextMonday()), "benchPress")
    assert (nextWeek.targetSets, nextWeek.targetReps, nextWeek.targetWeightKg) == (4, 10, 82.5)
    assert nextWeek.trackDay == 0 and nextWeek.stepKg == 2.5


def testSettingAWeightRestartsThatDayAtRepsMin(app):
    app.do(app.actions.setWeight, "benchPress", 0, 90, monday, False)
    bench = line(app.today(), "benchPress")
    assert (bench.targetReps, bench.targetWeightKg) == (8, 90)
    (row,) = app.database.rows("exerciseWeights")
    assert (row["weekday"], row["fromDate"]) == (0, monday)
    app.do(app.actions.setWeight, "benchPress", 0, 92.5, monday, True)  # done today: from tomorrow on
    rows = sorted(app.database.rows("exerciseWeights"), key=lambda row: row["fromDate"])
    assert [(row["weightKg"], row["fromDate"]) for row in rows] == [(90, monday), (92.5, monday + dt.timedelta(days=1))]
    assert line(app.today(), "benchPress").targetWeightKg == 90  # each change is kept, from its own day
    assert line(app.today(nextMonday()), "benchPress").targetWeightKg == 92.5
    with pytest.raises(ActionRefused, match="Weight must be"):
        app.do(app.actions.setWeight, "benchPress", 0, 82.555, monday, False)


def testSettingAWeightStep(app):
    app.do(app.actions.setStep, "benchPress", 1.25, monday)
    app.clock.advance(minutes=1)
    app.do(app.actions.setStep, "benchPress", 5, monday)
    assert line(app.today(), "benchPress").stepKg == 5  # the later change on a day wins
    assert sorted(row["incrementKg"] for row in app.database.rows("exerciseSteps")) == [1.25, 5]
    assert {row["fromDate"] for row in app.database.rows("exerciseSteps")} == {monday}
    with pytest.raises(ActionRefused, match="weight step"):
        app.do(app.actions.setStep, "benchPress", 0, monday)


# --- Deloads by hand (WD2.4, WD3.4) ---------------------------------------------------------------

def testADeloadByHandStartsTodayOrTomorrow(app):
    app.do(app.actions.startDeload, monday, False)
    view = app.today()
    assert view.deload is not None and view.deload.reason == "manual"
    bench = line(view, "benchPress")
    assert (bench.targetSets, bench.targetReps) == (2, 5)  # half of 4, 3 short of 8
    with pytest.raises(ActionRefused, match="already"):
        app.do(app.actions.startDeload, monday, False)
    app.do(app.actions.stopDeload, monday)
    assert app.today().deload is None
    app.do(app.actions.startDeload, monday, True)  # a workout is logged today: from tomorrow
    assert app.today().nextDeload.start == monday + dt.timedelta(days=1)
