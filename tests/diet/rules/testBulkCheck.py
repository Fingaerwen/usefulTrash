"""The bulk check (Ambrosia plan 4g, AM6.1, AM6.2, AM10.1, AM10.2): blocks, averages, both checks, thin blocks,
baselines after calorie changes, and your key dates with the Friday settings (regular 8 weeks, big miss 4)."""

import copy
import datetime as dt

import pytest

from ambrosia.rules.bulkCheck import (
    Comparison,
    Skipped,
    baselineFor,
    block,
    calorieChangeDates,
    checkBlock,
    latestCheck,
    nextCheckDate,
)
from ambrosia.rules.targets import AppliedChange, TargetsImport, targetsFromJson

example = {
    "format": "ambrosiaTargets", "version": 1, "name": "Bulk from 26 Oct",
    "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "restDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "bulkCheck": {"firstBlockStart": "2026-10-26", "rateKgPerWeek": {"min": 0.15, "max": 0.35}, "stepKcal": 150,
                  "bigStepKcal": 250, "bigGainKg": 2.0, "minWeighIns": 2, "changeMacro": "carbs",
                  "regularWeeks": 8, "bigMissWeeks": 4},
}
firstMonday = dt.date(2026, 10, 26)
importedAt = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.UTC)


def targets(**bulkCheck):
    data = copy.deepcopy(example)
    data["bulkCheck"].update(bulkCheck)
    checked = targetsFromJson(data)
    assert checked.problems == ()
    return checked.targets


def imported(effective=dt.date(2026, 10, 25), importId="import1", kcal=3200) -> TargetsImport:
    data = copy.deepcopy(example)
    data["trainingDay"]["kcal"] = data["restDay"]["kcal"] = kcal
    found = targetsFromJson(data).targets
    return TargetsImport(importId, dt.datetime.combine(effective, dt.time(12), dt.UTC), effective, found)


def friday(blockIndex: int, second: bool = False) -> dt.date:
    return firstMonday + dt.timedelta(days=14 * blockIndex + (11 if second else 4))


def fridays(startKg: float, kgPerWeek: float, blocks: int) -> dict[dt.date, float]:
    """A weigh-in every Friday from 30 Oct, on a straight line."""
    return {firstMonday + dt.timedelta(days=4 + 7 * week): round(startKg + kgPerWeek * week, 2)
            for week in range(2 * blocks)}


def settings():
    return targets().bulkCheck


def check(weights, index, changeDates=()):
    return checkBlock(settings(), weights, list(changeDates), index)


# --- Blocks --------------------------------------------------------------------------------------

def testBlocksAreTwoFullWeeksFromTheFirstMonday():
    first = block(settings(), {}, 0)
    assert (first.start, first.end) == (dt.date(2026, 10, 26), dt.date(2026, 11, 8))
    assert block(settings(), {}, 2).end == dt.date(2026, 12, 6)
    assert block(settings(), {}, 4).end == dt.date(2027, 1, 3)
    assert first.weighIns == 0 and first.averageKg is None


def testEveryWeighInCountsWhateverTheDay():
    """AM10.1: a Tuesday counts like a Friday. One before the first block doesn't count."""
    weights = {dt.date(2026, 10, 25): 70.0, dt.date(2026, 10, 27): 80.0, friday(0): 80.5, dt.date(2026, 11, 8): 81.0}
    found = block(settings(), weights, 0)
    assert found.weighIns == 3 and found.averageKg == 80.5


def testAveragesRoundAHalfAwayFromZero():
    """80.025 → 80.03 (Python's round would give 80.02)."""
    assert block(settings(), {friday(0): 80.0, friday(0, True): 80.05}, 0).averageKg == 80.03
    assert block(settings(), {friday(0): 80.0, friday(0, True): 80.04}, 0).averageKg == 80.02


# --- Your key dates (4g) with the Friday settings -------------------------------------------------

def testOnTargetNothingIsSuggestedAndTheKeyDatesHold():
    """0.25 kg a week, right on the line: 8 and 22 Nov compare nothing, 6 Dec is the first big miss (block 3
    against block 1 in the plan's counting), 3 Jan the first regular check."""
    weights = fridays(80.0, 0.25, 6)
    for index in (0, 1):
        result = check(weights, index)
        assert isinstance(result.regular, Skipped) and result.regular.why == "tooSoon"
        assert result.regular.firstOn == dt.date(2027, 1, 3)
        assert isinstance(result.bigMiss, Skipped) and result.bigMiss.firstOn == dt.date(2026, 12, 6)
        assert result.chosen is None
    sixthDec = check(weights, 2)
    assert sixthDec.checkDate == dt.date(2026, 12, 6)
    assert isinstance(sixthDec.regular, Skipped) and sixthDec.regular.firstOn == dt.date(2027, 1, 3)
    assert sixthDec.bigMiss == Comparison("bigMiss", block(settings(), weights, 0), 1.0, None, 0, None)
    thirdJan = check(weights, 4)
    assert thirdJan.checkDate == dt.date(2027, 1, 3)
    assert thirdJan.regular.compared.start == firstMonday and thirdJan.regular.rateKgPerWeek == 0.25
    assert thirdJan.bigMiss.compared.start == dt.date(2026, 11, 23) and thirdJan.bigMiss.differenceKg == 1.0
    assert thirdJan.chosen is None


def testTooSlowAddsTheStep():
    """0.05 kg a week: the regular check on 3 Jan sees 0.05 kg a week and adds 150 kcal. The big miss sees +0.20
    kg in 4 weeks, no big miss."""
    result = check(fridays(80.0, 0.05, 6), 4)
    assert (result.regular.rateKgPerWeek, result.regular.kcal, result.regular.reason) == (0.05, 150, "rate")
    assert (result.bigMiss.differenceKg, result.bigMiss.kcal) == (0.2, 0)
    assert result.chosen is result.regular


def testTooFastRemovesTheStep():
    result = check(fridays(80.0, 0.45, 6), 4)
    assert (result.regular.rateKgPerWeek, result.regular.kcal) == (0.45, -150)
    assert result.bigMiss.differenceKg == 1.8 and result.bigMiss.kcal == 0  # 2 kg or less isn't a big miss
    assert result.chosen.kcal == -150


@pytest.mark.parametrize("newestKg, rate, kcal", [
    (81.20, 0.15, 0),  # 1.20 / 8 = 0.15: on the edge of the range is inside it
    (81.19, 0.15, 0),  # 0.14875 rounds to 0.15 first, so the shown number decides
    (81.15, 0.14, 150),  # 0.14375 → 0.14
    (82.80, 0.35, 0),
    (82.84, 0.36, -150),  # 0.355 → 0.36 (a half away from zero)
    (79.00, -0.13, 150),  # −0.125 → −0.13
])
def testTheRateIsRoundedBeforeItsCompared(newestKg, rate, kcal):
    weights = {friday(0): 80.0, friday(0, True): 80.0, friday(4): newestKg, friday(4, True): newestKg,
               friday(2): newestKg, friday(2, True): newestKg}
    regular = check(weights, 4).regular
    assert (regular.rateKgPerWeek, regular.kcal) == (rate, kcal)


@pytest.mark.parametrize("newestKg, kcal, reason", [
    (80.99, 250, "bigMissLow"),  # lower than 4 weeks earlier
    (81.00, 0, None),  # the same isn't lower
    (83.00, 0, None),  # exactly 2 kg higher isn't more than 2 kg
    (83.01, -250, "bigMissHigh"),
])
def testTheBigMiss(newestKg, kcal, reason):
    weights = {friday(0): 81.0, friday(0, True): 81.0, friday(2): newestKg, friday(2, True): newestKg}
    bigMiss = check(weights, 2).bigMiss
    assert (bigMiss.kcal, bigMiss.reason) == (kcal, reason)


def testBothTheSameWayOnlyTheBigMissApplies():
    """AM6.2: 250, not 400."""
    weights = {**{friday(0): 80.0, friday(0, True): 80.0}, **{friday(2): 80.5, friday(2, True): 80.5},
               **{friday(4): 80.2, friday(4, True): 80.2}}
    result = check(weights, 4)
    assert result.regular.kcal == 150 and result.bigMiss.kcal == 250
    assert result.chosen is result.bigMiss


def testOppositeWaysNothingChanges():
    weights = {**{friday(0): 80.0, friday(0, True): 80.0}, **{friday(2): 78.0, friday(2, True): 78.0},
               **{friday(4): 80.5, friday(4, True): 80.5}}
    result = check(weights, 4)
    assert result.regular.kcal == 150 and result.bigMiss.kcal == -250
    assert result.chosen is None


# --- Thin blocks (AM6.1, AM10.2) ------------------------------------------------------------------

def testAMissedFridayLeavesTheBlockOut():
    """Minimum 2: a block with one Friday skips its own checks."""
    weights = fridays(80.0, 0.05, 6)
    del weights[friday(4, True)]
    result = check(weights, 4)
    assert result.regular == Skipped("regular", "thin", None, None) and result.bigMiss.why == "thin"
    assert result.chosen is None


def testAThinBlockIsNeverComparedAgainst():
    """…and any later check that would compare against it is skipped too."""
    weights = fridays(80.0, 0.05, 6)
    del weights[friday(0)]
    result = check(weights, 4)
    assert result.regular.why == "comparedThin" and result.regular.compared.weighIns == 1
    assert isinstance(result.bigMiss, Comparison)  # block 2 is fine


def testAMinimumOfOneCountsAOneFridayBlock():
    weights = fridays(80.0, 0.05, 6)
    del weights[friday(4, True)]
    result = checkBlock(targets(minWeighIns=1).bulkCheck, weights, [], 4)
    assert result.regular.kcal == 150


# --- Baselines after a calorie change -------------------------------------------------------------

@pytest.mark.parametrize("appliedOn, baseline", [
    (dt.date(2026, 12, 6), 3),  # the check Sunday: the block starting the next Monday
    (dt.date(2026, 12, 7), 3),  # the Monday after: that Monday's block
    (dt.date(2026, 12, 8), 4),  # any later: the one after
    (dt.date(2026, 12, 20), 4),
])
def testTheBaselineAfterAChange(appliedOn, baseline):
    assert baselineFor(settings(), [appliedOn], 10) == baseline
    assert baselineFor(settings(), [appliedOn], baseline - 1) == 0  # blocks before it keep the old one


def testNothingBeforeTheBaselineIsComparedWithAnythingAfter():
    """A change applied on 6 Dec: block 4 (3 Jan) can't look back past block 3, so both checks wait. The big miss
    first runs on 17 Jan (block 5 against block 3), the regular on 14 Feb."""
    weights = fridays(80.0, 0.05, 9)
    result = check(weights, 4, [dt.date(2026, 12, 6)])
    assert result.regular == Skipped("regular", "tooSoon", None, dt.date(2027, 2, 14))
    assert result.bigMiss == Skipped("bigMiss", "tooSoon", None, dt.date(2027, 1, 17))
    assert isinstance(check(weights, 5, [dt.date(2026, 12, 6)]).bigMiss, Comparison)
    assert isinstance(check(weights, 7, [dt.date(2026, 12, 6)]).regular, Comparison)


def change(fromDate, importId="import1", kcal=150) -> AppliedChange:
    return AppliedChange(importId, fromDate, kcal, "carbs", 38)


def testCalorieChangesAreAppliedChangesAndImportsWithOtherKcal():
    first = imported(dt.date(2026, 10, 25), "a")
    sameKcal = imported(dt.date(2026, 11, 2), "b")  # same kcal, so not a calorie change
    moreKcal = imported(dt.date(2026, 12, 9), "c", kcal=3500)
    assert calorieChangeDates([first], []) == []  # the first import isn't a change
    assert calorieChangeDates([first, sameKcal, moreKcal], [change(dt.date(2026, 11, 22), "b")]) == [
        dt.date(2026, 11, 22), dt.date(2026, 12, 9)]


def testAnImportMatchingTheChangedTargetsIsntAChange():
    """3,200 + an applied 150 = 3,350: a new file with 3,350 keeps the calories as they were."""
    first = imported(dt.date(2026, 10, 25), "a")
    applied = change(dt.date(2026, 12, 7), "a")
    again = imported(dt.date(2026, 12, 21), "b", kcal=3350)
    assert calorieChangeDates([first, again], [applied]) == [dt.date(2026, 12, 7)]


# --- The newest check by today --------------------------------------------------------------------

def testLatestCheckIsTheNewestBlockEndingByToday():
    imports = [imported()]
    weights = fridays(80.0, 0.25, 4)
    assert latestCheck(imports, [], weights, dt.date(2026, 11, 7)) is None  # no block has ended
    assert latestCheck(imports, [], weights, dt.date(2026, 11, 8)).checkDate == dt.date(2026, 11, 8)
    assert latestCheck(imports, [], weights, dt.date(2026, 12, 5)).checkDate == dt.date(2026, 11, 22)
    assert latestCheck(imports, [], weights, dt.date(2026, 12, 6)).checkDate == dt.date(2026, 12, 6)


def testLatestCheckUsesTodaysFileAndItsOffWithoutOne():
    weights = fridays(80.0, 0.0, 4)
    assert latestCheck([], [], weights, dt.date(2026, 12, 6)) is None
    data = copy.deepcopy(example)
    del data["bulkCheck"]
    cut = TargetsImport("cut", importedAt, dt.date(2026, 12, 1), targetsFromJson(data).targets)
    assert latestCheck([imported(), cut], [], weights, dt.date(2026, 12, 6)) is None
    assert latestCheck([imported(), cut], [], weights, dt.date(2026, 11, 30)).checkDate == dt.date(2026, 11, 22)


def testLatestCheckTakesTheChangesIntoAccount():
    """Down to 79.8 kg in the block ending 6 Dec: a big miss. With a change applied on 22 Nov the block from
    23 Nov is the baseline, so 6 Dec compares nothing."""
    weights = {**fridays(80.0, 0.0, 4), friday(2): 79.8, friday(2, True): 79.8}
    imports = [imported()]
    assert latestCheck(imports, [], weights, dt.date(2026, 12, 6)).chosen.reason == "bigMissLow"
    later = latestCheck(imports, [change(dt.date(2026, 11, 22))], weights, dt.date(2026, 12, 6))
    assert later.chosen is None and later.bigMiss.why == "tooSoon"


def testNextCheckDate():
    imports = [imported()]
    assert nextCheckDate(imports, dt.date(2026, 10, 25)) == dt.date(2026, 11, 8)  # before the first block
    assert nextCheckDate(imports, dt.date(2026, 10, 28)) == dt.date(2026, 11, 8)
    assert nextCheckDate(imports, dt.date(2026, 11, 8)) == dt.date(2026, 11, 22)
    assert nextCheckDate([], dt.date(2026, 11, 8)) is None


def testASettingWithMoreDecimalsIsComparedExactly():
    """A rate of 0.125 kg a week from the file stays 0.125: a measured 0.12 is below it, 0.13 isn't."""
    loose = targets(rateKgPerWeek={"min": 0.125, "max": 0.35}).bulkCheck
    low = {friday(0): 80.0, friday(0, True): 80.0, friday(4): 80.96, friday(4, True): 80.96}
    high = {friday(0): 80.0, friday(0, True): 80.0, friday(4): 81.04, friday(4, True): 81.04}
    assert checkBlock(loose, low, [], 4).regular.kcal == 150  # 0.96 / 8 = 0.12
    assert checkBlock(loose, high, [], 4).regular.kcal == 0  # 1.04 / 8 = 0.13
