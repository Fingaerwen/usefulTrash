"""The targets file, a day's targets, and training or rest days (Ambrosia plan 4f, AM3.1, AM3.2)."""

import copy
import datetime as dt
import json

import pytest

from ambrosia.rules.targets import (
    AppliedChange,
    DayTargets,
    TargetsImport,
    dayKind,
    macroGrams,
    planWeekFromRow,
    readTargetsFile,
    targetsFromJson,
    targetsOn,
    trainedDays,
)

example = {
    "format": "ambrosiaTargets", "version": 1, "name": "Bulk from 26 Oct",
    "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "restDay": {"kcal": 2900, "proteinG": 160, "fatG": 90, "carbsG": 365},
    "waterMl": 3000,
    "bulkCheck": {"firstBlockStart": "2026-10-26", "rateKgPerWeek": {"min": 0.15, "max": 0.35}, "stepKcal": 150,
                  "bigStepKcal": 250, "bigGainKg": 1.0, "minWeighIns": 8, "changeMacro": "carbs"},
}
moment = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.UTC)


def changed(**edits) -> dict:
    data = copy.deepcopy(example)
    for path, value in edits.items():
        where, *keys = path.split("__")
        target = data
        for key in [where, *keys][:-1]:
            target = target[key]
        last = [where, *keys][-1]
        if value is ...:
            del target[last]
        else:
            target[last] = value
    return data


def testTheExampleFileIsRead():
    checked = readTargetsFile(json.dumps(example))
    assert checked.problems == () and checked.warnings == ()
    targets = checked.targets
    assert targets.trainingDay == DayTargets(3200, 160, 90, 440) and targets.restDay.kcal == 2900
    assert targets.waterMl == 3000
    settings = targets.bulkCheck
    assert settings.firstBlockStart == dt.date(2026, 10, 26) and (settings.rateMinKg, settings.rateMaxKg) == (0.15, 0.35)
    assert (settings.stepKcal, settings.bigStepKcal, settings.bigGainKg) == (150, 250, 1.0)
    assert (settings.minWeighIns, settings.changeMacro) == (8, "carbs")


def testWithoutTheBulkCheckItsOff():
    """A file without the section switches the check off, for a cut, say (4f)."""
    checked = targetsFromJson(changed(bulkCheck=..., waterMl=...))
    assert checked.problems == () and checked.targets.bulkCheck is None and checked.targets.waterMl is None


@pytest.mark.parametrize("edits, problem", [
    ({"format": "gymPlan"}, '"format" must be "ambrosiaTargets"'),
    ({"version": 2}, '"version" must be 1'),
    ({"name": ""}, '"name" must be a short text'),
    ({"trainingDay": ...}, '"trainingDay" is missing'),
    ({"restDay__kcal": 290.5}, '"restDay.kcal" must be a whole number'),
    ({"restDay__proteinG": 900}, '"restDay.proteinG" must be a whole number from 0 to 500'),
    ({"restDay__sugarG": 5}, '"restDay.sugarG" isn\'t a field there'),
    ({"waterMl": -1}, '"waterMl" must be a whole number'),
    ({"bulkCheck__firstBlockStart": "2026-10-27"}, "must be a Monday"),
    ({"bulkCheck__rateKgPerWeek": {"min": 0.35, "max": 0.15}}, "min below max"),
    ({"bulkCheck__stepKcal": 0}, '"bulkCheck.stepKcal"'),
    ({"bulkCheck__minWeighIns": 20}, '"bulkCheck.minWeighIns"'),
    ({"bulkCheck__changeMacro": "protein"}, '"carbs" or "fat"'),
    ({"bulkCheck__wait": 3}, '"bulkCheck.wait" isn\'t a setting'),
    ({"extra": True}, '"extra" isn\'t a targets field'),
])
def testEveryProblemIsSaidInPlainWords(edits, problem):
    checked = targetsFromJson(changed(**edits))
    assert checked.targets is None
    assert any(problem in line for line in checked.problems), checked.problems


def testAllProblemsAreListedAtOnce():
    checked = targetsFromJson(changed(version=3, restDay__kcal="lots", bulkCheck__changeMacro="sugar"))
    assert len(checked.problems) == 3


def testNotJsonAtAll():
    assert readTargetsFile(b"\xff\xfe nope").problems == ("This isn't a targets file: it can't be read as JSON.",)
    assert targetsFromJson([1, 2]).targets is None


def testMacrosFarFromTheKcalAreAWarningOnly():
    checked = targetsFromJson(changed(trainingDay__carbsG=200))  # 640 + 810 + 800 = 2,250 of 3,200
    assert checked.targets is not None
    assert checked.warnings == ("trainingDay: protein, fat and carbs add up to 2,250 kcal, more than 10% from its "
                                "3,200 kcal.",)


def testAChangeTakesGramsFromItsMacro():
    assert macroGrams(150, "carbs") == 38 and macroGrams(-150, "carbs") == -38  # 37.5, a half away from zero
    assert macroGrams(250, "fat") == 28 and macroGrams(250, "carbs") == 63


def testADaysTargetsAreTheImportInEffectPlusItsChanges():
    first = TargetsImport("i1", moment, dt.date(2026, 10, 25), targetsFromJson(example).targets)
    later = TargetsImport("i2", moment + dt.timedelta(days=30), dt.date(2026, 11, 24),
                          targetsFromJson(changed(trainingDay__kcal=3400)).targets)
    changes = [AppliedChange("i1", dt.date(2026, 11, 22), 250, "carbs", 63),
               AppliedChange("i1", dt.date(2026, 12, 6), 150, "carbs", 38),
               AppliedChange("i2", dt.date(2026, 12, 20), -150, "carbs", -38)]
    assert targetsOn([first], [], dt.date(2026, 10, 24), "training") is None  # before any import
    assert targetsOn([first], changes, dt.date(2026, 11, 21), "training") == DayTargets(3200, 160, 90, 440)
    assert targetsOn([first], changes, dt.date(2026, 11, 22), "rest") == DayTargets(3150, 160, 90, 428)
    # A newer file replaces the targets, changes included; only its own changes count on it.
    assert targetsOn([first, later], changes, dt.date(2026, 12, 6), "training") == DayTargets(3400, 160, 90, 440)
    assert targetsOn([first, later], changes, dt.date(2026, 12, 20), "training") == DayTargets(3250, 160, 90, 402)


def planRow(days: list[dict], effective: dt.date = dt.date(2026, 10, 1), importId: str = "p1") -> dict:
    return {"id": importId, "effectiveDate": effective, "importedAt": moment, "planJson": {"week": days}}


workout, rest, flex = {"day": "x", "exercises": []}, {"day": "x", "restDay": True}, {"day": "x", "makeUp": ["monday"]}


def testTrainingAndRestDaysFollowTheGymPlan():
    """AM3.2: fixed sessions are training days, the flex day once you've trained on it, the rest day rests."""
    plans = [planWeekFromRow(planRow([workout] * 5 + [flex, rest]))]
    saturday, sunday = dt.date(2026, 10, 31), dt.date(2026, 11, 1)
    assert dayKind(plans, set(), dt.date(2026, 10, 26)) == "training"  # a Monday, trained or not
    assert dayKind(plans, set(), saturday) == "rest"
    assert dayKind(plans, {saturday}, saturday) == "training"
    assert dayKind(plans, {sunday}, sunday) == "rest"
    assert dayKind([], set(), sunday) == "training"  # no plan Ambrosia can read
    newer = planWeekFromRow(planRow([rest] * 6 + [workout], dt.date(2026, 10, 30), "p2"))
    assert dayKind([*plans, newer], set(), sunday) == "training" and dayKind([*plans, newer], set(), saturday) == "rest"
    assert planWeekFromRow({"id": "p3", "effectiveDate": moment.date(), "importedAt": moment,
                            "planJson": {"cycle": []}}) is None


def testTrainedMeansSomethingDoneInTalos():
    day = dt.date(2026, 10, 26)
    rows = [{"date": day, "sets": [{"reps": 8}], "minutes": None, "skipped": False, "deleted": False},
            {"date": day + dt.timedelta(1), "sets": [], "minutes": None, "skipped": True, "deleted": False},
            {"date": day + dt.timedelta(2), "sets": [], "minutes": 20, "skipped": False, "deleted": False},
            {"date": day + dt.timedelta(3), "sets": [{"reps": 8}], "minutes": None, "skipped": False, "deleted": True},
            {"date": day + dt.timedelta(4), "sets": [], "minutes": None, "skipped": False, "deleted": False}]  # an Undo
    assert trainedDays(rows) == {day, day + dt.timedelta(2)}
