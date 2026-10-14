"""Tests for the cycle and rest-day rules (plan section 5), written before the code (F10.1).

The example plan is Push, Pull, Rest, Legs, Rest ("day 1 of 5"). Days are counted from Monday 5 Oct 2026.
"""

import datetime as dt

import pytest

from gym.rules.cycle import CycleStep, LoggedWorkout, PlanStart, dayCycle, isFinished, replay

push, pull, rest1, legs, rest2 = range(5)
pplSteps = (
    CycleStep("Push", isRest=False),
    CycleStep("Pull", isRest=False),
    CycleStep("Rest", isRest=True),
    CycleStep("Legs", isRest=False),
    CycleStep("Rest", isRest=True),
)
monday = dt.date(2026, 10, 5)


def day(n: int) -> dt.date:
    """The date n days after Monday 5 Oct 2026."""
    return monday + dt.timedelta(days=n)


def plan(planImportId="p1", startDay=0, startStep=push, steps=pplSteps, importedHour=8) -> PlanStart:
    """A plan import that takes effect on day(startDay)."""
    importedAt = dt.datetime.combine(day(startDay), dt.time(importedHour), tzinfo=dt.UTC)
    return PlanStart(planImportId, day(startDay), startStep, importedAt, steps)


def workout(n: int, stepIndex: int, planImportId="p1", finished=True) -> LoggedWorkout:
    """A workout logged on day(n) as the given step."""
    return LoggedWorkout(day(n), planImportId, stepIndex, finished)


# --- Basics -------------------------------------------------------------------------------------

def testNoPlanYet():
    today = dayCycle([], [], day(0))
    assert today.planImportId is None
    assert today.stepIndex is None
    assert today.nextWorkoutIndex is None


def testFirstDayShowsTheChosenStartStep():
    today = dayCycle([plan()], [], day(0))
    assert (today.planImportId, today.stepIndex, today.isRest) == ("p1", push, False)
    assert today.nextWorkoutIndex == push


def testStartStepCanBeARestDay():
    today = dayCycle([plan(startStep=rest1)], [], day(0))
    assert (today.stepIndex, today.isRest, today.isKeptRest) == (rest1, True, False)
    assert today.nextWorkoutIndex == legs


def testWorkoutMovesTheCycleOn():
    assert dayCycle([plan()], [workout(0, push)], day(1)).stepIndex == pull


def testCycleWrapsAround():
    steps = (CycleStep("A", isRest=False), CycleStep("B", isRest=False))
    workouts = [workout(0, 0), workout(1, 1)]
    assert dayCycle([plan(steps=steps)], workouts, day(2)).stepIndex == 0


# --- Missed days and rest days (plan section 5) --------------------------------------------------

def testMissedTrainingDayJustWaits():
    """A missed day never shifts dates: the next step just waits."""
    for n in (1, 2, 3):
        today = dayCycle([plan()], [], day(n))
        assert (today.stepIndex, today.isRest) == (push, False)


def testPlannedRestIsUsedUpWhenTheDayEndsEvenIfTheAppWasNeverOpened():
    """R4a: the replay needs no app run at midnight; the Rest step on day 2 is used up by itself."""
    workouts = [workout(0, push), workout(1, pull)]
    assert dayCycle([plan()], workouts, day(3)).stepIndex == legs


def testUnplannedRestDoesNotUseUpAPlannedRest():
    """13.3: a day off on a training step doesn't count as the plan's Rest step."""
    workouts = [workout(0, push), workout(2, pull)]  # day 1 off, unplanned
    today = dayCycle([plan()], workouts, day(3))
    assert (today.stepIndex, today.isRest) == (rest1, True)


def testRestDayOffersTheNextWorkout():
    workouts = [workout(0, push), workout(1, pull)]
    today = dayCycle([plan()], workouts, day(2))
    assert (today.stepIndex, today.isRest, today.isKeptRest) == (rest1, True, False)
    assert today.nextWorkoutIndex == legs  # "Rest day · next: Legs", and what Train anyway does


# --- Train anyway (19.1c-2 / 13.1a) -------------------------------------------------------------

def testTrainAnywayKeepsTheRestForLater():
    workouts = [workout(0, push), workout(1, pull), workout(2, legs)]  # Legs done on the Rest day
    tomorrow = dayCycle([plan()], workouts, day(3))
    assert (tomorrow.stepIndex, tomorrow.isRest, tomorrow.isKeptRest) == (rest1, True, True)
    assert tomorrow.nextWorkoutIndex == push
    # The kept rest is used up on day 3, then the plan's own Rest step follows, then Push.
    dayAfter = dayCycle([plan()], workouts, day(4))
    assert (dayAfter.stepIndex, dayAfter.isRest, dayAfter.isKeptRest) == (rest2, True, False)
    assert dayCycle([plan()], workouts, day(5)).stepIndex == push


@pytest.mark.parametrize(
    ("keptRestLimit", "restDaysBeforePull"),
    [(None, 2), (1, 1)],
    ids=["everyRestOwed", "atMostOneRestOwed"],
)
def testTrainAnywayTwiceInARow(keptRestLimit, restDaysBeforePull):
    """Legs on the Rest day, then Push on the kept rest (passing the second Rest step).

    Every skipped rest owed: two rest days follow. At most one owed: one rest day follows.
    """
    workouts = [workout(0, push), workout(1, pull), workout(2, legs), workout(3, push)]
    for n in range(4, 4 + restDaysBeforePull):
        today = dayCycle([plan()], workouts, day(n), keptRestLimit=keptRestLimit)
        assert (today.isRest, today.isKeptRest, today.nextWorkoutIndex) == (True, True, pull)
    afterRests = dayCycle([plan()], workouts, day(4 + restDaysBeforePull), keptRestLimit=keptRestLimit)
    assert (afterRests.stepIndex, afterRests.isRest) == (pull, False)


# --- Today's workout, finishing ---------------------------------------------------------------

def testTodaysWorkoutIsShownWithWhatComesNext():
    today = dayCycle([plan()], [workout(0, push, finished=False)], day(0))
    assert today.workout == workout(0, push, finished=False)
    assert (today.stepIndex, today.isRest, today.status) == (push, False, "trained")
    assert today.nextWorkoutIndex == pull


def testUnfinishedWorkoutAutoFinishesAtMidnight():
    """R5a: a workout is finished when you tap Finish, or once its day is over."""
    unfinished = workout(0, push, finished=False)
    assert isFinished(unfinished, today=day(0)) is False
    assert isFinished(unfinished, today=day(1)) is True
    assert isFinished(workout(0, push, finished=True), today=day(0)) is True


# --- Plan imports -------------------------------------------------------------------------------

def testNewPlanStartsAtItsChosenStep():
    steps = (CycleStep("Upper", isRest=False), CycleStep("Lower", isRest=False), CycleStep("Rest", isRest=True))
    plans = [plan(), plan("p2", startDay=3, startStep=1, steps=steps)]
    workouts = [workout(0, push), workout(1, pull)]
    today = dayCycle(plans, workouts, day(3))
    assert (today.planImportId, today.stepIndex) == ("p2", 1)


def testSameDayImportTheLaterOneWins():
    plans = [plan("p1", importedHour=8), plan("p2", startStep=pull, importedHour=9)]
    assert dayCycle(plans, [], day(0)).planImportId == "p2"
    assert dayCycle(list(reversed(plans)), [], day(0)).planImportId == "p2"


def testPlanTakingEffectLaterIsNotActiveYet():
    plans = [plan(), plan("p2", startDay=5)]
    assert dayCycle(plans, [], day(4)).planImportId == "p1"
    assert dayCycle(plans, [], day(5)).planImportId == "p2"


def testOldPlansWorkoutAfterASwitchDoesNotMoveTheNewPlan():
    """An offline phone logged the old plan's step on the new plan's first day: it counts as trained,
    shown as the old plan's step, but the new plan's cycle stays where it was."""
    plans = [plan(), plan("p2", startDay=3, startStep=pull)]
    workouts = [workout(3, legs, planImportId="p1")]
    onTheDay = replay(plans, workouts, today=day(4))[day(3)]
    assert (onTheDay.planImportId, onTheDay.stepIndex, onTheDay.status) == ("p1", legs, "trained")
    nextDay = dayCycle(plans, workouts, day(4))
    assert (nextDay.planImportId, nextDay.stepIndex) == ("p2", pull)


# --- Calendar statuses (8: missed = 3rd+ unplanned rest day in a row) --------------------------

def testMissedIsTheThirdUnplannedRestDayInARow():
    days = replay([plan()], [], today=day(4))
    assert [days[day(n)].status for n in range(5)] == [
        "unplannedRest", "unplannedRest", "missed", "missed", "open"]


def testPlannedRestResetsTheMissedCount():
    workouts = [workout(0, push), workout(1, pull)]
    days = replay([plan()], workouts, today=day(6))
    assert [days[day(n)].status for n in range(7)] == [
        "trained", "trained", "plannedRest", "unplannedRest", "unplannedRest", "missed", "open"]


def testDaysBeforeTheFirstPlanAreNotListed():
    assert day(0) not in replay([plan(startDay=1)], [], today=day(2))


# --- Robustness -------------------------------------------------------------------------------

def testFactsOrderDoesNotMatter():
    workouts = [workout(0, push), workout(1, pull), workout(3, legs)]
    forwards = dayCycle([plan()], workouts, day(5))
    backwards = dayCycle([plan()], list(reversed(workouts)), day(5))
    assert forwards == backwards


def testDeletingAnOldWorkoutDoesNotRewriteLaterSteps():
    """Each workout records its step (plan 14), so removing day 0 leaves day 1 as Pull."""
    days = replay([plan()], [workout(1, pull)], today=day(2))
    assert days[day(1)].stepIndex == pull
    assert days[day(2)].stepIndex == rest1


def testOutOfRangeStepIsTrainedButDoesNotMoveTheCycle():
    days = replay([plan()], [workout(0, 9)], today=day(1))
    assert days[day(0)].status == "trained"
    assert days[day(1)].stepIndex == push


def testCycleOfOnlyRestDaysHasNoNextWorkout():
    steps = (CycleStep("Rest", isRest=True),)
    today = dayCycle([plan(steps=steps)], [], day(3))
    assert (today.isRest, today.nextWorkoutIndex) == (True, None)
