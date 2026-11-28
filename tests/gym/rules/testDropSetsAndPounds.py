"""Tests for drop sets (DS1.1) and machines marked in pounds (LB1.1): the plan fields, the drop part's own
progression, the totals in kg, and how Today writes them. Days are counted from Monday 12 Oct 2026."""

import datetime as dt

from usefulShared.training.facts import ImportedPlan, LoggedExercise, SetDone
from usefulShared.training.planFile import checkPlan, dropPart, planExercises, scheduleDays
from gym.rules.progression import Target, training
from usefulShared.training.schedule import LoggedWorkout, PlanStart
from gym.rules.stats import loadKg, nextTargetText, oneRepMaxKg, readableSets, setsText, unit, volumeKg
from gym.rules.today import setsLeftText, targetText, todayView

monday = dt.date(2026, 10, 12)


def day(n: int) -> dt.date:
    return monday + dt.timedelta(days=n)


def hammerCurl(**settings) -> dict:
    return {"exerciseId": "hammerCurl", "name": "Hammer Curl", "equipment": "dumbbell", "dumbbells": 2,
            "incrementKg": 1, "sets": 3, "repsMin": 4, "repsMax": 6, "weightKg": 1,
            "drop": {"repsMin": 12, "repsMax": 15}, **settings}


def pullover(**settings) -> dict:
    return {"exerciseId": "latPullover", "name": "Lat Pullover Machine", "equipment": "machine", "sets": 3,
            "repsMin": 10, "repsMax": 12, "weightLb": 1, "incrementLb": 10, **settings}


def planFile(*mondayExercises: dict, wednesday: tuple[dict, ...] = ()) -> dict:
    exercises = list(mondayExercises) or [hammerCurl(), pullover()]
    week = [{"day": "monday", "title": "Arms", "exercises": exercises}]
    week.append({"day": "tuesday", "title": "Rest", "restDay": True})
    week.append({"day": "wednesday", "title": "More", "exercises": list(wednesday)} if wednesday
                else {"day": "wednesday", "title": "Rest", "restDay": True})
    week += [{"day": name, "title": "Rest", "restDay": True} for name in ("thursday", "friday", "saturday", "sunday")]
    return {"planId": "arms", "name": "Arms", "version": 1, "weeklyTarget": 1, "week": week}


def errorsOf(data) -> tuple[str, ...]:
    return checkPlan(data).errors


plan = checkPlan(planFile()).plan
known = planExercises(plan)
curl, machine = known["hammerCurl"], known["latPullover"]
imported = ImportedPlan(PlanStart("p1", monday, dt.datetime(2026, 10, 12, 6, tzinfo=dt.UTC), scheduleDays(plan), 1),
                        plan)


def logged(*sets: tuple) -> LoggedExercise:
    return LoggedExercise("hammerCurl", tuple(SetDone(*done) for done in sets))


def trainingAfter(sessions: dict[int, LoggedExercise], today: int):
    workouts = [LoggedWorkout(day(n), "p1", 0, True) for n in sessions]
    logs = {day(n): {entry.exerciseId: entry} for n, entry in sessions.items()}
    return training([imported], workouts, logs, [], [], [], day(today))


# --- The plan file -------------------------------------------------------------------------------

def testAPoundMachineAndADropSetAreRead():
    assert (machine.unit, machine.weightKg, machine.incrementKg) == ("lb", 1, 10)
    assert (curl.unit, curl.dropRepsMin, curl.dropRepsMax, curl.dropIncrementKg) == ("kg", 12, 15, 1)
    assert curl.hasDrop and not machine.hasDrop
    drop = dropPart(curl)
    assert (drop.exerciseId, drop.repsMin, drop.repsMax, drop.incrementKg, drop.weightKg) == (
        "hammerCurl#drop", 12, 15, 1, 1)


def testThePoundStepComesFromBodyInPounds():
    plain = {key: value for key, value in pullover().items() if key != "incrementLb"} | {"body": "lower"}
    assert planExercises(checkPlan(planFile(plain)).plan)["latPullover"].incrementKg == 10


def testADropsOwnStepInTheExercisesUnit():
    dropped = hammerCurl(drop={"repsMin": 12, "repsMax": 15, "incrementKg": 0.5})
    assert planExercises(checkPlan(planFile(dropped)).plan)["hammerCurl"].dropIncrementKg == 0.5
    pounds = pullover(drop={"repsMin": 12, "repsMax": 15, "incrementLb": 5})
    assert planExercises(checkPlan(planFile(pounds)).plan)["latPullover"].dropIncrementKg == 5


def testWrongPoundAndDropFieldsAreRefusedInPlainWords():
    place = 'Monday "Arms", exercise 1 "Lat Pullover Machine"'
    assert errorsOf(planFile(pullover(weightKg=1))) == (
        f'{place}: has both "weightKg" and "weightLb". Give one: "weightLb" is for a machine marked in pounds.',)
    assert errorsOf(planFile(pullover(incrementKg=5))) == (
        f'{place}: "incrementKg" doesn\'t go with "weightLb". Give "incrementLb", in the same unit as the weight.',)
    bodyweight = {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight", "sets": 3, "repsMin": 5,
                  "repsMax": 8, "weightLb": 1, "drop": {"repsMin": 5, "repsMax": 8}}
    assert errorsOf(planFile(bodyweight)) == (
        'Monday "Arms", exercise 1 "Dips": a bodyweight exercise has no "weightLb". Its progress is counted in reps.',
        'Monday "Arms", exercise 1 "Dips": "drop" is only for exercises with a weight: a drop set goes on at a '
        "lighter one.")
    curlPlace = 'Monday "Arms", exercise 1 "Hammer Curl"'
    assert errorsOf(planFile(hammerCurl(drop={"repsMin": 15, "repsMax": 12, "reps": 3}))) == (
        f'{curlPlace}, drop: unknown field "reps" (did you mean "repsMin"?).',
        f'{curlPlace}, drop: "repsMin" (15) is more than "repsMax" (12).')
    assert errorsOf(planFile(hammerCurl(drop=12))) == (
        f'{curlPlace}: "drop" must be a {{…}} block with "repsMin" and "repsMax", like {{"repsMin": 10, '
        '"repsMax": 15}, not 12.',)
    walk = {"exerciseId": "walk", "name": "Walk", "type": "cardio", "minutes": 10, "drop": {}}
    assert any('"drop" doesn\'t belong to a cardio exercise' in error for error in errorsOf(planFile(walk)))


def testTheDropAndUnitMustMatchOnEveryDay():
    errors = errorsOf(planFile(hammerCurl(), wednesday=(hammerCurl(drop={"repsMin": 10, "repsMax": 15}),)))
    assert len(errors) == 1 and "drop repsMin 12 vs 10" in errors[0]


def testAStoredPlanFromANewerAppIsStillRead():
    """Lenient reading ignores fields an older app doesn't know, so a drop's extra field doesn't break it."""
    stored = planFile(hammerCurl(drop={"repsMin": 12, "repsMax": 15, "someday": 1}))
    assert checkPlan(stored, strict=False).plan is not None


# --- Progression ---------------------------------------------------------------------------------

def testTheDropPartProgressesOnItsOwnTrack():
    """8 kg × 4-6 then 5 kg × 12-15. The drop steps up by its own rules: every set at its top, all sets done."""
    first = trainingAfter({0: logged((5, 8, 12, 5), (5, 8, 12, 5), (4, 8, 12, 5))}, 7)
    assert first.target(curl, 0) == Target(8, 5)  # the lowest set + 1, as always
    assert first.target(dropPart(curl), 0) == Target(5, 13)
    topped = trainingAfter({0: logged((6, 8, 15, 5), (6, 8, 15, 5), (6, 8, 15, 5))}, 7)
    assert topped.target(curl, 0) == Target(9, 4)
    assert topped.target(dropPart(curl), 0) == Target(6, 12)
    assert nextTargetText(curl, topped, 0) == "9 kg × 4, drop 6 kg × 12"  # the Progress tab's
    assert nextTargetText(curl, trainingAfter({}, 0), 0) == "? kg × 4, drop ? kg × 12"


def testTheDropWaitsForEveryPlannedSet():
    """TK1.2 for the drop too: two drops at the top of the range out of three sets keep it there."""
    short = trainingAfter({0: logged((6, 8, 15, 5), (6, 8, 15, 5), (6, 8))}, 7)
    assert short.target(dropPart(curl), 0) == Target(5, 15)


def testTheDropNeedsAWeightUntilOneIsLogged():
    fresh = trainingAfter({}, 0)
    assert fresh.needsWeight(dropPart(curl), 0)
    noDrop = trainingAfter({0: logged((5, 8), (5, 8), (5, 8))}, 7)  # logged before the plan had a drop
    assert noDrop.needsWeight(dropPart(curl), 0) and not noDrop.needsWeight(curl, 0)
    dropped = trainingAfter({0: logged((5, 8, 12, 5))}, 7)
    assert not dropped.needsWeight(dropPart(curl), 0)


# --- Totals in kg ---------------------------------------------------------------------------------

def testPoundsTurnIntoKilogramsOnlyForTheTotals():
    assert unit(machine) == "lb" and unit(curl) == "kg"
    assert round(loadKg(machine, 100), 2) == 45.36
    assert round(volumeKg(machine, [SetDone(10, 100)] * 3)) == 1361
    assert setsText(machine, [SetDone(10, 100)] * 3) == "3×10 @ 100 lb"


def testDropsCountInVolumeAndOneRepMax():
    sets = [SetDone(5, 8, 12, 5)] * 3
    assert volumeKg(curl, sets) == 3 * (5 * 16 + 12 * 10)  # two dumbbells: both hands count
    assert oneRepMaxKg(curl, [SetDone(12, 8, 10, 7)]) == 7 * 2 * (1 + 10 / 30)  # the drop's 10 reps count
    assert setsText(curl, sets) == "3×5 @ 8 kg, drop 3×12 @ 5 kg"


def testTheExportHasADropRowPerSet():
    rows = readableSets({day(0): {"hammerCurl": logged((5, 8, 12, 5))}}, known).splitlines()
    assert rows[1:] == ["2026-10-12,Hammer Curl,hammerCurl,1,5,8,kg,", "2026-10-12,Hammer Curl,hammerCurl,1 drop,12,5,kg,"]


# --- Today -----------------------------------------------------------------------------------------

def todayLine(exerciseId: str, sessions: dict[int, LoggedExercise], today: int, logsToday=None):
    plans = training([imported], [LoggedWorkout(day(n), "p1", 0, True) for n in sessions],
                     {day(n): {entry.exerciseId: entry} for n, entry in sessions.items()}, [], [], [], day(today))
    view = todayView([imported], [LoggedWorkout(day(n), "p1", 0, True) for n in sessions], logsToday or {}, known,
                     None, day(today), plans)
    return next(line for line in view.exercises if line.exercise.exerciseId == exerciseId)


def testTodayWritesTheDropAfterTheTarget():
    first = todayLine("hammerCurl", {}, 0)
    assert targetText(first) == "3×4 @ ? kg, drop 12 @ ? kg" and first.asksWeight
    line = todayLine("hammerCurl", {0: logged((5, 8, 12, 5), (5, 8, 12, 5), (5, 8, 12, 5))}, 7)
    assert targetText(line) == "3×6 @ 8 kg, drop 13 @ 5 kg" and not line.asksWeight
    partDone = todayLine("hammerCurl", {0: logged((5, 8, 12, 5), (5, 8, 12, 5), (5, 8, 12, 5))}, 7,
                         {"hammerCurl": logged((6, 8, 13, 5))})
    assert setsLeftText(partDone) == "1 of 3 done · 2×6 @ 8 kg, drop 13 @ 5 kg left"


def testAPoundMachineOnTodayIsInPounds():
    line = todayLine("latPullover", {0: LoggedExercise("latPullover", (SetDone(10, 100),) * 3)}, 7)
    assert targetText(line) == "3×11 @ 100 lb"
