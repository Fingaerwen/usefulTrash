"""Tests for the week numbers (plan 6 and 8): workouts this week against the weekly target. Weeks run
Monday to Sunday. Written before the code."""

import datetime as dt

from gym.rules.schedule import LoggedWorkout, PlanStart, ScheduleDay
from gym.rules.week import weekStart, weeklyTarget, workoutsInWeek

monday = dt.date(2026, 10, 12)
days = (ScheduleDay("Workout", isRest=False), ScheduleDay("Rest", isRest=True)) * 3 + (ScheduleDay("Rest", isRest=True),)


def day(n: int) -> dt.date:
    """The date n days after Monday 12 Oct 2026."""
    return monday + dt.timedelta(days=n)


def plan(planImportId: str, startDay: int, weeklyTarget: int) -> PlanStart:
    importedAt = dt.datetime.combine(day(startDay), dt.time(8), tzinfo=dt.UTC)
    return PlanStart(planImportId, day(startDay), importedAt, days, weeklyTarget)


def workout(n: int) -> LoggedWorkout:
    return LoggedWorkout(day(n), "p1", 0, finished=True)


def testWeekRunsMondayToSunday():
    assert [weekStart(day(n)) for n in (0, 3, 6, 7)] == [monday, monday, monday, day(7)]


def testMondaysPlanDecidesTheWeeksTarget():
    """17.4a: a plan switched mid-week sets the target from the next week on."""
    plans = [plan("p1", -7, weeklyTarget=4), plan("p2", 2, weeklyTarget=3)]
    assert weeklyTarget(plans, day(1)) == 4
    assert weeklyTarget(plans, day(5)) == 4
    assert weeklyTarget(plans, day(7)) == 3


def testFirstPlanStartingMidWeekSetsThatWeeksTarget():
    plans = [plan("p1", 2, weeklyTarget=3), plan("p2", 4, weeklyTarget=5)]
    assert weeklyTarget(plans, day(3)) == 3


def testNoPlanNoTarget():
    assert weeklyTarget([], day(0)) is None
    assert weeklyTarget([plan("p1", 7, weeklyTarget=4)], day(0)) is None


def testWorkoutsInTheWeek():
    """Only that week's workouts count; a day counts once (one workout per day, DT1.1)."""
    workouts = [workout(-1), workout(0), workout(2), workout(2), workout(6), workout(7)]
    assert workoutsInWeek(workouts, day(3)) == 3
