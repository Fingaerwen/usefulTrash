"""The bulk check in words (apps/diet/docs/plan.md 4g): the suggestion on Today's banner, with both blocks'
averages, their weigh-in counts and the rule that fired, and the newest check's outcome on the Targets tab. The
numbers are the ones that decided, to 0.01 kg."""

import datetime as dt

from ambrosia.rules.bulkCheck import Block, Comparison, Skipped
from ambrosia.state import BulkCheckView
from ambrosia.screens.common import months, shortDay


def signed(kg: float) -> str:
    """+0.25, −0.30 (a real minus sign)."""
    return f"{kg:+.2f}".replace("-", "−")


def blockRange(block: Block) -> str:
    """ "23 Nov - 6 Dec" """
    first, last = block.start, block.end
    return f"{first.day} {months[first.month - 1]} - {last.day} {months[last.month - 1]}"


def blockLine(block: Block) -> str:
    """ "23 Nov - 6 Dec: 81.13 kg, 2 weigh-ins" """
    count = f"{block.weighIns} weigh-in{'' if block.weighIns == 1 else 's'}"
    return f"{blockRange(block)}: {block.averageKg:.2f} kg, {count}"


def weeksBack(block: Block, compared: Block) -> int:
    return (block.start - compared.start).days // 7


def suggestionTitle(comparison: Comparison) -> str:
    """ "Add 150 kcal a day?" """
    return f"{'Add' if comparison.kcal > 0 else 'Remove'} {abs(comparison.kcal)} kcal a day?"


def ruleText(view: BulkCheckView, comparison: Comparison) -> str:
    """The rule that fired, with its numbers."""
    settings = view.settings
    weeks = weeksBack(view.check.block, comparison.compared)
    if comparison.rule == "regular":
        where = "below" if comparison.kcal > 0 else "above"
        return (f"{signed(comparison.rateKgPerWeek)} kg a week over {weeks} weeks, {where} your "
                f"{settings.rateMinKg:g} to {settings.rateMaxKg:g}.")
    if comparison.kcal > 0:
        return f"{signed(comparison.differenceKg)} kg against {weeks} weeks earlier: lower, a big miss."
    return (f"{signed(comparison.differenceKg)} kg against {weeks} weeks earlier: more than {settings.bigGainKg:g} kg, "
            f"a big miss.")


def outcomeText(view: BulkCheckView) -> str:
    """The newest check's outcome for the Targets tab, or when the first one is."""
    check = view.check
    if check is None:
        return f"First check {shortDay(view.nextCheck)}, when the first block ends."
    day = shortDay(check.checkDate)
    chosen = check.chosen
    if view.applied:
        return f"{day}: applied."
    if chosen is not None:
        verb = "adding" if chosen.kcal > 0 else "removing"
        return f"{day}: suggests {verb} {abs(chosen.kcal)} kcal a day" + (
            "." if view.suggestion is not None else ", not now.")
    ran = [part for part in (check.regular, check.bigMiss) if isinstance(part, Comparison)]
    if ran:
        numbers = ", ".join(f"{signed(part.rateKgPerWeek)} kg a week" if part.rule == "regular"
                            else f"{signed(part.differenceKg)} kg in {weeksBack(check.block, part.compared)} weeks"
                            for part in ran)
        return f"{day}: no change ({numbers})."
    return f"{day}: {skippedText(check.regular, check.bigMiss, check.minWeighIns, check.block)}"


def skippedText(regular: Skipped, bigMiss: Skipped, minWeighIns: int, block: Block) -> str:
    """Why neither check ran, in plain words."""
    if regular.why == "thin":
        return f"skipped, {block.weighIns} weigh-in{'' if block.weighIns == 1 else 's'} and it needs {minWeighIns}."
    if regular.why == "tooSoon" and bigMiss.why == "tooSoon":
        return (f"nothing to compare yet. The first big-miss check is {shortDay(bigMiss.firstOn)}, the first regular "
                f"one {shortDay(regular.firstOn)}.")
    thin = next(part.compared for part in (bigMiss, regular) if part.why == "comparedThin")
    return f"skipped, the block {blockRange(thin)} had {thin.weighIns} weigh-in{'' if thin.weighIns == 1 else 's'}."


def changeText(kcal: int, macro: str, grams: int) -> str:
    """ "+150 kcal, +38 g carbs" """
    return f"{kcal:+,} kcal, {grams:+} g {macro}".replace("-", "−")


def fromText(date: dt.date) -> str:
    return f"From {shortDay(date)}"
