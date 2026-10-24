"""Tests for the Progress and Week numbers (plan 8, 10, WD1.3, WD3.6): the real load, volume, estimated
1RM, PRs, history and the week's summary. Days are counted from Monday 12 Oct 2026."""

import datetime as dt
import json

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone
from gym.rules.planFile import PlanExercise, checkPlan, planExercises, scheduleDays
from gym.rules.progression import training
from gym.rules.schedule import LoggedWorkout, PlanStart
from gym.rules.stats import (
    exerciseDetail,
    loadKg,
    oneRepMaxKg,
    progressLines,
    records,
    history,
    setsText,
    sparkline,
    volumeKg,
    weekLines,
    weekSummary,
    weekTitle,
    workoutVolumeKg,
)

monday = dt.date(2026, 10, 12)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def strength(exerciseId, equipment="barbell", **settings) -> PlanExercise:
    return PlanExercise(exerciseId, exerciseId.capitalize(), "strength", equipment=equipment, **settings)


bench = strength("bench", platesPerSide=True, barKg=20)
raise_ = strength("raise", equipment="dumbbell", dumbbells=2)
extension = strength("extension", equipment="dumbbell", dumbbells=1)
row = strength("row", equipment="machine", barKg=10)
press = strength("press", equipment="machine")
pullUp = strength("pullUp", equipment="bodyweight")


# --- The real load (WD1.3) ----------------------------------------------------------------------

def testTheRealLoad():
    assert loadKg(bench, 25) == 70  # 25 a side, doubled, plus the 20 kg bar
    assert loadKg(raise_, 8) == 16  # two dumbbells
    assert loadKg(extension, 20) == 20  # one dumbbell
    assert loadKg(row, 40) == 50  # all on one pin, plus the lever
    assert loadKg(press, 40) == 40  # as logged


def testABarNotInThePlanIsGuessedFromTheName():
    """PF7: plates per side without a barKg get the bar or sled their name suggests."""
    def bar(name, equipment="barbell", exerciseId="lift", **settings):
        lift = PlanExercise(exerciseId, name, "strength", equipment=equipment, platesPerSide=True, **settings)
        return loadKg(lift, 10) - 20

    assert bar("Romanian deadlift") == 20
    assert bar("Preacher curl (EZ bar)") == bar("Wrist curl", exerciseId="ezBarWristCurl") == 10
    assert bar("Trap bar deadlift") == bar("Hex Bar Deadlift") == 25
    assert bar("Incline Smith press 30°", "machine") == 15
    assert bar("Hack squat", "machine") == 30
    assert bar("Barbell hack squat") == 20  # the machine words are for machines
    assert bar("Leg Press", "machine") == 50
    assert bar("Lat pulldown", "machine") == bar("Calf press (partials)", "machine") == 0  # lever arms
    assert bar("Squeeze curl") == 20  # "ez" only as a word
    assert bar("Smith machine squat", "machine", barKg=7.5) == 7.5  # the plan's barKg wins
    assert bar("Romanian deadlift", barKg=0) == 0
    assert loadKg(strength("deadlift"), 100) == 100  # logged as its whole load: nothing added


def testVolumeUsesTheRealLoad():
    assert volumeKg(bench, [SetDone(8, 25), SetDone(6, 25)]) == 70 * 14
    assert volumeKg(pullUp, [SetDone(10)]) == 0  # bodyweight reps are kept separate


def testEstimatedOneRepMax():
    """Epley from the real load, only from sets of 1 to 10 reps (16.2a)."""
    assert oneRepMaxKg(bench, [SetDone(10, 25)]) == 70 * (1 + 10 / 30)
    assert oneRepMaxKg(bench, [SetDone(12, 25)]) is None
    assert oneRepMaxKg(press, [SetDone(1, 100), SetDone(5, 90)]) == max(100, 90 * (1 + 5 / 30))


# --- History and PRs (plan 8) --------------------------------------------------------------------

logs = {
    day(0): {"bench": LoggedExercise("bench", (SetDone(8, 25),) * 3),
             "pullUp": LoggedExercise("pullUp", (SetDone(8), SetDone(7))),
             "raise": LoggedExercise("raise", skipped=True)},
    day(7): {"bench": LoggedExercise("bench", (SetDone(10, 26.25), SetDone(9, 26.25))),
             "pullUp": LoggedExercise("pullUp", (SetDone(10), SetDone(9)))},
}


def testHistoryAndRecords():
    sessions = history(logs, "bench")
    assert [session.date for session in sessions] == [day(0), day(7)]
    assert history(logs, "raise") == []  # skipped doesn't count
    found = records(bench, sessions)
    assert (found.heaviestKg, found.mostReps, found.mostRepsAtKg) == (26.25, 10, 26.25)
    assert found.oneRepMaxKg == loadKg(bench, 26.25) * (1 + 10 / 30)
    assert records(pullUp, history(logs, "pullUp")).mostReps == 10


def testHowSetsAreWritten():
    assert setsText(bench, (SetDone(8, 25),) * 3) == "3×8 @ 25 kg/side"
    assert setsText(press, (SetDone(8, 40), SetDone(7, 40))) == "8@40 · 7@40"
    assert setsText(pullUp, (SetDone(10),) * 2) == "2×10"
    assert setsText(strength("walk"), (), 15) == "15 min"


def testSparkline():
    assert sparkline([1, 2, 3, 4, 5, 6, 7, 8]) == "▁▂▃▄▅▆▇█"
    assert sparkline([5, 5]) == "▄▄"
    assert len(sparkline(list(range(100)))) == 30 and sparkline(list(range(100)))[-1] == "█"


# --- The Progress tab (SC3.1) --------------------------------------------------------------------

planFile = {"planId": "test", "name": "Test", "version": 1, "weeklyTarget": 2, "week": [
    {"day": "monday", "title": "Upper", "exercises": [
        {"exerciseId": "bench", "name": "Bench Press", "equipment": "barbell", "platesPerSide": True, "barKg": 20,
         "incrementKg": 1.25, "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 25},
        {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight", "sets": 2, "repsMin": 5, "repsMax": 10}]},
    {"day": "tuesday", "title": "Rest", "restDay": True},
    {"day": "wednesday", "title": "Push", "exercises": [
        {"exerciseId": "bench", "name": "Bench Press", "equipment": "barbell", "platesPerSide": True, "barKg": 20,
         "incrementKg": 1.25, "sets": 2, "repsMin": 6, "repsMax": 10, "weightKg": 25}]},
    *({"day": name, "title": "Rest", "restDay": True} for name in ("thursday", "friday", "saturday", "sunday"))]}
plan = checkPlan(planFile).plan
imported = ImportedPlan(PlanStart("p1", monday, dt.datetime(2026, 10, 12, 6, tzinfo=dt.UTC), scheduleDays(plan), 2),
                        plan)
known = {**planExercises(plan), "oldRow": strength("oldRow", equipment="machine")}
workouts = [LoggedWorkout(day(0), "p1", 0, True), LoggedWorkout(day(7), "p1", 0, True)]
weekLogs = {**logs, day(2): {"oldRow": LoggedExercise("oldRow", (SetDone(10, 50),))}}
workouts.append(LoggedWorkout(day(2), "p1", 2, True))


def trainingOn(today):
    return training([imported], workouts, weekLogs, [], [], [], today)


def testProgressListsThePlanAndPastExercises():
    lines, past = progressLines(imported, known, weekLogs, trainingOn(day(8)), day(8))
    assert [(line.exercise.name, line.now, line.record) for line in lines] == [
        ("Bench Press", "now 26.25 kg/side × 6", "PR 26.25 kg/side"),  # Wednesday next: its latest weight
        ("Pull-up", "now 10 reps", "PR 10 reps")]  # 5, then 7 + 1, then 9 + 1
    assert [(line.exercise.exerciseId, line.now) for line in past] == [("oldRow", "last 1×10 @ 50 kg")]


def testExerciseDetail():
    detail = exerciseDetail(known["bench"], imported, weekLogs, trainingOn(day(8)), day(8), "All")
    assert (detail.chart, detail.chartLabel) == ("▁█", "kg/side")
    assert detail.recordsText == f"PRs: heaviest 26.25 kg/side · 1RM ~{round(loadKg(bench, 26.25) * 4 / 3)} kg · 10 reps @ 26.25 kg/side"
    assert [day.text for day in detail.days] == ["Mon 26.25 kg/side × 10", "Wed 26.25 kg/side × 6"]
    assert detail.stepKg == 1.25
    assert detail.lines[0] == f"19 Oct  10@26.25 · 9@26.25 · {round(loadKg(bench, 26.25) * 19):,} kg"


def testAnExerciseStillAtThePlansOneKiloAsksForItsWeight():
    """"? kg" in Progress too, and the page's ✎ starts empty (PF3)."""
    placeholders = json.loads(json.dumps(planFile))
    for weekday in (0, 2):
        placeholders["week"][weekday]["exercises"][0]["weightKg"] = 1  # the bench press, Monday and Wednesday
    onPlaceholders = checkPlan(placeholders).plan
    plans = ImportedPlan(imported.start, onPlaceholders)
    exercisesAt1 = planExercises(onPlaceholders)
    soFar = training([plans], [], {}, [], [], [], day(0))
    lines, _ = progressLines(plans, exercisesAt1, {}, soFar, day(0))
    assert lines[0].now == "now ? kg/side × 6"
    detail = exerciseDetail(exercisesAt1["bench"], plans, {}, soFar, day(0), "All")
    assert [(day.text, day.target.weightKg) for day in detail.days] == [("Mon ? kg/side × 6", None),
                                                                         ("Wed ? kg/side × 6", None)]


# --- The Week tab (SC4.1) ------------------------------------------------------------------------

def testWeekSummary():
    week = weekSummary([imported], workouts, weekLogs, known, {day(8): 14000, day(9): 500}, {day(4): 81.6, day(11): 81.2},
                       day(7), day(9))
    assert (week.workouts, week.target, week.streak) == (1, 2, 1)
    assert (week.gymCardio, week.stepsCardio) == (0, 145)
    assert week.volumeKg == volumeKg(bench, logs[day(7)]["bench"].sets)
    assert week.lastWeekVolumeKg == volumeKg(bench, logs[day(0)]["bench"].sets) + 500
    assert week.bodyweightReps == 19
    assert week.records == ("Bench Press 26.25 kg/side", "Pull-up 10 reps")
    assert (week.weightKg, week.weightChangeKg) == (81.2, -0.4)
    assert [status for _, status in week.calendar] == ["trained", "rest", "open", "later", "later", "later", "later"]


def testLastWeek():
    week = weekSummary([imported], workouts, weekLogs, known, {}, {day(4): 81.6, day(-3): 82.0}, day(0), day(9))
    # Monday: bench and pull-up done, the raise skipped; Wednesday: the row done, bench not: 3 of 5.
    assert (week.workouts, week.streak, week.completion) == (2, 1, 60)
    assert (week.weightKg, week.weightChangeKg) == (81.6, -0.4)
    assert [status for _, status in week.calendar][:3] == ["trained", "rest", "trained"]


def testWorkoutVolume():
    assert workoutVolumeKg(logs[day(0)], known) == volumeKg(bench, logs[day(0)]["bench"].sets)


def testWeekLines():
    week = weekSummary([imported], workouts, weekLogs, known, {day(8): 14000, day(9): 500}, {day(4): 81.6, day(11): 81.2},
                       day(7), day(9))
    benchNow, benchBefore = volumeKg(bench, logs[day(7)]["bench"].sets), volumeKg(bench, logs[day(0)]["bench"].sets)
    change = round((benchNow - benchBefore - 500) / (benchBefore + 500) * 100)
    assert weekTitle(week) == "Week 19–25 Oct"
    assert weekLines(week) == [
        ("Workouts", "1 of 2"), ("Streak", "1 week"), ("Completion", "100%"), ("Cardio", "145 min (from steps)"),
        ("Volume", f"{round(benchNow):,} kg   {'↑' if change > 0 else '↓'} {abs(change)}% vs last week"),
        ("Bodyweight", "19 reps"), ("PRs", "Bench Press 26.25 kg/side · Pull-up 10 reps"),
        ("Weight", "81.2 kg   ↓ 0.4 kg")]
    assert weekTitle(weekSummary([imported], workouts, weekLogs, known, {}, {}, day(-14), day(9))) == "Week 28 Sep – 4 Oct"
