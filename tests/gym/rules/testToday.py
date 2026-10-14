"""Tests for what Today shows (plan 6, SC2.1): the step, targets, logged and skipped exercises, rest
days and Train anyway, the week's count and the header line."""

import datetime as dt

from gym.rules.cycle import LoggedWorkout, PlanStart
from gym.rules.planFile import checkPlan, cycleSteps, planExercises
from gym.rules.today import ImportedPlan, LoggedExercise, SetDone, headerText, targetText, todayView

monday = dt.date(2026, 10, 12)
push, pull, rest1, legs, rest2 = range(5)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


planFile = {
    "planId": "pushPullLegs", "name": "Push Pull Legs", "version": 1, "weeklyTarget": 4,
    "cycle": [
        {"title": "Push", "exercises": [
            {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
             "sets": 4, "repsMin": 8, "repsMax": 12, "weightKg": 82.5, "restSec": 120, "notes": "pause at bottom"},
            {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight", "sets": 3, "repsMin": 8, "repsMax": 12},
            {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15}]},
        {"title": "Pull", "exercises": [
            {"exerciseId": "deadlift", "name": "Deadlift", "equipment": "barbell", "body": "lower",
             "sets": 3, "repsMin": 5, "repsMax": 8, "weightKg": 140}]},
        {"title": "Rest", "restDay": True},
        {"title": "Legs", "exercises": [
            {"exerciseId": "squat", "name": "Squat", "equipment": "barbell", "body": "lower",
             "sets": 3, "repsMin": 5, "repsMax": 8, "weightKg": 120}]},
        {"title": "Rest", "restDay": True},
    ],
}
plan = checkPlan(planFile).plan
imported = ImportedPlan(
    PlanStart("p1", monday, 0, dt.datetime(2026, 10, 12, 6, tzinfo=dt.UTC), cycleSteps(plan), plan.weeklyTarget),
    plan)
known = planExercises(plan)


def workout(n: int, stepIndex: int, finished: bool = True, planImportId: str = "p1") -> LoggedWorkout:
    return LoggedWorkout(day(n), planImportId, stepIndex, finished)


def view(today: dt.date, workouts=(), logs=None, steps=None, trainAnyway=False, plans=(imported,)):
    return todayView(list(plans), list(workouts), logs or {}, known, steps, today, trainAnyway)


def testNoPlanYet():
    today = view(day(0), plans=(), steps=9500)
    assert (today.hasPlan, today.exercises, today.stepsToday) == (False, (), 9500)
    assert headerText(today) == "Today"


def testTheDaysStepWithItsTargets():
    today = view(day(0))
    assert headerText(today) == "Push · day 1 of 5 · week 0/4"
    assert [(line.exercise.name, targetText(line), line.status) for line in today.exercises] == [
        ("Bench Press", "4×8 @ 82.5 kg", "todo"), ("Dips", "3×8", "todo"), ("Incline Walk", "15 min", "todo")]
    assert (today.planImportId, today.stepIndex, today.workoutExists, today.isRestDay) == ("p1", push, False, False)
    assert today.exercises[0].exercise.notes == "pause at bottom"


def testLoggedAndSkippedExercises():
    logs = {"benchPress": LoggedExercise("benchPress", (SetDone(9, 82.5),) * 4),
            "dips": LoggedExercise("dips", skipped=True)}
    today = view(day(0), [workout(0, push, finished=False)], logs)
    assert [line.status for line in today.exercises] == ["done", "skipped", "todo"]
    assert today.exercises[0].logged.sets[0] == SetDone(9, 82.5)
    assert (today.workoutExists, today.finished) == (True, False)


def testFinishedWorkoutAutoSkipsWhatsLeft():
    """19.1b-1: anything untouched when you tap Finish counts as skipped."""
    logs = {"benchPress": LoggedExercise("benchPress", (SetDone(8, 82.5),) * 4)}
    today = view(day(0), [workout(0, push)], logs)
    assert [line.status for line in today.exercises] == ["done", "autoSkipped", "autoSkipped"]
    assert today.finished


def testRestDayOffersWhatComesNext():
    today = view(day(2), [workout(0, push), workout(1, pull)])
    assert (today.isRestDay, today.title, today.nextWorkoutTitle, today.exercises) == (True, "Rest", "Legs", ())
    assert headerText(today) == "Rest · day 3 of 5 · week 2/4"


def testTrainAnywayShowsTheNextWorkout():
    today = view(day(2), [workout(0, push), workout(1, pull)], trainAnyway=True)
    assert (today.isRestDay, today.title, today.stepIndex) == (False, "Legs", legs)
    assert [line.exercise.exerciseId for line in today.exercises] == ["squat"]


def testAWorkoutLoggedOnARestDayShowsItsStep():
    """After Train anyway logged something, the day is that workout (no button needed any more)."""
    today = view(day(2), [workout(0, push), workout(1, pull), workout(2, legs, finished=False)])
    assert (today.isRestDay, today.title, today.workoutExists) == (False, "Legs", True)


def testExerciseLoggedOutsideTheStepStillShows():
    logs = {"deadlift": LoggedExercise("deadlift", (SetDone(5, 140.0),))}
    today = view(day(0), [workout(0, push, finished=False)], logs)
    assert [line.exercise.name for line in today.exercises][-1] == "Deadlift"
    assert today.exercises[-1].status == "done"


def testWorkoutOfAnOlderPlanShowsThatPlansStep():
    """Logged offline on the old plan as the new one took effect: shown as what was done."""
    newPlan = checkPlan(dict(planFile, name="New", cycle=[{"title": "Full Body", "exercises": [
        {"exerciseId": "squat", "name": "Squat", "equipment": "barbell", "body": "lower",
         "sets": 5, "repsMin": 5, "repsMax": 5, "weightKg": 100}]}])).plan
    switched = ImportedPlan(PlanStart("p2", day(1), 0, dt.datetime(2026, 10, 12, 20, tzinfo=dt.UTC),
                                      cycleSteps(newPlan), 3), newPlan)
    today = view(day(1), [workout(0, push), workout(1, pull, finished=False)], plans=(imported, switched))
    assert (today.title, today.planImportId) == ("Pull", "p1")
    assert view(day(2), [workout(0, push), workout(1, pull)], plans=(imported, switched)).title == "Full Body"


def testWeekTarget():
    """Monday's plan decides the week's target (17.4a)."""
    assert view(day(3), [workout(0, push), workout(1, pull)]).weekTarget == 4
    assert headerText(view(day(7))) == "Push · day 1 of 5 · week 0/4"  # nothing logged: Push still waits


def testTargetsWithoutWeight():
    today = view(day(0))
    assert targetText(today.exercises[1]) == "3×8"


def testWholeKilogramsHaveNoDecimals():
    assert targetText(view(day(1), [workout(0, push)]).exercises[0]) == "3×5 @ 140 kg"
