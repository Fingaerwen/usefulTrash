"""Tests for whether a workout counts (WD4.1): at most 30% of its session's exercises skipped or not done,
moves included. Days are counted from Monday 12 Oct 2026."""

import datetime as dt

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone
from gym.rules.planFile import checkPlan, scheduleDays
from gym.rules.schedule import LoggedWorkout, PlanStart
from gym.rules.sessions import withCounts

monday = dt.date(2026, 10, 12)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def machine(exerciseId: str) -> dict:
    return {"exerciseId": exerciseId, "name": exerciseId.capitalize(), "equipment": "machine", "sets": 3,
            "repsMin": 8, "repsMax": 12, "weightKg": 40, "incrementKg": 2.5}


rest = {"title": "Rest", "restDay": True}
planJson = {"planId": "test", "name": "Test", "version": 1, "weeklyTarget": 3, "week": [
    {"day": "monday", "title": "Ten", "exercises": [machine(f"ten{number}") for number in range(10)]},
    dict(rest, day="tuesday"), dict(rest, day="wednesday"), dict(rest, day="thursday"),
    {"day": "friday", "title": "Three", "exercises": [machine("three0"), machine("three1"), machine("wrist")]},
    {"day": "saturday", "title": "Flex", "makeUp": ["monday"], "exercises": [machine("bonus")],
     "moves": [{"exerciseId": "wrist", "from": "friday", "to": "saturday", "when": ["monday"]}]},
    dict(rest, day="sunday")]}
plan = checkPlan(planJson).plan
start = PlanStart("p1", monday, dt.datetime(2026, 10, 12, 8, tzinfo=dt.UTC), scheduleDays(plan), plan.weeklyTarget)
plans = [ImportedPlan(start, plan)]


def done(exerciseId: str) -> LoggedExercise:
    return LoggedExercise(exerciseId, (SetDone(8, 40),) * 3)


def counts(n: int, logged: list[LoggedExercise], stepIndex: int | None = None,
           earlier: dict[int, list[LoggedExercise]] | None = None) -> bool:
    """Whether day(n)'s workout counts, with the given entries, after the earlier days' workouts."""
    days = {**(earlier or {}), n: logged}
    workouts = [LoggedWorkout(day(d), "p1", day(d).weekday() if d != n or stepIndex is None else stepIndex, True)
                for d in days]
    logs = {day(d): {entry.exerciseId: entry for entry in entries} for d, entries in days.items()}
    return next(workout.counts for workout in withCounts(plans, workouts, logs) if workout.date == day(n))


def testUpTo30PercentSkippedStillCounts():
    seven = [done(f"ten{number}") for number in range(7)]
    assert counts(0, seven)  # 3 of 10 not done: exactly 30%
    assert not counts(0, seven[:6])  # 4 of 10
    assert counts(0, [*seven, LoggedExercise("ten7", skipped=True)])  # a skip is as good as not done


def testOnlySkipsIsNotAWorkout():
    assert not counts(4, [LoggedExercise("three0", skipped=True)])


def testMovesChangeWhatTheDayHolds():
    """Monday that doesn't count is missed, so Saturday makes it up and Friday's wrist exercise moves there:
    Friday then holds 2 exercises, and doing both counts."""
    mondayTooShort = {0: [done("ten0")]}
    assert counts(4, [done("three0"), done("three1")], earlier=mondayTooShort)
    mondayDone = {0: [done(f"ten{number}") for number in range(10)]}
    assert not counts(4, [done("three0")], earlier=mondayDone)  # 2 of 3 not done, nothing moved
    assert counts(4, [done("three0"), done("three1"), done("wrist")], earlier=mondayDone)
