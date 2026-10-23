"""Tests for the plan file checks (plan 4 and 12b, G8a / F12.1), written before the code.

Every problem must be listed at once, in plain words, with its place in the file, so the list can be
pasted back to whoever wrote the plan.
"""

import json
from pathlib import Path

import pytest

from gym.rules.planFile import checkPlan, maxFileBytes, planExercises, readPlanFile, scheduleDays
from gym.rules.schedule import ScheduleDay

repoRoot = Path(__file__).resolve().parents[3]


def validPlan() -> dict:
    """A valid plan: Push on Monday (barbell, bodyweight and cardio), Pull on Tuesday, rest the other days."""
    return {
        "planId": "pushPullLegs", "name": "Push Pull Legs", "version": 2, "weeklyTarget": 2,
        "week": [
            {"day": "monday", "title": "Push", "exercises": [
                {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
                 "sets": 4, "repsMin": 8, "repsMax": 12, "weightKg": 80, "restSec": 120, "incrementKg": 2.5,
                 "notes": "pause at bottom"},
                {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight",
                 "sets": 3, "repsMin": 8, "repsMax": 12, "restSec": 90},
                {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15},
            ]},
            {"day": "tuesday", "title": "Pull", "exercises": [
                {"exerciseId": "deadlift", "name": "Deadlift", "equipment": "barbell", "body": "lower",
                 "sets": 3, "repsMin": 5, "repsMax": 8, "weightKg": 140},
            ]},
            *({"day": name, "title": "Rest", "restDay": True}
              for name in ("wednesday", "thursday", "friday", "saturday", "sunday")),
        ],
    }


def errorsOf(data) -> tuple[str, ...]:
    """The errors a plan gets; a plan with errors is never returned."""
    result = checkPlan(data)
    assert (result.plan is None) == bool(result.errors)
    return result.errors


bench = 'Monday "Push", exercise 1 "Bench Press"'  # the place errors about Bench Press name


# --- Valid plans --------------------------------------------------------------------------------

def testValidPlanBecomesAPlan():
    result = checkPlan(validPlan())
    assert (result.errors, result.warnings) == ((), ())
    plan = result.plan
    assert (plan.planId, plan.name, plan.version, plan.weeklyTarget) == ("pushPullLegs", "Push Pull Legs", 2, 2)
    assert scheduleDays(plan) == (ScheduleDay("Push", isRest=False), ScheduleDay("Pull", isRest=False),
                                  *(ScheduleDay("Rest", isRest=True),) * 5)
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
    broken["week"][1]["exercises"][2]["weightKg"] = 10  # Lower A's plank
    problem = ('Tuesday "Lower A", exercise 3 "Plank": a bodyweight exercise has no "weightKg"; its progress is '
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
    del data["week"][0]["exercises"][0]["incrementKg"]
    plan = checkPlan(data).plan
    assert planExercises(plan)["benchPress"].incrementKg == 2.5
    assert planExercises(plan)["deadlift"].incrementKg == 5.0


def testStoredPlanIgnoresFieldsFromNewerVersions():
    """A stored plan is read leniently, so an older app can still read a plan a newer one imported."""
    data = validPlan()
    data["tempo"] = "3-1-1"
    data["week"][0]["exercises"][0]["rpe"] = 8
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
        '"week".',)


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
        'The plan: "weeklyTarget" is missing.', 'The plan: "week" is missing.')


def testUnknownFieldIsRefusedWithASuggestion():
    data = validPlan()
    benchPress = data["week"][0]["exercises"][0]
    benchPress["repMin"] = benchPress.pop("repsMin")
    assert errorsOf(data) == (f'{bench}: unknown field "repMin" (did you mean "repsMin"?).',
                              f'{bench}: "repsMin" is missing.')


# --- The weekly target (F12.1) ------------------------------------------------------------------

@pytest.mark.parametrize("target", [0, 8, -1])
def testWeeklyTargetOutsideOneToSevenIsRefused(target):
    data = validPlan()
    data["weeklyTarget"] = target
    assert errorsOf(data) == (f'The plan: "weeklyTarget" must be between 1 and 7, not {target}.',)


def testTargetAboveTheWeeksWorkoutDaysIsRefused():
    """There's no Train anyway (WD1.1), so such a target could never be met."""
    data = validPlan()
    data["weeklyTarget"] = 3
    assert errorsOf(data) == (
        "The plan: \"weeklyTarget\" (3) is more than the week's 2 workout days, so it could never be met.",)


# --- The week (WD1.1) ---------------------------------------------------------------------------

def testTheOldCycleFormatIsRefusedInPlainWords():
    data = validPlan()
    data["cycle"] = data.pop("week")
    assert errorsOf(data) == ('The plan: "cycle" is the old format; plans now run on weekdays. Give "week" with the 7 '
                              "days, Monday to Sunday, instead.",)


@pytest.mark.parametrize(("week", "has"), [([], "it has 0"), ("Mon", 'not "Mon"')])
def testWeekMustListTheSevenDays(week, has):
    data = validPlan()
    data["week"] = week
    assert errorsOf(data) == (f'The plan: "week" must be a list of the 7 days, Monday to Sunday; {has}.',)


def testWeekOfEightDays():
    data = validPlan()
    data["week"].append(dict(data["week"][2]))
    assert errorsOf(data) == ('The plan: "week" must be a list of the 7 days, Monday to Sunday; it has 8.',)


def testDaysAreNamedInOrder():
    data = validPlan()
    data["week"][1]["day"] = "wednesday"
    del data["week"][2]["day"]
    assert errorsOf(data) == (
        'Tuesday "Pull": "day" must be "tuesday" (the week runs Monday to Sunday, in order), not "wednesday".',
        'Wednesday "Rest": "day" is missing.')


def testWeekNeedsAWorkout():
    data = validPlan()
    for index in (0, 1):
        data["week"][index] = {"day": data["week"][index]["day"], "title": "Rest", "restDay": True}
    assert errorsOf(data) == ("The plan: the week has no workout; every day is a rest day.",)


def testDayThatIsNotABlock():
    data = validPlan()
    data["week"][2] = "Rest"
    assert errorsOf(data) == ('Wednesday must be a {…} block with "day" and "title".',)


def testRestDayCantHaveExercises():
    data = validPlan()
    data["week"][2]["exercises"] = data["week"][1]["exercises"]
    assert errorsOf(data) == ("Wednesday \"Rest\": a rest day can't have exercises.",)
    data["week"][2]["exercises"] = []
    assert errorsOf(data) == ()


def testWorkoutDayNeedsExercises():
    data = validPlan()
    del data["week"][1]["exercises"]
    assert errorsOf(data) == ('Tuesday "Pull": "exercises" is missing (for a rest day, add "restDay": true).',)
    data["week"][1]["exercises"] = []
    assert errorsOf(data) == ('Tuesday "Pull": "exercises" must be a list with at least one exercise.',)


def testSameExerciseTwiceInOneDay():
    """A day logs each exercise once (one exerciseLogs row per exercise per day)."""
    data = validPlan()
    data["week"][1]["exercises"].append(dict(data["week"][1]["exercises"][0]))
    assert errorsOf(data) == (
        'Tuesday "Pull": "deadlift" appears more than once; each exercise can be in a day only once.',)


def testSameExerciseOnTwoDaysNeedsTheSameSettings():
    """Progress is tracked per exercise, so its settings can't differ; notes and rest time may."""
    data = validPlan()
    pullBench = dict(data["week"][0]["exercises"][0], notes="other cue", restSec=60)
    del pullBench["body"]
    data["week"][1]["exercises"].append(pullBench)
    assert errorsOf(data) == (
        '"benchPress" is on Monday "Push" and Tuesday "Pull" with different settings (body "upper" vs not set). '
        "Give it the same settings on both, or a different exerciseId on one.",)
    pullBench.update(body="upper")
    assert errorsOf(data) == ()


def testSetsMayDifferBetweenDays():
    """WD1.4: one exercise and one history, with 4 sets on Monday and 3 on Tuesday."""
    data = validPlan()
    data["week"][1]["exercises"].append(dict(data["week"][0]["exercises"][0], sets=3))
    plan = checkPlan(data).plan
    assert (plan.steps[0].exercises[0].sets, plan.steps[1].exercises[1].sets) == (4, 3)


# --- The flex day and its moves (WD1.1, WD1.2) --------------------------------------------------

flexPlace = 'Saturday "Flex"'


def withFlex() -> dict:
    """The valid plan plus Arms on Wednesday and a flex day on Saturday that makes up Pull, Push or Arms, in
    that order. Wednesday's wrist curl moves to the end of Saturday when it makes up Push."""
    data = validPlan()
    data["weeklyTarget"] = 3
    data["week"][2] = {"day": "wednesday", "title": "Arms", "exercises": [
        {"exerciseId": "curlMachine", "name": "Curl Machine", "equipment": "machine", "incrementKg": 5,
         "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 30},
        {"exerciseId": "wristCurl", "name": "Wrist Curl", "equipment": "barbell", "incrementKg": 2.5,
         "sets": 2, "repsMin": 12, "repsMax": 20, "weightKg": 30}]}
    data["week"][5] = {"day": "saturday", "title": "Flex", "makeUp": ["tuesday", "monday", "wednesday"],
                       "moves": [{"exerciseId": "wristCurl", "from": "wednesday", "to": "saturday", "when": ["monday"]}],
                       "exercises": [{"exerciseId": "abMachine", "name": "Ab Machine", "equipment": "machine",
                                      "incrementKg": 5, "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 40}]}
    return data


def flexErrors(**changes) -> tuple[str, ...]:
    """The errors of withFlex() with Saturday's fields changed (None removes one)."""
    data = withFlex()
    for key, value in changes.items():
        if value is None:
            data["week"][5].pop(key, None)
        else:
            data["week"][5][key] = value
    return errorsOf(data)


def move(**changes) -> dict:
    return {"exerciseId": "wristCurl", "from": "wednesday", "to": "saturday", "when": ["monday"], **changes}


def testTheFlexDayIsRead():
    plan = checkPlan(withFlex()).plan
    assert plan.steps[5].makeUp == (1, 0, 2) and scheduleDays(plan)[5].makeUp == (1, 0, 2)
    (wristCurl,) = plan.moves
    assert (wristCurl.exerciseId, wristCurl.fromDay, wristCurl.toDay, wristCurl.when) == ("wristCurl", 2, 5, (0,))
    assert wristCurl.exercise == plan.steps[2].exercises[1]  # with Wednesday's settings


def testOnlyOneFlexDay():
    data = withFlex()
    data["week"][1]["makeUp"] = ["monday"]
    assert errorsOf(data) == ('The plan: only one day can make up missed days, but Tuesday "Pull" and '
                              'Saturday "Flex" all have "makeUp".',)


def testAFlexDayIsAWorkoutDay():
    assert flexErrors(restDay=True, exercises=None, moves=None) == (
        f'{flexPlace}: a rest day can\'t make up missed days; give it exercises (its bonus workout) or leave '
        '"makeUp" out.',)


def testWhatTheFlexDayMakesUp():
    assert flexErrors(makeUp=[]) == (
        f'{flexPlace}: "makeUp" must be a list of days, like ["monday", "thursday"], not [].',)
    assert flexErrors(makeUp=["monday", "Tuesday", "monday"]) == (
        f'{flexPlace}: "makeUp" has "Tuesday", which isn\'t a day; days are "monday" to "sunday".',
        f'{flexPlace}: "makeUp" has "monday" more than once.')
    assert flexErrors(makeUp=["monday", "sunday", "thursday"], moves=None) == (
        f'{flexPlace}: "makeUp" can only list days before saturday, not "sunday".',
        f'{flexPlace}: "makeUp" lists "thursday", which is a rest day.')


def testMovesGoOnlyWithTheFlexDay():
    data = withFlex()
    data["week"][1]["moves"] = []
    assert errorsOf(data) == ('Tuesday "Pull": "moves" only goes with "makeUp", on the flex day.',)
    assert flexErrors(moves="wristCurl") == (
        f'{flexPlace}: "moves" must be a list of moves, like [{{"exerciseId": "…", "from": "friday", "to": '
        '"saturday", "when": ["monday"]}].',)


def testMoveFields():
    place = f"{flexPlace}, move 1"
    assert flexErrors(moves=["wristCurl"]) == (
        f'{place} must be a {{…}} block with "exerciseId", "from", "to" and "when".',)
    assert flexErrors(moves=[move(to="sat", exerciseId="wrist_curl", why="tired")]) == (
        f'{place}: unknown field "why".',
        f'{place}: "exerciseId" must be camelCase letters and digits starting with a small letter, like '
        '"benchPress", not "wrist_curl".',
        f'{place}: "to" must be a day, "monday" to "sunday", not "sat".')
    assert flexErrors(moves=[{"exerciseId": "wristCurl"}]) == (
        f'{place}: "from" is missing.', f'{place}: "to" is missing.', f'{place}: "when" is missing.')


def testWhereAMoveCanGo():
    place = f"{flexPlace}, move 1"
    assert flexErrors(moves=[move(**{"from": "saturday", "exerciseId": "abMachine", "to": "monday"})]) == (
        f'{place}: "from" can\'t be the flex day itself; its own exercises are only its bonus workout.',)
    assert flexErrors(moves=[move(to="wednesday")]) == (f'{place}: "from" and "to" are the same day.',)
    assert flexErrors(moves=[move(to="sunday")]) == (f'{place}: "to" is sunday, a rest day.',)
    assert flexErrors(moves=[move(when=["monday", "thursday"])]) == (
        f'{place}: "when" lists "thursday", which "makeUp" doesn\'t.',)
    assert flexErrors(moves=[move(exerciseId="benchPress")]) == (
        f'{place}: "benchPress" isn\'t in Wednesday "Arms".',)


def testAMoveCantPutAnExerciseInAWorkoutTwice():
    place = f"{flexPlace}, move 1"
    assert flexErrors(moves=[move(exerciseId="curlMachine", to="monday")]) == ()
    data = withFlex()
    data["week"][0]["exercises"].append(dict(data["week"][2]["exercises"][1]))  # Monday has a wrist curl too
    assert errorsOf(data) == (
        f'{place}: "wristCurl" is already in Monday "Push", which Saturday makes up; an exercise can be in a '
        "workout only once.",)
    assert flexErrors(moves=[move(to="tuesday", when=["tuesday"]), move(to="monday", when=["tuesday"])]) == (
        f'{flexPlace}, move 2: "wristCurl" already moves from wednesday when saturday makes up tuesday.',)


# --- Exercises ----------------------------------------------------------------------------------

def testRepsMinAboveRepsMax():
    data = validPlan()
    data["week"][0]["exercises"][0]["repsMin"] = 13
    assert errorsOf(data) == (f'{bench}: "repsMin" (13) is more than "repsMax" (12).',)


@pytest.mark.parametrize(("value", "shown"), [(True, "true"), (4.5, "4.5"), ("4", '"4"'), (None, "null")])
def testWholeNumbersMustBeWholeNumbers(value, shown):
    """JSON true is a number to Python, so it must be refused explicitly."""
    data = validPlan()
    data["week"][0]["exercises"][0]["sets"] = value
    assert errorsOf(data) == (f'{bench}: "sets" must be a whole number, not {shown}.',)


def testWeights():
    data = validPlan()
    benchPress = data["week"][0]["exercises"][0]
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
    benchPress = data["week"][0]["exercises"][0]
    del benchPress["incrementKg"], benchPress["body"]
    assert errorsOf(data) == (
        f'{bench}: needs "body" ("upper" or "lower") or "incrementKg", to know how much weight to add.',)


def testBodyweightExerciseHasNoWeight():
    data = validPlan()
    dips = data["week"][0]["exercises"][1]
    dips["weightKg"] = 10
    assert errorsOf(data) == (
        'Monday "Push", exercise 2 "Dips": a bodyweight exercise has no "weightKg"; its progress is counted '
        'in reps.',)
    del dips["weightKg"]
    dips["incrementKg"] = 2.5
    result = checkPlan(data)
    assert result.errors == ()
    assert result.warnings == (
        'Monday "Push", exercise 2 "Dips": "incrementKg" is ignored, because a bodyweight exercise '
        'progresses in reps.',)


def testCardioHasOnlyMinutes():
    walk = 'Monday "Push", exercise 3 "Incline Walk"'
    data = validPlan()
    data["week"][0]["exercises"][2]["sets"] = 3
    assert errorsOf(data) == (
        f'{walk}: "sets" doesn\'t belong to a cardio exercise; it has only "minutes", "notes", "setup", "howTo" '
        'and "form".',)
    data = validPlan()
    del data["week"][0]["exercises"][2]["minutes"]
    assert errorsOf(data) == (f'{walk}: "minutes" is missing.',)
    data = validPlan()
    data["week"][0]["exercises"][0]["minutes"] = 10
    assert errorsOf(data) == (f'{bench}: "minutes" is only for cardio exercises (add "type": "cardio").',)


def testChoicesAreListed():
    data = validPlan()
    data["week"][0]["exercises"][0]["equipment"] = "cable"
    data["week"][0]["exercises"][2]["type"] = "cardo"
    assert errorsOf(data) == (
        f'{bench}: "equipment" must be "barbell", "dumbbell", "bodyweight" or "machine", not "cable".',
        'Monday "Push", exercise 3 "Incline Walk": "type" must be "strength" or "cardio", not "cardo".')


def testIdsAreCamelCase():
    data = validPlan()
    data["week"][0]["exercises"][0]["exerciseId"] = "bench_press"
    assert errorsOf(data) == (
        f'{bench}: "exerciseId" must be camelCase letters and digits starting with a small letter, like '
        '"benchPress", not "bench_press".',)


def testTextFields():
    data = validPlan()
    data["week"][0]["exercises"][0]["name"] = "   "
    data["week"][0]["exercises"][1]["notes"] = "line one\nline two"
    data["week"][1]["title"] = "x" * 51
    assert errorsOf(data) == (
        'Monday "Push", exercise 1: "name" is empty.',
        'Monday "Push", exercise 2 "Dips": "notes" can\'t have line breaks or other control characters.',
        'Tuesday: "title" is longer than 50 characters.')


def testExerciseThatIsNotABlock():
    data = validPlan()
    data["week"][1]["exercises"] = ["Deadlift"]
    assert errorsOf(data) == ('Tuesday "Pull", exercise 1 must be a {…} block with an "exerciseId" and a "name".',)


# --- How-to (SC7.1) -----------------------------------------------------------------------------

def withHowTo() -> dict:
    """The valid plan with a how-to for Bench Press and Incline Walk."""
    data = validPlan()
    data["week"][0]["exercises"][0].update(
        setup="  Flat bench, barbell in a rack, safety pins at chest height ",
        howTo=["Lie back, eyes under the bar", "Grip a bit wider than shoulders", "Lower to mid-chest, press up"],
        form=["Shoulder blades pinched", "Feet flat on the floor"])
    data["week"][0]["exercises"][2].update(setup="Treadmill", howTo=["Incline 10, 5 km/h"])
    return data


def testHowToIsReadForTheTodayScreen():
    result = checkPlan(withHowTo())
    assert (result.errors, result.warnings) == ((), ())
    benchPress, dips, walk = result.plan.steps[0].exercises
    assert benchPress.setup == "Flat bench, barbell in a rack, safety pins at chest height"
    assert benchPress.howTo == ("Lie back, eyes under the bar", "Grip a bit wider than shoulders",
                                "Lower to mid-chest, press up")
    assert benchPress.form == ("Shoulder blades pinched", "Feet flat on the floor")
    assert (dips.setup, dips.howTo, dips.form) == (None, (), ())
    assert (walk.setup, walk.howTo, walk.form) == ("Treadmill", ("Incline 10, 5 km/h",), ())


def testHowToIsGivenOnceForAllSteps():
    """The how-to belongs to the exercise: a step that leaves a field out shows the one given elsewhere,
    and a step that gives its own keeps it. Like notes, it never has to match."""
    data = withHowTo()
    pullBench = {key: value for key, value in data["week"][0]["exercises"][0].items()
                 if key not in ("setup", "howTo", "form")}
    data["week"][1]["exercises"].insert(0, dict(pullBench, form=["Pause on the chest"]))
    plan = checkPlan(data).plan
    pushBench, pullBenchRead = plan.steps[0].exercises[0], plan.steps[1].exercises[0]
    assert pullBenchRead.setup == pushBench.setup and pullBenchRead.howTo == pushBench.howTo
    assert pullBenchRead.form == ("Pause on the chest",) and pushBench.form == ("Shoulder blades pinched",
                                                                                 "Feet flat on the floor")


def testHowToInAStoredPlanIsReadToo():
    plan = checkPlan(withHowTo(), strict=False).plan
    assert planExercises(plan)["benchPress"].form == ("Shoulder blades pinched", "Feet flat on the floor")


def testHowToProblems():
    data = validPlan()
    benchPress, dips, walk = data["week"][0]["exercises"]
    benchPress.update(howTo="Lie back and press", form=["Fine", 5], setup="x" * 301)
    dips.update(howTo=["Step"] * 13, form=["One", "  "])
    walk.update(howTo=["x" * 201], form=["line one\nline two"])
    dipsPlace, walkPlace = 'Monday "Push", exercise 2 "Dips"', 'Monday "Push", exercise 3 "Incline Walk"'
    assert errorsOf(data) == (
        f'{bench}: "setup" is longer than 300 characters.',
        f'{bench}: "howTo" must be a list of lines, like ["First step", "Second step"], not "Lie back and press".',
        f'{bench}: "form" line 2 must be text, not 5.',
        f'{dipsPlace}: "howTo" has 13 lines; at most 12 are allowed.',
        f'{dipsPlace}: "form" line 2 is empty.',
        f'{walkPlace}: "howTo" line 1 is longer than 200 characters.',
        f'{walkPlace}: "form" line 1 can\'t have line breaks or other control characters.')


def testEmptyHowToCountsAsNotGiven():
    data = validPlan()
    data["week"][0]["exercises"][0].update(setup=" ", howTo=[], form=[])
    benchPress = checkPlan(data).plan.steps[0].exercises[0]
    assert (benchPress.setup, benchPress.howTo, benchPress.form) == (None, (), ())


# --- How volume and 1RM count the weight, compound lifts (WD1.3) --------------------------------

def withLoads() -> dict:
    """The valid plan with a two-dumbbell lateral raise on Monday and the bench press logged as the plates
    on one side of a 20 kg bar."""
    data = validPlan()
    data["week"][0]["exercises"][0].update(platesPerSide=True, barKg=20, weightKg=30, compound=True)
    data["week"][0]["exercises"].append(
        {"exerciseId": "lateralRaise", "name": "Lateral Raise", "equipment": "dumbbell", "dumbbells": 2,
         "incrementKg": 1, "sets": 3, "repsMin": 12, "repsMax": 20, "weightKg": 8})
    return data


def testLoadSettingsAreRead():
    benchPress, dips, walk, lateralRaise = checkPlan(withLoads()).plan.steps[0].exercises
    assert (benchPress.platesPerSide, benchPress.barKg, benchPress.compound, benchPress.dumbbells) == (
        True, 20.0, True, None)
    assert (lateralRaise.dumbbells, lateralRaise.platesPerSide, lateralRaise.barKg, lateralRaise.compound) == (
        2, False, None, False)
    assert (dips.compound, walk.compound) == (False, False)


def testDumbbellExercisesSayHowManyDumbbells():
    raise_ = 'Monday "Push", exercise 4 "Lateral Raise"'
    data = withLoads()
    del data["week"][0]["exercises"][3]["dumbbells"]
    assert errorsOf(data) == (f'{raise_}: "dumbbells" is missing: 2 for one in each hand, 1 for a single dumbbell.',)
    data["week"][0]["exercises"][3]["dumbbells"] = 3
    assert errorsOf(data) == (f'{raise_}: "dumbbells" must be between 1 and 2, not 3.',)
    data = withLoads()
    data["week"][0]["exercises"][0]["dumbbells"] = 2
    assert errorsOf(data) == (f'{bench}: "dumbbells" is only for dumbbell exercises.',)


def testPlatesPerSideAndBarOnlyForBarbellsAndMachines():
    data = withLoads()
    data["week"][0]["exercises"][1].update(platesPerSide=True)
    data["week"][0]["exercises"][3].update(barKg=2)
    assert errorsOf(data) == (
        'Monday "Push", exercise 2 "Dips": "platesPerSide" is only for barbell and plate-loaded machine exercises.',
        'Monday "Push", exercise 4 "Lateral Raise": "barKg" is only for barbell and plate-loaded machine exercises.')
    data = withLoads()
    data["week"][0]["exercises"][0].update(platesPerSide="yes", barKg=20.005)
    assert errorsOf(data) == (f'{bench}: "platesPerSide" must be true or false, not "yes".',
                              f'{bench}: "barKg" can have at most 2 decimals, not 20.005.')


def testLoadSettingsMatchOnEveryDay():
    data = withLoads()
    data["week"][1]["exercises"].append(dict(data["week"][0]["exercises"][0], compound=False, barKg=15))
    assert errorsOf(data) == (
        '"benchPress" is on Monday "Push" and Tuesday "Pull" with different settings (barKg 20 vs 15, compound '
        "true vs false). Give it the same settings on both, or a different exerciseId on one.",)


def testCardioHasNoLoadSettings():
    data = validPlan()
    data["week"][0]["exercises"][2]["compound"] = True
    assert errorsOf(data) == (
        'Monday "Push", exercise 3 "Incline Walk": "compound" doesn\'t belong to a cardio exercise; it has only '
        '"minutes", "notes", "setup", "howTo" and "form".',)
