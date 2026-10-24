"""Tests for the weekly schedule (plan section 5, WD1.1), written before the code (F10.1).

The example plan is Upper, Lower A, Push, Pull, Lower B, a flex day that makes up a missed session
(Upper, Pull, Push, Lower A, Lower B in that order), and a rest day. Days are counted from Monday 5 Oct
2026.
"""

import datetime as dt

from gym.rules.schedule import (
    LoggedWorkout,
    PlanStart,
    ScheduleDay,
    daySchedule,
    flexDayIndex,
    isFinished,
    planInEffect,
    replay,
)

upper, lowerA, push, pull, lowerB, flex, sunday = range(7)
weekDays = (
    ScheduleDay("Upper", isRest=False),
    ScheduleDay("Lower A", isRest=False),
    ScheduleDay("Push", isRest=False),
    ScheduleDay("Pull", isRest=False),
    ScheduleDay("Lower B", isRest=False),
    ScheduleDay("Flex", isRest=False, makeUp=(upper, pull, push, lowerA, lowerB)),
    ScheduleDay("Rest", isRest=True),
)
monday = dt.date(2026, 10, 5)


def day(n: int) -> dt.date:
    """The date n days after Monday 5 Oct 2026 (day(5) is Saturday, day(7) the next Monday)."""
    return monday + dt.timedelta(days=n)


def plan(planImportId="p1", startDay=0, days=weekDays, importedHour=8, weeklyTarget=5) -> PlanStart:
    """A plan import that takes effect on day(startDay)."""
    importedAt = dt.datetime.combine(day(startDay), dt.time(importedHour), tzinfo=dt.UTC)
    return PlanStart(planImportId, day(startDay), importedAt, days, weeklyTarget)


def workout(n: int, stepIndex: int | None = None, planImportId="p1", finished=True) -> LoggedWorkout:
    """A workout logged on day(n), by default as that weekday's own session."""
    return LoggedWorkout(day(n), planImportId, day(n).weekday() if stepIndex is None else stepIndex, finished)


def trained(*days: int) -> list[LoggedWorkout]:
    return [workout(n) for n in days]


# --- Basics -------------------------------------------------------------------------------------

def testNoPlanYet():
    today = daySchedule([], [], day(0))
    assert (today.planImportId, today.stepIndex, today.nextWorkoutIndex, today.status) == (None, None, None, "open")


def testTodaysWeekdayDecidesTheSession():
    for n in range(5):
        today = daySchedule([plan()], trained(*range(n)), day(n))
        assert (today.planImportId, today.stepIndex, today.isRest, today.makesUp) == ("p1", n, False, None)


def testAPlanTakingEffectMidWeekStartsOnThatWeekday():
    """There's no starting step to choose: a plan starting on Thursday starts with Thursday's session."""
    assert daySchedule([plan(startDay=3)], [], day(3)).stepIndex == pull


def testAMissedDayIsJustMissed():
    """Nothing shifts: Tuesday is Lower A whether Monday was trained or not."""
    today = daySchedule([plan()], [], day(1))
    assert (today.stepIndex, today.isRest) == (lowerA, False)


def testRestDayIsRestAndSaysWhatComesNext():
    today = daySchedule([plan()], trained(0, 1, 2, 3, 4, 5), day(6))
    assert (today.stepIndex, today.isRest, today.status) == (sunday, True, "open")
    assert today.nextWorkoutIndex == upper  # "Rest day · next: Upper"


def testWhatComesNextSkipsRestDays():
    days = weekDays[:1] + (ScheduleDay("Rest", isRest=True),) * 6
    assert daySchedule([plan(days=days)], [], day(1)).nextWorkoutIndex == upper
    assert daySchedule([plan()], [], day(4)).nextWorkoutIndex == flex


# --- The flex day (WD1.1) -----------------------------------------------------------------------

def testFlexDayMakesUpTheMissedSession():
    today = daySchedule([plan()], trained(1, 2, 3, 4), day(5))  # Monday missed
    assert (today.stepIndex, today.makesUp, today.isRest) == (upper, upper, False)


def testFlexDayMakesUpTheMoreImportantOfTwo():
    """Push and Pull missed: Pull comes first in the plan's order, so Push stays missed."""
    today = daySchedule([plan()], trained(0, 1, 4), day(5))
    assert (today.stepIndex, today.makesUp) == (pull, pull)
    today = daySchedule([plan()], trained(0, 2, 3), day(5))  # Lower A and Lower B missed
    assert (today.stepIndex, today.makesUp) == (lowerA, lowerA)


def testFlexDayShowsItsBonusWhenNothingWasMissed():
    today = daySchedule([plan()], trained(0, 1, 2, 3, 4), day(5))
    assert (today.stepIndex, today.makesUp, today.flexMakesUp) == (flex, None, None)


def testFlexWorkoutRecordsWhatItWas():
    madeUp = daySchedule([plan()], [*trained(1, 2, 3, 4), workout(5, upper)], day(6))
    bonus = daySchedule([plan()], [*trained(0, 1, 2, 3, 4), workout(5, flex)], day(6))
    assert (madeUp.flexMakesUp, bonus.flexMakesUp) == (upper, None)
    onTheDay = daySchedule([plan()], [*trained(1, 2, 3, 4), workout(5, upper, finished=False)], day(5))
    assert (onTheDay.stepIndex, onTheDay.makesUp, onTheDay.status) == (upper, upper, "trained")


def testWhatTheLoggedFlexWorkoutWasWinsOverWhatWasMissed():
    """Logged as the bonus although Monday was missed (say, from the PC): what was done counts."""
    today = daySchedule([plan()], [*trained(1, 2, 3, 4), workout(5, flex, finished=False)], day(5))
    assert (today.stepIndex, today.makesUp, today.flexMakesUp) == (flex, None, None)


def testEarlierDaysKnowWhatTheFlexDayWillMakeUp():
    """Each day decides from the days already over; it and the days after count as trained (WD1.2)."""
    assert daySchedule([plan()], [], day(0)).flexMakesUp is None  # nothing is over yet
    assert daySchedule([plan()], trained(0, 1), day(3)).flexMakesUp == push  # Wednesday missed
    assert daySchedule([plan()], trained(1), day(3)).flexMakesUp == upper  # Monday too: Upper comes first
    assert daySchedule([plan()], trained(0, 1, 2, 3), day(4)).flexMakesUp is None  # Friday is today, not missed


def testOnlyTheFlexDaysOwnWeekCounts():
    lastWeek = trained(1, 2, 3, 4)  # last week's Monday missed
    assert daySchedule([plan()], [*lastWeek, *trained(7, 8, 9, 10, 11)], day(12)).makesUp is None


def testDaysBeforeTheFirstPlanAreNotMissed():
    today = daySchedule([plan(startDay=2)], trained(2, 3, 4), day(5))
    assert (today.stepIndex, today.makesUp) == (flex, None)


def testAMissUnderTheEarlierPlanStillCounts():
    """A new version imported on Wednesday: Monday was missed under the old one and is made up."""
    plans = [plan("p1", startDay=-7), plan("p2", startDay=2)]
    workouts = [*trained(1), *[workout(n, planImportId="p2") for n in (2, 3, 4)]]
    today = daySchedule(plans, workouts, day(5))
    assert (today.planImportId, today.stepIndex, today.makesUp) == ("p2", upper, upper)


def testWithoutAFlexDayNothingIsMadeUp():
    days = weekDays[:5] + (ScheduleDay("Arms", isRest=False), weekDays[6])
    today = daySchedule([plan(days=days)], [], day(5))
    assert (today.stepIndex, today.makesUp, today.flexMakesUp) == (flex, None, None)
    assert flexDayIndex(days) is None and flexDayIndex(weekDays) == flex


# --- Today's workout, finishing ---------------------------------------------------------------

def testTodaysWorkoutIsShownWithWhatComesNext():
    today = daySchedule([plan()], [workout(0, finished=False)], day(0))
    assert today.workout == workout(0, finished=False)
    assert (today.stepIndex, today.isRest, today.status, today.nextWorkoutIndex) == (upper, False, "trained", lowerA)


def testUnfinishedWorkoutAutoFinishesAtMidnight():
    """R5a: a workout is finished when you tap Finish, or once its day is over."""
    unfinished = workout(0, finished=False)
    assert isFinished(unfinished, today=day(0)) is False
    assert isFinished(unfinished, today=day(1)) is True
    assert isFinished(workout(0, finished=True), today=day(0)) is True


# --- Plan imports -------------------------------------------------------------------------------

def testSameDayImportTheLaterOneWins():
    """Decided by import time, not by id: "a" was imported after "b"."""
    plans = [plan("b", importedHour=8), plan("a", importedHour=9)]
    assert daySchedule(plans, [], day(0)).planImportId == "a"
    assert daySchedule(list(reversed(plans)), [], day(0)).planImportId == "a"


def testPlanTakingEffectLaterIsNotActiveYet():
    plans = [plan(), plan("p2", startDay=5)]
    assert daySchedule(plans, [], day(4)).planImportId == "p1"
    assert daySchedule(plans, [], day(5)).planImportId == "p2"


def testPlanInEffect():
    plans = [plan("b", importedHour=8), plan("a", importedHour=9), plan("c", startDay=5)]
    assert planInEffect(plans, day(-1)) is None
    assert planInEffect(plans, day(4)).planImportId == "a"
    assert planInEffect(list(reversed(plans)), day(4)).planImportId == "a"
    assert planInEffect(plans, day(5)).planImportId == "c"


def testOldPlansWorkoutAfterASwitchShowsAsWhatWasDone():
    """An offline phone logged the old plan's session on the new plan's first day: it counts as trained,
    shown as the old plan's session."""
    plans = [plan(), plan("p2", startDay=3)]
    onTheDay = replay(plans, [workout(3, planImportId="p1")], today=day(4))[day(3)]
    assert (onTheDay.planImportId, onTheDay.stepIndex, onTheDay.status) == ("p1", pull, "trained")
    assert daySchedule(plans, [], day(4)).planImportId == "p2"


# --- Calendar statuses (8, WD1.1) ---------------------------------------------------------------

def testCalendarOfAWeekWithAMadeUpDay():
    days = replay([plan()], [*trained(1, 2, 3, 4), workout(5, upper)], today=day(7))
    assert [days[day(n)].status for n in range(8)] == [
        "missed", "trained", "trained", "trained", "trained", "trained", "rest", "open"]


def testABonusLeftOutIsRestButAMakeUpLeftOutIsMissed():
    allDone = replay([plan()], trained(0, 1, 2, 3, 4), today=day(6))
    assert allDone[day(5)].status == "rest"
    oneMissed = replay([plan()], trained(1, 2, 3, 4), today=day(6))
    assert (oneMissed[day(5)].status, oneMissed[day(5)].makesUp) == ("missed", upper)


def testAWorkoutThatDoesntCountLeavesItsDayMissed():
    """WD4.1: too much skipped (worked out in sessions.py) and the day is missed, so the flex day makes it up;
    today's workout is still open, and a bonus that doesn't count is rest."""
    skippedMonday = LoggedWorkout(day(0), "p1", upper, finished=True, counts=False)
    days = replay([plan()], [skippedMonday, *trained(1, 2, 3, 4)], today=day(6))
    assert (days[day(0)].status, days[day(5)].makesUp, days[day(5)].stepIndex) == ("missed", upper, upper)
    assert daySchedule([plan()], [skippedMonday], day(0)).status == "open"
    shortBonus = LoggedWorkout(day(5), "p1", flex, finished=True, counts=False)
    assert replay([plan()], [*trained(0, 1, 2, 3, 4), shortBonus], today=day(6))[day(5)].status == "rest"


def testDaysBeforeTheFirstPlanAreNotListed():
    assert day(0) not in replay([plan(startDay=1)], [], today=day(2))


# --- Robustness -------------------------------------------------------------------------------

def testFactsOrderDoesNotMatter():
    workouts = trained(0, 2, 3)
    forwards = daySchedule([plan()], workouts, day(5))
    backwards = daySchedule([plan()], list(reversed(workouts)), day(5))
    assert forwards == backwards


def testDeletingAnOldWorkoutOnlyChangesThatDay():
    """Each workout records its session (plan 14): removing Monday's makes Monday missed, nothing else."""
    days = replay([plan()], trained(1), today=day(2))
    assert [days[day(n)].status for n in range(3)] == ["missed", "trained", "open"]
    assert days[day(1)].stepIndex == lowerA


def testAWeekOfOnlyRestDaysHasNoNextWorkout():
    days = (ScheduleDay("Rest", isRest=True),) * 7
    today = daySchedule([plan(days=days)], [], day(3))
    assert (today.isRest, today.nextWorkoutIndex) == (True, None)
