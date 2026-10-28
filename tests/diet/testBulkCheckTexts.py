"""The bulk check in words (ambrosia/screens/bulkCheck.py, 4g): the banner's rule with its numbers, and the newest
check's outcome on the Targets tab, for each way a check can go."""

import copy
import datetime as dt

from ambrosia.rules.bulkCheck import checkBlock
from ambrosia.rules.targets import targetsFromJson
from ambrosia.screens.bulkCheck import blockLine, outcomeText, ruleText, suggestionTitle
from ambrosia.state import BulkCheckView

example = {
    "format": "ambrosiaTargets", "version": 1, "name": "Bulk from 26 Oct",
    "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "restDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "bulkCheck": {"firstBlockStart": "2026-10-26", "rateKgPerWeek": {"min": 0.15, "max": 0.35}, "stepKcal": 150,
                  "bigStepKcal": 250, "bigGainKg": 2.0, "minWeighIns": 2, "changeMacro": "carbs",
                  "regularWeeks": 8, "bigMissWeeks": 4},
}
settings = targetsFromJson(copy.deepcopy(example)).targets.bulkCheck
firstMonday = dt.date(2026, 10, 26)


def fridays(startKg: float, kgPerWeek: float, weeks: int = 12) -> dict[dt.date, float]:
    return {firstMonday + dt.timedelta(days=4 + 7 * week): round(startKg + kgPerWeek * week, 2) for week in range(weeks)}


def view(weights, index, applied=False, dismissed=False) -> BulkCheckView:
    check = checkBlock(settings, weights, [], index)
    suggestion = None if applied or dismissed else check.chosen
    return BulkCheckView(check, suggestion, applied, check.checkDate + dt.timedelta(days=14), settings, "import1")


def testTheRegularChecksSuggestion():
    shown = view(fridays(80.0, 0.05), 4)
    assert suggestionTitle(shown.suggestion) == "Add 150 kcal a day?"
    assert ruleText(shown, shown.suggestion) == "+0.05 kg a week over 8 weeks, below your 0.15 to 0.35 kg a week."
    assert blockLine(shown.check.block) == "21 Dec - 3 Jan: 80.43 kg, 2 weigh-ins"
    assert outcomeText(shown) == "Sun 3 Jan: suggests adding 150 kcal a day."


def testABigMissTooHigh():
    shown = view(fridays(80.0, 0.6), 2)
    assert suggestionTitle(shown.suggestion) == "Remove 250 kcal a day?"
    assert ruleText(shown, shown.suggestion) == "+2.40 kg against 4 weeks earlier: more than 2 kg, a big miss."


def testOutcomesWithoutASuggestion():
    assert outcomeText(view(fridays(80.0, 0.25), 4)) == "Sun 3 Jan: no change (+0.25 kg a week, +1.00 kg in 4 weeks)."
    assert outcomeText(view(fridays(80.0, 0.25), 1)) == (
        "Sun 22 Nov: nothing to compare yet. The first big-miss check is Sun 6 Dec, the first regular one Sun 3 Jan.")
    assert outcomeText(view(fridays(80.0, 0.05), 4, applied=True)) == "Sun 3 Jan: applied."
    assert outcomeText(view(fridays(80.0, 0.05), 4, dismissed=True)) == (
        "Sun 3 Jan: suggests adding 150 kcal a day, you tapped Not now.")
    thin = fridays(80.0, 0.25)
    del thin[firstMonday + dt.timedelta(days=4 + 7 * 8)]
    assert outcomeText(view(thin, 4)) == "Sun 3 Jan: skipped, 1 weigh-in and it needs 2."
    comparedThin = fridays(80.0, 0.25)
    del comparedThin[firstMonday + dt.timedelta(days=4)]
    assert outcomeText(view(comparedThin, 2)) == "Sun 6 Dec: skipped, the block 26 Oct - 8 Nov had 1 weigh-in."
