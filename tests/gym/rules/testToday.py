"""Tests for what Today shows (plan 6, SC2.1, WD1.1): the weekday's session, targets, logged and skipped
exercises, rest days, the flex day and its moves, the week's count and the header line."""

import datetime as dt
import json

from gym.rules.planFile import checkPlan, planExercises, scheduleDays
from gym.rules.schedule import LoggedWorkout, PlanStart
from gym.rules.today import (
    ImportedPlan,
    LoggedExercise,
    SetDone,
    clockText,
    headerParts,
    headerText,
    restLeft,
    targetText,
    todayView,
    workoutProgress,
)

monday = dt.date(2026, 10, 12)
upper, lowerA, push, pull, lowerB, flex, sunday = range(7)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def machine(exerciseId: str, name: str, sets: int = 3, **settings) -> dict:
    return {"exerciseId": exerciseId, "name": name, "equipment": "machine", "incrementKg": 5, "sets": sets,
            "repsMin": 10, "repsMax": 15, "weightKg": 30, **settings}


planFile = {
    "planId": "upperLowerPushPull", "name": "Upper Lower Push Pull", "version": 1, "weeklyTarget": 5,
    "week": [
        {"day": "monday", "title": "Upper", "exercises": [
            {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
             "platesPerSide": True, "barKg": 20, "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 25,
             "restSec": 150, "notes": "pause on the chest"},
            {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight", "sets": 3, "repsMin": 8, "repsMax": 12},
            {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15}]},
        {"day": "tuesday", "title": "Lower A", "exercises": [machine("seatedLegCurl", "Seated Leg Curl", sets=4)]},
        {"day": "wednesday", "title": "Push", "exercises": [
            {"exerciseId": "overheadPress", "name": "Overhead Press", "equipment": "barbell", "body": "upper",
             "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 40}]},
        {"day": "thursday", "title": "Pull", "exercises": [
            {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight", "sets": 3, "repsMin": 5,
             "repsMax": 10}]},
        {"day": "friday", "title": "Lower B", "exercises": [
            machine("seatedLegCurl", "Seated Leg Curl", sets=3), machine("rearDelt", "Rear Delt Machine"),
            machine("wristCurl", "Behind-the-Back Wrist Curl", sets=2)]},
        {"day": "saturday", "title": "Flex", "makeUp": ["monday", "thursday", "wednesday", "tuesday", "friday"],
         "moves": [{"exerciseId": "wristCurl", "from": "friday", "to": "saturday", "when": ["monday", "thursday"]},
                   {"exerciseId": "rearDelt", "from": "friday", "to": "thursday", "when": ["wednesday"]}],
         "exercises": [machine("abMachine", "Ab Machine")]},
        {"day": "sunday", "title": "Rest", "restDay": True},
    ],
}
plan = checkPlan(planFile).plan
imported = ImportedPlan(
    PlanStart("p1", monday, dt.datetime(2026, 10, 12, 6, tzinfo=dt.UTC), scheduleDays(plan), plan.weeklyTarget),
    plan)
known = planExercises(plan)


def workout(n: int, stepIndex: int | None = None, finished: bool = True, planImportId: str = "p1") -> LoggedWorkout:
    """A workout on day(n), by default that weekday's own session."""
    return LoggedWorkout(day(n), planImportId, day(n).weekday() if stepIndex is None else stepIndex, finished)


def trained(*days: int) -> list[LoggedWorkout]:
    return [workout(n) for n in days]


def view(today: dt.date, workouts=(), logs=None, steps=None, plans=(imported,)):
    return todayView(list(plans), list(workouts), logs or {}, known, steps, today)


def ids(today) -> list[str]:
    return [line.exercise.exerciseId for line in today.exercises]


def testNoPlanYet():
    today = view(day(0), plans=(), steps=9500)
    assert (today.hasPlan, today.exercises, today.stepsToday) == (False, (), 9500)
    assert headerText(today) == "Today"


def testTheWeekdaysSessionWithItsTargets():
    today = view(day(0))
    assert headerText(today) == "Upper · Monday · week 0/5"
    assert [(line.exercise.name, targetText(line), line.status) for line in today.exercises] == [
        ("Bench Press", "3×6 @ 25 kg/side", "todo"), ("Dips", "3×8", "todo"), ("Incline Walk", "15 min", "todo")]
    assert (today.planImportId, today.stepIndex, today.workoutExists, today.isRestDay) == ("p1", upper, False, False)
    assert today.exercises[0].exercise.notes == "pause on the chest"


def testAMissedDayDoesntShiftTheNextOne():
    today = view(day(1))
    assert (today.title, today.stepIndex) == ("Lower A", lowerA)
    assert headerText(today) == "Lower A · Tuesday · week 0/5"


def testSetsMayDifferBetweenDays():
    """WD1.4: one exercise, 4 sets on Tuesday and 3 on Friday."""
    assert targetText(view(day(1)).exercises[0]) == "4×10 @ 30 kg"
    assert targetText(view(day(4), trained(0, 1, 2, 3)).exercises[0]) == "3×10 @ 30 kg"


def testLoggedAndSkippedExercises():
    logs = {"benchPress": LoggedExercise("benchPress", (SetDone(9, 25),) * 3),
            "dips": LoggedExercise("dips", skipped=True)}
    today = view(day(0), [workout(0, finished=False)], logs)
    assert [line.status for line in today.exercises] == ["done", "skipped", "todo"]
    assert today.exercises[0].logged.sets[0] == SetDone(9, 25)
    assert (today.workoutExists, today.finished) == (True, False)


def testFinishedWorkoutAutoSkipsWhatsLeft():
    """19.1b-1: anything untouched when you tap Finish counts as skipped."""
    logs = {"benchPress": LoggedExercise("benchPress", (SetDone(8, 25),) * 3)}
    today = view(day(0), [workout(0)], logs)
    assert [line.status for line in today.exercises] == ["done", "autoSkipped", "autoSkipped"]
    assert today.finished


def testRestDaySaysWhatComesNext():
    today = view(day(6), trained(0, 1, 2, 3, 4))
    assert (today.isRestDay, today.title, today.nextWorkoutTitle, today.exercises) == (True, "Rest", "Upper", ())
    assert headerText(today) == "Rest · Sunday · week 5/5"


# --- The flex day and its moves (WD1.1, WD1.2) --------------------------------------------------

def testFlexDayMakesUpAMissedSession():
    today = view(day(5), trained(1, 2, 3, 4))  # Monday missed
    assert (today.title, today.stepIndex, today.makesUp) == ("Upper", upper, "Monday")
    assert headerText(today) == "Upper · Saturday, for Monday · week 4/5"
    assert headerParts(today) == ("Upper", "Saturday, for Monday · 4 of 5 this week")


def testFlexDayShowsItsBonusWhenNothingWasMissed():
    today = view(day(5), trained(0, 1, 2, 3, 4))
    assert (today.title, today.stepIndex, today.makesUp, ids(today)) == ("Flex", flex, None, ["abMachine"])
    assert headerText(today) == "Flex · Saturday · week 5/5"


def testAMoveToTheFlexDayJoinsTheEndOfTheSessionMadeUp():
    """Saturday makes up Monday, so Friday's wrist curl moves to the end of Saturday."""
    friday = view(day(4), trained(1, 2, 3))
    assert ids(friday) == ["seatedLegCurl", "rearDelt"]
    saturday = view(day(5), trained(1, 2, 3, 4))
    assert ids(saturday) == ["benchPress", "dips", "inclineWalk", "wristCurl"]
    assert targetText(saturday.exercises[-1]) == "2×10 @ 30 kg"  # with its settings from Friday


def testAMoveToAnEarlierDayIsDecidedOnThatDay():
    """Wednesday missed: on Thursday it's already clear Saturday makes up Push (Monday was trained), so
    Friday's rear delt machine joins the end of Thursday and leaves Friday."""
    thursday = view(day(3), trained(0, 1))
    assert ids(thursday) == ["pullUp", "rearDelt"]
    assert ids(view(day(4), trained(0, 1, 3))) == ["seatedLegCurl", "wristCurl"]
    assert view(day(5), trained(0, 1, 3, 4)).title == "Push"


def testNoMovesWhenTheFlexDayMakesUpSomethingElse():
    assert ids(view(day(4), trained(0, 2, 3))) == ["seatedLegCurl", "rearDelt", "wristCurl"]  # Tuesday missed
    assert ids(view(day(3), trained(0, 1, 2))) == ["pullUp"]  # nothing missed
    # Monday and Wednesday missed: Saturday makes up Upper, so the rear delt machine stays on Friday.
    assert ids(view(day(3), trained(1))) == ["pullUp"]
    assert ids(view(day(4), trained(1, 3))) == ["seatedLegCurl", "rearDelt"]


def testAFlexWorkoutLoggedAsTheBonusHasNoMoves():
    today = view(day(5), [*trained(1, 2, 3, 4), workout(5, flex, finished=False)])
    assert (today.title, today.makesUp, ids(today)) == ("Flex", None, ["abMachine"])


# --- Other facts --------------------------------------------------------------------------------

def testExerciseLoggedOutsideTheSessionStillShows():
    logs = {"overheadPress": LoggedExercise("overheadPress", (SetDone(5, 40.0),))}
    today = view(day(0), [workout(0, finished=False)], logs)
    assert [line.exercise.name for line in today.exercises][-1] == "Overhead Press"
    assert today.exercises[-1].status == "done"


def testWorkoutOfAnOlderPlanShowsThatPlansSession():
    """Logged offline on the old plan as the new one took effect: shown as what was done."""
    week = [dict(dayFile, title="Full Body") if not dayFile.get("restDay") else dayFile for dayFile in planFile["week"]]
    newPlan = checkPlan(dict(planFile, name="New", week=week)).plan
    switched = ImportedPlan(PlanStart("p2", day(1), dt.datetime(2026, 10, 12, 20, tzinfo=dt.UTC),
                                      scheduleDays(newPlan), 3), newPlan)
    today = view(day(1), [workout(0), workout(1, finished=False)], plans=(imported, switched))
    assert (today.title, today.planImportId) == ("Lower A", "p1")
    assert view(day(2), trained(0, 1), plans=(imported, switched)).title == "Full Body"


def testWeekTarget():
    """Monday's plan decides the week's target (17.4a)."""
    assert view(day(3), trained(0, 1)).weekTarget == 5
    assert headerText(view(day(7))) == "Upper · Monday · week 0/5"


def testTargetsWithoutWeight():
    assert targetText(view(day(0)).exercises[1]) == "3×8"


def testWholeKilogramsHaveNoDecimals():
    assert targetText(view(day(2)).exercises[0]) == "3×6 @ 40 kg"


def testThePlansOneKiloAsksForYourWeight():
    """Your plans give every weight as 1 kg, a placeholder (PF2): until you lift or set one, Today shows
    "? kg" and offers no weight (PF3)."""
    from gym.rules.progression import training
    placeholders = json.loads(json.dumps(planFile))
    placeholders["week"][2]["exercises"][0]["weightKg"] = 1  # Wednesday's overhead press
    onPlaceholders = checkPlan(placeholders).plan
    plans = [ImportedPlan(imported.start, onPlaceholders)]
    soFar = training(plans, [], {}, [], [], [], day(2))
    (overheadPress,) = todayView(plans, [], {}, planExercises(onPlaceholders), None, day(2), soFar).exercises
    assert (overheadPress.needsWeight, overheadPress.targetWeightKg) == (True, None)
    assert targetText(overheadPress) == "3×6 @ ? kg"


def testTheHeaderInTwoLines():
    """SC2.3: the session's title big, the weekday and the week's count under it."""
    assert headerParts(view(day(0))) == ("Upper", "Monday · 0 of 5 this week")


def testWorkoutProgressCountsDoneAndSkipped():
    """SC2.4: done, skipped and all of today's exercises, for the bar on Today."""
    first, second = (line.exercise.exerciseId for line in view(day(0)).exercises[:2])
    assert workoutProgress(view(day(0))) == (0, 0, len(view(day(0)).exercises))
    logs = {first: LoggedExercise(first, (SetDone(8, 80),)), second: LoggedExercise(second, skipped=True)}
    assert workoutProgress(view(day(0), logs=logs)) == (1, 1, len(view(day(0)).exercises))


def testTheRestTimersTimeLeft():
    """RT1.1: whole seconds left, rounded up, never below 0; written as minutes and seconds."""
    start = dt.datetime(2026, 10, 12, 18, 0, tzinfo=dt.UTC)
    assert restLeft(start + dt.timedelta(seconds=90), start) == 90
    assert restLeft(start + dt.timedelta(seconds=90), start + dt.timedelta(seconds=0.4)) == 90
    assert restLeft(start, start + dt.timedelta(seconds=5)) == 0
    assert (clockText(90), clockText(5), clockText(0)) == ("1:30", "0:05", "0:00")
