"""Tests for progression (plan 7, WD2.3, WD3.7, WD3.9, WD3.10), the plan's 1 kg placeholder (PF2, PF3, PF6)
and deloads (WD2.4, WD3.2–WD3.5), written before the code. Days are counted from Monday 12 Oct 2026."""

import datetime as dt

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone, StepEdit, WeightEdit
from gym.rules.planFile import checkPlan, planExercises, scheduleDays
from gym.rules.progression import Deload, Target, deloadReps, deloadSets, training, workingWeight
from gym.rules.schedule import LoggedWorkout, PlanStart

monday = dt.date(2026, 10, 12)
mon, tue, wed, thu, fri, sat, sun = range(7)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def barbell(exerciseId, sets=3, repsMin=6, repsMax=10, weightKg=25, **settings):
    return {"exerciseId": exerciseId, "name": exerciseId, "equipment": "barbell", "incrementKg": 2.5,
            "sets": sets, "repsMin": repsMin, "repsMax": repsMax, "weightKg": weightKg, **settings}


def planFile(benchKg=25, extensionKg=20) -> dict:
    """Upper (bench per side, overhead extension, pull-up), Lower (squat), Push (extension again, press),
    Pull (row), Lower B (curl, wrist curl), a flex day making up Upper, Pull, Push, Lower, Lower B, with
    Friday's wrist curl moving to Saturday when it makes up Monday. Sunday rest."""
    extension = {"exerciseId": "extension", "name": "Overhead Extension", "equipment": "dumbbell", "dumbbells": 1,
                 "incrementKg": 2, "repsMin": 10, "repsMax": 15, "weightKg": extensionKg}
    return {"planId": "test", "name": "Test", "version": 1, "weeklyTarget": 5, "week": [
        {"day": "monday", "title": "Upper", "exercises": [
            barbell("bench", weightKg=benchKg, incrementKg=1.25, platesPerSide=True, barKg=20, compound=True),
            dict(extension, sets=3),
            {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight", "compound": True,
             "sets": 3, "repsMin": 5, "repsMax": 10},
            {"exerciseId": "walk", "name": "Walk", "type": "cardio", "minutes": 15}]},
        {"day": "tuesday", "title": "Lower", "exercises": [barbell("squat", weightKg=60, compound=True)]},
        {"day": "wednesday", "title": "Push", "exercises": [dict(extension, sets=4),
                                                            barbell("press", weightKg=40, compound=True)]},
        {"day": "thursday", "title": "Pull", "exercises": [barbell("row", weightKg=50, compound=True)]},
        {"day": "friday", "title": "Lower B", "exercises": [barbell("curl", repsMin=10, repsMax=15),
                                                           barbell("wristCurl", repsMin=12, repsMax=20)]},
        {"day": "saturday", "title": "Flex", "makeUp": ["monday", "thursday", "wednesday", "tuesday", "friday"],
         "moves": [{"exerciseId": "wristCurl", "from": "friday", "to": "saturday", "when": ["monday"]}],
         "exercises": [barbell("abs", repsMin=10, repsMax=15)]},
        {"day": "sunday", "title": "Rest", "restDay": True}]}


def imported(planImportId="p1", startDay=0, **weights) -> ImportedPlan:
    plan = checkPlan(planFile(**weights)).plan
    importedAt = dt.datetime.combine(day(startDay), dt.time(6), tzinfo=dt.UTC)
    return ImportedPlan(PlanStart(planImportId, day(startDay), importedAt, scheduleDays(plan), plan.weeklyTarget),
                        plan)


exercises = planExercises(imported().plan)


class History:
    """Logged workouts, built up in tests: history.log(n, bench=[(8, 25)] * 3, ...)."""

    def __init__(self, plans=None):
        self.plans = plans or [imported()]
        self.workouts: list[LoggedWorkout] = []
        self.logs: dict[dt.date, dict[str, LoggedExercise]] = {}
        self.edits: list[WeightEdit] = []
        self.steps: list[StepEdit] = []
        self.deloads: list[dt.date] = []

    def log(self, n: int, stepIndex: int | None = None, planImportId: str = "p1", **sets) -> "History":
        """A workout on day(n) (by default that weekday's session) with each exercise's sets as (reps, kg)."""
        date = day(n)
        self.workouts.append(LoggedWorkout(date, planImportId, date.weekday() if stepIndex is None else stepIndex,
                                           True))
        self.logs[date] = {exerciseId: LoggedExercise(exerciseId, tuple(SetDone(reps, kg) for reps, kg in done))
                           for exerciseId, done in sets.items()}
        return self

    def training(self, today: int):
        return training(self.plans, self.workouts, self.logs, self.edits, self.steps, self.deloads, day(today))

    def target(self, today: int, exerciseId: str, trackDay: int, now: bool = False) -> Target:
        return self.training(today).target(exercises[exerciseId], trackDay, now)


def sets(reps, kg=25):
    """Sets with these reps at one weight."""
    return [(r, kg) for r in reps]


# --- Double progression (plan 7) ----------------------------------------------------------------

def testANewExerciseStartsAtRepsMinAtThePlansWeight():
    assert History().target(0, "bench", mon) == Target(25, 6)
    assert History().target(0, "pullUp", mon) == Target(None, 5)


def testEverySetHitsTheTargetSoTheLowestSetPlusOne():
    assert History().log(0, bench=sets([8, 7, 7])).target(7, "bench", mon) == Target(25, 8)


def testASetBelowTheTargetKeepsIt():
    history = History().log(0, bench=sets([8, 7, 7])).log(7, bench=sets([8, 8, 7]))
    assert history.target(14, "bench", mon) == Target(25, 8)


def testTheTopOfTheRangeAddsTheStepPerSide():
    """Every set at repsMax: + the step (1.25 kg a side, 2.5 kg in all) and back to repsMin."""
    assert History().log(0, bench=sets([10, 10, 11])).target(7, "bench", mon) == Target(26.25, 6)


# --- ↑new and Undo (UN1.1) ----------------------------------------------------------------------

def undone(history: History, n: int, exerciseId: str) -> History:
    """day(n)'s entry for the exercise was logged after Undo on ↑new."""
    logged = history.logs[day(n)][exerciseId]
    history.logs[day(n)][exerciseId] = LoggedExercise(exerciseId, logged.sets, declinedSuggestion=True)
    return history


def testAStepUpSaysWhereItCameFrom():
    history = History().log(0, bench=sets([10, 10, 10]))
    assert history.target(7, "bench", mon).steppedUpFrom == 25  # Today: ↑new
    history.log(7, bench=sets([6, 6, 6], 26.25))
    assert history.target(14, "bench", mon).steppedUpFrom is None  # done there: no longer new


def testUndoIsNotTodayAndTheTopAgainSuggestsTheStepAgain():
    history = undone(History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([10, 10, 10])), 7, "bench")
    target = history.target(14, "bench", mon)
    assert (target, target.steppedUpFrom) == (Target(26.25, 6), 25)


def testUndoThenShortOfTheTopStaysAtTheLastWeightsTop():
    """Judged at 25 kg × 10 (the top), not as a fresh start at 25 kg, which would ask for 9."""
    history = undone(History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([10, 9, 8])), 7, "bench")
    target = history.target(14, "bench", mon)
    assert (target, target.steppedUpFrom) == (Target(25, 10), None)


def testTwoMissesInARowGoBackToTheLastLowerWeightThatWorked():
    history = (History().log(0, bench=sets([10, 10, 10]))  # 25 worked at 10: up to 26.25
               .log(7, bench=sets([5, 5, 6], 26.25)))  # a miss: two sets under 6
    assert history.target(14, "bench", mon) == Target(26.25, 6)  # one miss changes nothing
    history.log(14, bench=sets([5, 4, 6], 26.25))
    assert history.target(21, "bench", mon) == Target(25, 10)  # back to 25, at the reps achieved there


def testADropGoesToTheNearestLowerWeightThatWorked():
    """With 25 and 26.25 both worked, two misses at 27.5 go back to 26.25, not all the way to 25 (R7b)."""
    history = (History().log(0, bench=sets([10, 10, 10]))  # 25 worked: up to 26.25
               .log(7, bench=sets([10, 10, 10], 26.25))  # 26.25 worked: up to 27.5
               .log(14, bench=sets([5, 5, 6], 27.5)).log(21, bench=sets([5, 4, 6], 27.5)))  # two misses
    assert history.target(28, "bench", mon) == Target(26.25, 10)


def testAfterADropItTakesTwoSessionsAtTheTopToGoHeavier():
    history = (History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([5, 5, 6], 26.25))
               .log(14, bench=sets([5, 4, 6], 26.25)).log(21, bench=sets([10, 10, 10])))
    assert history.target(28, "bench", mon) == Target(25, 10)  # once at the top: not yet
    history.log(28, bench=sets([10, 11, 10]))
    assert history.target(35, "bench", mon) == Target(26.25, 6)


def testTwoMissesWithNoLowerWeightKeepTheTarget():
    history = History().log(0, bench=sets([4, 4, 6])).log(7, bench=sets([5, 4, 4]))
    assert history.target(14, "bench", mon) == Target(25, 6)


def testAOneSetExerciseMissesWithThatSet():
    history = History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([5], 26.25)).log(14, bench=sets([5], 26.25))
    assert history.target(21, "bench", mon) == Target(25, 10)


def testASessionAtAnotherWeightStartsAfreshThere():
    """Lifted 30 instead of 25: judged against repsMin at 30, so 8, 8, 7 → 8 next time at 30."""
    assert History().log(0, bench=sets([8, 8, 7], 30)).target(7, "bench", mon) == Target(30, 8)


def testBodyweightGoesPastTheTopOfTheRange():
    history = History().log(0, pullUp=[(10, None), (11, None), (10, None)])
    assert history.target(7, "pullUp", mon) == Target(None, 11)


def testWorkingWeightIsWhatMostSetsUsed():
    assert workingWeight([SetDone(8, 25), SetDone(8, 25), SetDone(6, 22.5)]) == 25
    assert workingWeight([SetDone(8, 25), SetDone(6, 22.5)]) == 25  # a tie: the heavier
    assert workingWeight([SetDone(8)]) is None


# --- One target per day (WD2.3), the flex day and moves (WD3.10), re-imports (WD3.9) -------------

def testEachDayHasItsOwnTarget():
    history = History().log(0, extension=sets([15, 15, 15], 20)).log(2, extension=sets([11, 10, 10, 10], 20))
    assert history.target(7, "extension", mon) == Target(22, 10)
    assert history.target(7, "extension", wed) == Target(20, 11)


def testANewDayStartsAtTheLatestWeightFromAnyDay():
    """Wednesday's first session starts at Monday's 22 kg, at repsMin."""
    history = History().log(0, extension=sets([15, 15, 15], 20)).log(7, extension=sets([12, 11, 11], 22))
    assert history.target(9, "extension", wed) == Target(22, 10)


def testTheFlexDayUsesTheTargetsOfTheDayItMakesUp():
    """Monday missed. Saturday does Upper, so Monday's bench target moves on."""
    history = History().log(5, stepIndex=mon, bench=sets([8, 8, 8]))
    assert history.target(7, "bench", mon) == Target(25, 9)
    assert history.target(7, "bench", sat) == Target(25, 6)


def testAMovedExerciseUsesTheTargetsOfTheDayItCameFrom():
    """Saturday makes up Monday, so Friday's wrist curl is done on Saturday: Friday's target moves on."""
    history = History().log(5, stepIndex=mon, bench=sets([8, 8, 8]), wristCurl=sets([14, 13, 13], 30))
    assert history.target(7, "wristCurl", fri) == Target(30, 14)


def testAReImportKeepsTheWeightsYouHaveLogged():
    plans = [imported(), imported("p2", startDay=7, benchKg=40, extensionKg=30)]
    history = History(plans).log(0, bench=sets([8, 7, 7]))
    assert history.target(14, "bench", mon) == Target(25, 8)
    newPlan = planExercises(plans[1].plan)
    assert history.training(14).target(newPlan["extension"], mon) == Target(30, 10)  # never trained: the plan's


# --- Weights and steps set in the app (WD2.1, WD3.7) ---------------------------------------------

def testASetWeightRestartsAtRepsMin():
    history = History().log(0, bench=sets([9, 9, 9]))
    history.edits.append(WeightEdit("bench", mon, 30, day(7)))
    assert history.target(7, "bench", mon) == Target(30, 6)
    assert history.target(7, "bench", wed) == Target(25, 6)  # a new day starts at the latest session's weight
    history.log(7, bench=sets([7, 7, 7], 30))
    assert history.target(14, "bench", mon) == Target(30, 8)


def testAWeightSetForADayWithNoSessionYet():
    history = History()
    history.edits.append(WeightEdit("bench", mon, 40, day(0)))
    assert history.target(0, "bench", mon) == Target(40, 6)
    history.log(0, bench=sets([7, 7, 7], 40))
    assert history.target(7, "bench", mon) == Target(40, 8)


def testAWeightSetForTomorrowLeavesTodayAlone():
    history = History().log(0, bench=sets([9, 9, 9]))
    history.edits.append(WeightEdit("bench", mon, 30, day(1)))
    assert history.target(0, "bench", mon) == Target(25, 6)
    assert history.target(0, "bench", mon, now=True) == Target(30, 6)


def testAStepSetInTheAppIsUsed():
    history = History().log(0, bench=sets([10, 10, 10]))
    history.steps.append(StepEdit("bench", 2.5, day(0)))  # set after today's session: it already counts
    assert history.target(7, "bench", mon) == Target(27.5, 6)
    assert history.training(7).stepKg(exercises["bench"]) == 2.5


def testAStepChangeLeavesEarlierSessionsAlone():
    """Sessions before a step change keep the step they had (1.25 a side from the plan)."""
    history = History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([10, 10, 10], 26.25))
    history.steps.append(StepEdit("bench", 2.5, day(14)))
    assert history.target(14, "bench", mon) == Target(27.5, 6)  # not 25 + 2.5 + 2.5
    history.log(14, bench=sets([10, 10, 10], 27.5))
    assert history.target(21, "bench", mon) == Target(30, 6)


def testTheLaterStepChangeOnADayWins():
    history = History().log(0, bench=sets([10, 10, 10]))
    history.steps += [StepEdit("bench", 5, day(0)), StepEdit("bench", 2.5, day(0))]
    assert history.target(7, "bench", mon) == Target(27.5, 6)


def testASecondWeightChangeKeepsWhatTheFirstDid():
    """Setting Monday's bench again later doesn't undo the earlier change, so the deload that followed it
    (bench at the weight set, and squat, each with the last set short twice) stays."""
    history = History().log(1, squat=sets([6, 6, 6], 60))
    history.edits.append(WeightEdit("bench", mon, 30, day(7)))
    history.log(7, bench=sets([7, 7, 5], 30)).log(8, squat=sets([7, 7, 6], 60))
    history.log(14, bench=sets([7, 7, 5], 30)).log(15, squat=sets([7, 7, 6], 60))
    assert history.training(16).upcomingDeload(day(16)) == Deload(day(21), "backwards")
    history.edits.append(WeightEdit("bench", mon, 35, day(28)))
    assert history.training(29).deloadOn(day(21)) == Deload(day(21), "backwards")
    assert history.target(28, "bench", mon) == Target(35, 6)


def testALaterWeightChangeLeavesAnEarlierOneInPlace():
    """Setting the same weight again restarts that day (WD3.7), clearing a miss. A later change doesn't undo
    that, so the next miss is the first in a row, not the second."""
    history = History().log(0, bench=sets([10, 10, 10])).log(7, bench=sets([5, 5, 6], 26.25))  # a miss at 26.25
    history.edits.append(WeightEdit("bench", mon, 26.25, day(14)))
    history.log(14, bench=sets([5, 5, 6], 26.25))
    history.edits.append(WeightEdit("bench", mon, 30, day(21)))
    assert history.target(14, "bench", mon, now=True) == Target(26.25, 6)  # not back to 25 × 10
    assert history.target(21, "bench", mon) == Target(30, 6)


def testTodaysTargetIsBeforeTodaysSession():
    history = History().log(0, bench=sets([8, 8, 8]))
    assert history.target(0, "bench", mon) == Target(25, 6)
    assert history.target(0, "bench", mon, now=True) == Target(25, 9)


# --- The plan's 1 kg placeholder (PF2, PF3, PF6) ------------------------------------------------

onPlaceholders = imported(extensionKg=1)  # the overhead extension, on Monday and Wednesday, at the plan's 1 kg
extensionAt1 = planExercises(onPlaceholders.plan)["extension"]


def testThePlansOneKiloAsksForYourWeight():
    training = History([onPlaceholders]).training(0)
    assert training.needsWeight(extensionAt1, mon) and training.needsWeight(extensionAt1, wed)
    assert not training.needsWeight(exercises["bench"], mon)  # a plan weight other than 1 kg is a weight
    assert not training.needsWeight(exercises["pullUp"], mon)  # bodyweight has no weight to ask for


def testYourFirstSessionReplacesThePlaceholderOnEveryDay():
    """Monday at 20 kg: Monday goes on from there, and Wednesday, with no session yet, starts at 20 too."""
    training = History([onPlaceholders]).log(0, extension=sets([12, 11, 11], 20)).training(7)
    assert not training.needsWeight(extensionAt1, mon) and not training.needsWeight(extensionAt1, wed)
    assert training.target(extensionAt1, mon) == Target(20, 12)
    assert training.target(extensionAt1, wed) == Target(20, 10)


def testAWeightSetOnOneDayStartsTheDaysStillAtThePlaceholder():
    history = History([onPlaceholders])
    history.edits.append(WeightEdit("extension", mon, 20, day(0)))
    training = history.training(0)
    assert training.target(extensionAt1, mon) == Target(20, 10)
    assert training.target(extensionAt1, wed) == Target(20, 10) and not training.needsWeight(extensionAt1, wed)


def testAWeightSetOnOneDayLeavesADayWithItsOwnSessionsAlone():
    history = History([onPlaceholders]).log(2, extension=sets([10, 10, 10, 10], 18))
    history.edits.append(WeightEdit("extension", mon, 20, day(7)))
    assert history.target(7, "extension", wed) == Target(18, 11)
    assert history.training(7).target(extensionAt1, mon) == Target(20, 10)


def testADeloadSessionDoesntReplaceThePlaceholder():
    """Deload sessions don't count (WD3.5): an exercise first done in a deload still asks afterwards."""
    history = History([onPlaceholders])
    history.deloads.append(day(0))
    history.log(0, extension=sets([8, 8], 20))
    assert history.training(7).needsWeight(extensionAt1, mon)


# --- Deloads (WD2.4, WD3.2–WD3.5) ---------------------------------------------------------------

def testDeloadSessionsAreHalfTheSetsAndThreeRepsShort():
    assert [deloadSets(n) for n in (5, 4, 3, 1)] == [3, 2, 2, 1]
    assert [deloadReps(n) for n in (10, 4, 3, 1)] == [7, 1, 1, 1]


def testALiftNoLongerInThePlanDoesntCountAsGoingBackwards():
    """Squat goes backwards, then a new plan drops it: bench going backwards later is one lift, not two."""
    file = planFile()
    file["week"][1] = {"day": "tuesday", "title": "Rest", "restDay": True}
    file["week"][5]["makeUp"].remove("tuesday")
    plan = checkPlan(file).plan
    importedAt = dt.datetime.combine(day(16), dt.time(6), tzinfo=dt.UTC)
    withoutSquat = ImportedPlan(PlanStart("p2", day(16), importedAt, scheduleDays(plan), plan.weeklyTarget), plan)
    history = History([imported(), withoutSquat])
    history.log(1, squat=sets([6, 6, 6], 60)).log(8, squat=sets([7, 7, 6], 60)).log(15, squat=sets([7, 7, 6], 60))
    history.log(21, planImportId="p2", bench=sets([7, 7, 5])).log(28, planImportId="p2", bench=sets([7, 7, 5]))
    assert history.training(29).upcomingDeload(day(29)) == Deload(day(49), "week8")


def backwards(history: History, n: int, **lifts) -> History:
    """Two sessions in a row with the same set under the target, for each lift, on day(n) and day(n + 7)."""
    for offset in (0, 7):
        history.log(n + offset, **{exerciseId: sets(reps, kg) for exerciseId, (reps, kg) in lifts.items()})
    return history


def testTwoCompoundLiftsGoingBackwardsStartADeloadNextMonday():
    """The same set short of the target twice in a row, on bench (Monday) and squat (Tuesday)."""
    history = History().log(0, bench=sets([8, 8, 8])).log(1, squat=sets([8, 8, 8], 60))  # targets: 9
    backwards(history, 7, bench=([9, 8, 9], 25))
    backwards(history, 8, squat=([9, 9, 8], 60))
    assert history.training(14).nextDeload is None or history.training(14).nextDeload.reason != "backwards"
    result = history.training(15)
    assert Deload(day(21), "backwards") in (result.deloads + (result.nextDeload,))
    assert result.upcomingDeload(day(15)) == Deload(day(21), "backwards")


def testOneLiftGoingBackwardsIsNotEnough():
    history = History().log(0, bench=sets([8, 8, 8]))
    backwards(history, 7, bench=([9, 8, 9], 25))
    assert history.training(15).upcomingDeload(day(15)).reason == "week8"


def testDifferentSetsShortOfTheTargetAreNotGoingBackwards():
    history = History().log(0, bench=sets([8, 8, 8])).log(1, squat=sets([8, 8, 8], 60))
    history.log(7, bench=sets([9, 8, 9])).log(14, bench=sets([9, 9, 8]))
    backwards(history, 8, squat=([9, 9, 8], 60))
    assert history.training(16).upcomingDeload(day(16)).reason == "week8"


def testIsolationLiftsDontStartADeload():
    history = History().log(4, curl=sets([11, 11, 11], 25), wristCurl=sets([13, 13, 13], 30))
    backwards(history, 11, curl=([12, 11, 12], 25), wristCurl=([14, 13, 14], 30))
    assert history.training(19).upcomingDeload(day(19)).reason == "week8"


def testWeekEightIsADeloadAtTheLatest():
    """Week 1 is the week of the first workout. Week 8 starts 7 weeks later."""
    history = History().log(2, bench=sets([8, 8, 8]))
    result = history.training(3)
    assert result.nextDeload == Deload(day(49), "week8")
    assert history.training(49).deloadOn(day(49)) == Deload(day(49), "week8")
    assert history.training(56).deloadOn(day(56)) is None


def testWeeksCountFromTheEndOfTheLastDeload():
    history = History().log(0, bench=sets([8, 8, 8]))
    history.deloads.append(day(10))  # by hand, on a Wednesday: 7 days, to Tuesday day(16)
    assert history.training(10).deloadOn(day(16)) == Deload(day(10), "manual")
    assert history.training(17).nextDeload == Deload(day(14 + 49), "week8")  # week 1 is the one holding day(17)


def testADeloadByHandReplacesOneThatsOnlyScheduled():
    history = History().log(0, bench=sets([8, 8, 8])).log(1, squat=sets([8, 8, 8], 60))
    backwards(history, 7, bench=([9, 8, 9], 25))
    backwards(history, 8, squat=([9, 9, 8], 60))
    history.deloads.append(day(17))
    result = history.training(22)
    assert result.deloads == (Deload(day(17), "manual"),)
    assert history.training(25).upcomingDeload(day(25)) == Deload(day(21 + 49), "week8")  # week 1 holds day(24)


def testADeloadByHandOnTheDayAScheduledOneStartsIsYours():
    """Started by hand on the scheduled Monday itself: it's yours (so ⋮ can stop it)."""
    history = History().log(0, bench=sets([8, 8, 8])).log(1, squat=sets([8, 8, 8], 60))
    backwards(history, 7, bench=([9, 8, 9], 25))
    backwards(history, 8, squat=([9, 9, 8], 60))
    history.deloads.append(day(21))
    assert history.training(22).deloads == (Deload(day(21), "manual"),)


def testAKnownLiftOnANewDayStartsWhereItWasAndCountsFromThere():
    """Bench, last done at 30 on Monday, joins Thursday: Thursday starts at 30 (WD3.9), so its first session
    there is at the target and already counts towards going backwards."""
    file = planFile()
    file["week"][3]["exercises"].append(barbell("bench", weightKg=25, incrementKg=1.25, platesPerSide=True, barKg=20,
                                                compound=True))
    plan = checkPlan(file).plan
    importedAt = dt.datetime.combine(day(0), dt.time(6), tzinfo=dt.UTC)
    history = History([ImportedPlan(PlanStart("p1", day(0), importedAt, scheduleDays(plan), plan.weeklyTarget), plan)])
    history.log(0, bench=sets([8, 8, 8], 30))  # lifted 30, not the plan's 25
    history.log(1, squat=sets([8, 8, 8], 60))
    history.log(3, bench=sets([7, 7, 5], 30)).log(8, squat=sets([9, 9, 8], 60)).log(10, bench=sets([7, 7, 5], 30))
    history.log(15, squat=sets([9, 9, 8], 60))
    assert history.training(16).upcomingDeload(day(16)) == Deload(day(21), "backwards")


def testDeloadSessionsDontCountAndTargetsPickUpAfterwards():
    history = History().log(0, bench=sets([8, 8, 8]))
    history.deloads.append(day(7))
    history.log(7, bench=sets([10, 10], 25))  # counted, this would step the weight up
    assert history.target(14, "bench", mon) == Target(25, 9)


def testBackwardsDoesntCarryOverADeload():
    history = History().log(0, bench=sets([8, 8, 8])).log(1, squat=sets([8, 8, 8], 60))
    history.log(7, bench=sets([9, 8, 9])).log(8, squat=sets([9, 9, 8], 60))
    history.deloads.append(day(14))
    history.log(21, bench=sets([9, 8, 9])).log(22, squat=sets([9, 9, 8], 60))
    assert history.training(23).upcomingDeload(day(23)).reason == "week8"
