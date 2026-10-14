"""Tests for the plan file checks (plan 4 and 12b, G8a / F12.1), written before the code.

Every problem must be listed at once, in plain words, with its place in the file, so the list can be
pasted back to whoever wrote the plan.
"""

import json
from pathlib import Path

import pytest

from gym.rules.cycle import CycleStep
from gym.rules.planFile import checkPlan, cycleSteps, maxFileBytes, planExercises, readPlanFile

repoRoot = Path(__file__).resolve().parents[3]


def validPlan() -> dict:
    """A valid plan: Push (barbell, bodyweight and cardio), Pull, Rest. Pace: 2 of 3 steps = 4.7 a week."""
    return {
        "planId": "pushPullLegs", "name": "Push Pull Legs", "version": 2, "weeklyTarget": 4,
        "cycle": [
            {"title": "Push", "exercises": [
                {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
                 "sets": 4, "repsMin": 8, "repsMax": 12, "weightKg": 80, "restSec": 120, "incrementKg": 2.5,
                 "notes": "pause at bottom"},
                {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight",
                 "sets": 3, "repsMin": 8, "repsMax": 12, "restSec": 90},
                {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15},
            ]},
            {"title": "Pull", "exercises": [
                {"exerciseId": "deadlift", "name": "Deadlift", "equipment": "barbell", "body": "lower",
                 "sets": 3, "repsMin": 5, "repsMax": 8, "weightKg": 140},
            ]},
            {"title": "Rest", "restDay": True},
        ],
    }


def errorsOf(data) -> tuple[str, ...]:
    """The errors a plan gets; a plan with errors is never returned."""
    result = checkPlan(data)
    assert (result.plan is None) == bool(result.errors)
    return result.errors


bench = 'Step 1 "Push", exercise 1 "Bench Press"'  # the place errors about Bench Press name


# --- Valid plans --------------------------------------------------------------------------------

def testValidPlanBecomesAPlan():
    result = checkPlan(validPlan())
    assert (result.errors, result.warnings) == ((), ())
    plan = result.plan
    assert (plan.planId, plan.name, plan.version, plan.weeklyTarget) == ("pushPullLegs", "Push Pull Legs", 2, 4)
    assert cycleSteps(plan) == (CycleStep("Push", isRest=False), CycleStep("Pull", isRest=False),
                                CycleStep("Rest", isRest=True))
    benchPress, dips, walk = plan.steps[0].exercises
    assert (benchPress.sets, benchPress.repsMin, benchPress.repsMax) == (4, 8, 12)
    assert (benchPress.weightKg, benchPress.incrementKg, benchPress.restSec) == (80.0, 2.5, 120)
    assert benchPress.notes == "pause at bottom"
    assert (dips.equipment, dips.weightKg, dips.incrementKg, dips.isCardio) == ("bodyweight", None, None, False)
    assert (walk.isCardio, walk.minutes, walk.sets) == (True, 15, None)
    assert list(planExercises(plan)) == ["benchPress", "dips", "inclineWalk", "deadlift"]


def testExamplePlanFileIsValid():
    """The example in plans/ must always pass, since it's what the format spec points to."""
    result = readPlanFile((repoRoot / "plans" / "examplePlan.json").read_bytes())
    assert (result.errors, result.warnings) == ((), ())


def testPlanBriefExampleIsValid():
    """The example in plans/planFormat.md is what the Claude project copies, so it must pass too, and
    its sample problem must be word for word what the app says for that mistake."""
    brief = (repoRoot / "plans" / "planFormat.md").read_text(encoding="utf-8")
    example = brief.split("```json\n", 1)[1].split("```", 1)[0]
    result = readPlanFile(example)
    assert (result.errors, result.warnings) == ((), ())

    broken = json.loads(example)
    broken["cycle"][1]["exercises"][2]["weightKg"] = 10  # Lower A's plank
    problem = ('Step 2 "Lower A", exercise 3 "Plank": a bodyweight exercise has no "weightKg"; its progress is '
               "counted in reps.")
    assert readPlanFile(json.dumps(broken)).errors == (problem,)
    assert f"`{problem}`" in brief


def testFileStartingWithAByteOrderMarkIsFine():
    """Some editors put an invisible marker at the start of UTF-8 files."""
    assert readPlanFile(b"\xef\xbb\xbf" + json.dumps(validPlan()).encode()).errors == ()
    assert readPlanFile("\ufeff" + json.dumps(validPlan())).errors == ()


def testThePlanAsReadIsKeptForStoring():
    """plans.planJson stores the plan as imported (plan 14)."""
    assert readPlanFile(json.dumps(validPlan())).planJson == validPlan()


def testIncrementComesFromBodyWhenNotGiven():
    """9.1: upper body 2.5 kg, lower body 5 kg, unless the plan gives incrementKg."""
    data = validPlan()
    del data["cycle"][0]["exercises"][0]["incrementKg"]
    plan = checkPlan(data).plan
    assert planExercises(plan)["benchPress"].incrementKg == 2.5
    assert planExercises(plan)["deadlift"].incrementKg == 5.0


def testStoredPlanIgnoresFieldsFromNewerVersions():
    """A stored plan is read leniently, so an older app can still read a plan a newer one imported."""
    data = validPlan()
    data["tempo"] = "3-1-1"
    data["cycle"][0]["exercises"][0]["rpe"] = 8
    assert len(errorsOf(data)) == 2
    assert checkPlan(data, strict=False).errors == ()


# --- Whole-file problems ------------------------------------------------------------------------

def testFileThatIsNotJson():
    (error,) = readPlanFile(b'{"planId": ').errors
    assert error.startswith("The file isn't valid JSON: ") and "(line 1, column 12)" in error


def testFileThatIsNotText():
    assert readPlanFile(b"\xff\xfe\x00junk").errors == (
        "The file isn't a text file: a plan file is JSON text (UTF-8).",)


def testFileThatIsTooBig():
    assert readPlanFile(b" " * (maxFileBytes + 1)).errors == ("The file is too big to be a plan file (over 1 MB).",)


def testFileMustHoldOnePlan():
    assert readPlanFile(b"[]").errors == (
        'The file must hold one plan: a {…} block with "planId", "name", "version", "weeklyTarget" and '
        '"cycle".',)


def testFileNestedTooDeeply():
    assert readPlanFile("[" * 100_000 + "]" * 100_000).errors == ("The file is nested too deeply to be a plan file.",)


def testFieldTwiceInOneBlock():
    text = json.dumps(validPlan()).replace('"version": 2', '"version": 2, "version": 3')
    assert readPlanFile(text).errors == (
        'The plan file has "version" twice in one block; each field may appear only once.',)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def testNotANumberIsRefused(constant):
    text = json.dumps(validPlan()).replace('"weightKg": 80', f'"weightKg": {constant}')
    assert readPlanFile(text).errors == (f"The plan file uses {constant}, which isn't a number a plan can use.",)


def testEveryProblemIsListedAtOnce():
    assert errorsOf({}) == (
        'The plan: "planId" is missing.', 'The plan: "name" is missing.', 'The plan: "version" is missing.',
        'The plan: "weeklyTarget" is missing.', 'The plan: "cycle" is missing.')


def testUnknownFieldIsRefusedWithASuggestion():
    data = validPlan()
    benchPress = data["cycle"][0]["exercises"][0]
    benchPress["repMin"] = benchPress.pop("repsMin")
    assert errorsOf(data) == (f'{bench}: unknown field "repMin" (did you mean "repsMin"?).',
                              f'{bench}: "repsMin" is missing.')


# --- The weekly target (F12.1) ------------------------------------------------------------------

@pytest.mark.parametrize("target", [0, 8, -1])
def testWeeklyTargetOutsideOneToSevenIsRefused(target):
    data = validPlan()
    data["weeklyTarget"] = target
    assert errorsOf(data) == (f'The plan: "weeklyTarget" must be between 1 and 7, not {target}.',)


def testTargetFasterThanTheCyclesPaceIsOnlyAWarning():
    data = validPlan()
    data["weeklyTarget"] = 5
    result = checkPlan(data)
    assert result.errors == () and result.plan is not None
    assert result.warnings == (
        "The weekly target (5) is more than this cycle's pace (about 4.7 workouts a week), so some weeks "
        "will fall short unless you train on rest days.",)


# --- Steps --------------------------------------------------------------------------------------

def testCycleNeedsAWorkout():
    data = validPlan()
    data["cycle"] = [{"title": "Rest", "restDay": True}]
    assert errorsOf(data) == ("The plan: the cycle has no workout; every step is a rest day.",)


def testCycleMustBeAListOfSteps():
    data = validPlan()
    data["cycle"] = []
    assert errorsOf(data) == ('The plan: "cycle" must be a list with at least one step.',)
    data["cycle"] = [{"title": "Push", "exercises": [{}]}] * 61
    assert errorsOf(data) == ("The plan: the cycle has 61 steps; at most 60 are allowed.",)


def testStepThatIsNotABlock():
    data = validPlan()
    data["cycle"][2] = "Rest"
    assert errorsOf(data) == ('Step 3 must be a {…} block with a "title".',)


def testRestDayCantHaveExercises():
    data = validPlan()
    data["cycle"][2]["exercises"] = data["cycle"][1]["exercises"]
    assert errorsOf(data) == ("Step 3 \"Rest\": a rest day can't have exercises.",)
    data["cycle"][2]["exercises"] = []
    assert errorsOf(data) == ()


def testWorkoutStepNeedsExercises():
    data = validPlan()
    del data["cycle"][1]["exercises"]
    assert errorsOf(data) == ('Step 2 "Pull": "exercises" is missing (for a rest day, add "restDay": true).',)
    data["cycle"][1]["exercises"] = []
    assert errorsOf(data) == ('Step 2 "Pull": "exercises" must be a list with at least one exercise.',)


def testSameExerciseTwiceInOneStep():
    """A day logs each exercise once (one exerciseLogs row per exercise per day)."""
    data = validPlan()
    data["cycle"][1]["exercises"].append(dict(data["cycle"][1]["exercises"][0]))
    assert errorsOf(data) == (
        'Step 2 "Pull": "deadlift" appears more than once; each exercise can be in a step only once.',)


def testSameExerciseInTwoStepsNeedsTheSameSettings():
    """Progress is tracked per exercise, so its settings can't differ; notes and rest time may."""
    data = validPlan()
    pullBench = dict(data["cycle"][0]["exercises"][0], sets=3, body=None, notes="other cue", restSec=60)
    del pullBench["body"]
    data["cycle"][1]["exercises"].append(pullBench)
    assert errorsOf(data) == (
        '"benchPress" is in step 1 "Push" and step 2 "Pull" with different settings (body "upper" vs not '
        'set, sets 4 vs 3). Give it the same settings in both, or a different exerciseId in one.',)
    pullBench.update(sets=4, body="upper")
    assert errorsOf(data) == ()


# --- Exercises ----------------------------------------------------------------------------------

def testRepsMinAboveRepsMax():
    data = validPlan()
    data["cycle"][0]["exercises"][0]["repsMin"] = 13
    assert errorsOf(data) == (f'{bench}: "repsMin" (13) is more than "repsMax" (12).',)


@pytest.mark.parametrize(("value", "shown"), [(True, "true"), (4.5, "4.5"), ("4", '"4"'), (None, "null")])
def testWholeNumbersMustBeWholeNumbers(value, shown):
    """JSON true is a number to Python, so it must be refused explicitly."""
    data = validPlan()
    data["cycle"][0]["exercises"][0]["sets"] = value
    assert errorsOf(data) == (f'{bench}: "sets" must be a whole number, not {shown}.',)


def testWeights():
    data = validPlan()
    benchPress = data["cycle"][0]["exercises"][0]
    benchPress["weightKg"] = 82.25
    assert errorsOf(data) == ()
    benchPress["weightKg"] = 82.255
    assert errorsOf(data) == (f'{bench}: "weightKg" can have at most 2 decimals, not 82.255.',)
    benchPress["weightKg"] = True
    assert errorsOf(data) == (f'{bench}: "weightKg" must be a number, not true.',)
    benchPress["weightKg"] = 1001
    assert errorsOf(data) == (f'{bench}: "weightKg" must be between 0 and 1000, not 1001.',)
    del benchPress["weightKg"]
    assert errorsOf(data) == (f'{bench}: "weightKg" is missing.',)


def testWeightedExerciseNeedsBodyOrIncrement():
    data = validPlan()
    benchPress = data["cycle"][0]["exercises"][0]
    del benchPress["incrementKg"], benchPress["body"]
    assert errorsOf(data) == (
        f'{bench}: needs "body" ("upper" or "lower") or "incrementKg", to know how much weight to add.',)


def testBodyweightExerciseHasNoWeight():
    data = validPlan()
    dips = data["cycle"][0]["exercises"][1]
    dips["weightKg"] = 10
    assert errorsOf(data) == (
        'Step 1 "Push", exercise 2 "Dips": a bodyweight exercise has no "weightKg"; its progress is counted '
        'in reps.',)
    del dips["weightKg"]
    dips["incrementKg"] = 2.5
    result = checkPlan(data)
    assert result.errors == ()
    assert result.warnings == (
        'Step 1 "Push", exercise 2 "Dips": "incrementKg" is ignored, because a bodyweight exercise '
        'progresses in reps.',)


def testCardioHasOnlyMinutes():
    walk = 'Step 1 "Push", exercise 3 "Incline Walk"'
    data = validPlan()
    data["cycle"][0]["exercises"][2]["sets"] = 3
    assert errorsOf(data) == (
        f'{walk}: "sets" doesn\'t belong to a cardio exercise; it has only "minutes" and "notes".',)
    data = validPlan()
    del data["cycle"][0]["exercises"][2]["minutes"]
    assert errorsOf(data) == (f'{walk}: "minutes" is missing.',)
    data = validPlan()
    data["cycle"][0]["exercises"][0]["minutes"] = 10
    assert errorsOf(data) == (f'{bench}: "minutes" is only for cardio exercises (add "type": "cardio").',)


def testChoicesAreListed():
    data = validPlan()
    data["cycle"][0]["exercises"][0]["equipment"] = "cable"
    data["cycle"][0]["exercises"][2]["type"] = "cardo"
    assert errorsOf(data) == (
        f'{bench}: "equipment" must be "barbell", "dumbbell", "bodyweight" or "machine", not "cable".',
        'Step 1 "Push", exercise 3 "Incline Walk": "type" must be "strength" or "cardio", not "cardo".')


def testIdsAreCamelCase():
    data = validPlan()
    data["cycle"][0]["exercises"][0]["exerciseId"] = "bench_press"
    assert errorsOf(data) == (
        f'{bench}: "exerciseId" must be camelCase letters and digits starting with a small letter, like '
        '"benchPress", not "bench_press".',)


def testTextFields():
    data = validPlan()
    data["cycle"][0]["exercises"][0]["name"] = "   "
    data["cycle"][0]["exercises"][1]["notes"] = "line one\nline two"
    data["cycle"][1]["title"] = "x" * 51
    assert errorsOf(data) == (
        'Step 1 "Push", exercise 1: "name" is empty.',
        'Step 1 "Push", exercise 2 "Dips": "notes" can\'t have line breaks or other control characters.',
        'Step 2: "title" is longer than 50 characters.')


def testExerciseThatIsNotABlock():
    data = validPlan()
    data["cycle"][1]["exercises"] = ["Deadlift"]
    assert errorsOf(data) == ('Step 2 "Pull", exercise 1 must be a {…} block with an "exerciseId" and a "name".',)
