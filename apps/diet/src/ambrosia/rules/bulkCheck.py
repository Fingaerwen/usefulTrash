"""The bulk check (apps/diet/docs/plan.md 4g, AM3.3, AM6.1, AM6.2, AM10.1, AM10.2): your Claude project's
weigh-in protocol, run on Talon's weigh-ins with the settings of the targets file in effect.

Blocks are two full Monday–Sunday weeks from the first block's start. Every weigh-in counts, whatever the day
(AM10.1). On each block's last day (a Sunday) two checks compare its average with an earlier block's: the regular
check with the block regularWeeks earlier, giving the weekly rate, and the big miss with the block bigMissWeeks
earlier. A block with fewer weigh-ins than the minimum is left out entirely (AM6.1). After a calorie change the
first block starting on or after the day it counts from is a new baseline, and nothing before a baseline is ever
compared with anything from it on. The check only suggests: your targets change when you tap Apply.

Averages, differences and the rate are worked out exactly in hundredths of a kg, each rounded a half away from
zero, so the numbers shown are the ones that decide. Nothing here reads a database or the clock.
"""

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from ambrosia.rules.targets import (
    AppliedChange,
    BulkCheckSettings,
    TargetsImport,
    dayKinds,
    importInEffect,
    targetsOn,
)

blockDays = 14  # two full Monday–Sunday weeks


@dataclass(frozen=True, slots=True)
class Block:
    """One block of two weeks and its weigh-ins."""

    index: int  # 0 is the first block, from firstBlockStart
    start: dt.date  # a Monday
    weighIns: int
    averageKg: float | None  # to 0.01 kg. None without weigh-ins

    @property
    def end(self) -> dt.date:
        """The block's last day, a Sunday: its check day."""
        return self.start + dt.timedelta(days=blockDays - 1)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One check that ran: the newest block against an earlier one, and what it calls for."""

    rule: str  # regular or bigMiss
    compared: Block
    differenceKg: float  # the newest block's average minus the compared one's, to 0.01 kg
    rateKgPerWeek: float | None  # the regular check's weekly rate, to 0.01 kg. None for a big miss
    kcal: int  # +step, −step, or 0 for no change
    reason: str | None  # the targetChanges reason (rate, bigMissLow or bigMissHigh). None for no change


@dataclass(frozen=True, slots=True)
class Skipped:
    """One check that couldn't run, and why (the screens say it in words)."""

    rule: str  # regular or bigMiss
    why: str  # thin (this block), comparedThin, or tooSoon (no block that far back from the baseline on)
    compared: Block | None  # comparedThin: the block it would have used
    firstOn: dt.date | None  # tooSoon: the first check day it can run, counted from the baseline


@dataclass(frozen=True, slots=True)
class BlockCheck:
    """A check day's outcome."""

    block: Block
    regular: Comparison | Skipped
    bigMiss: Comparison | Skipped
    minWeighIns: int

    @property
    def checkDate(self) -> dt.date:
        return self.block.end

    @property
    def chosen(self) -> Comparison | None:
        """The comparison whose change is suggested (AM6.2): the big miss's when both call for a change the same
        way, nothing when they point opposite ways, otherwise whichever calls for one."""
        regular = self.regular if isinstance(self.regular, Comparison) and self.regular.kcal else None
        big = self.bigMiss if isinstance(self.bigMiss, Comparison) and self.bigMiss.kcal else None
        if regular and big:
            return big if (regular.kcal > 0) == (big.kcal > 0) else None
        return big or regular


# --- Exact numbers -------------------------------------------------------------------------------

def _roundHalfAway(value: Fraction) -> int:
    """A whole number, a half rounding away from zero (2.5 → 3, −2.5 → −3)."""
    whole = math.floor(abs(value) + Fraction(1, 2))
    return whole if value >= 0 else -whole


def _hundredths(kg: float) -> int:
    """A stored weight (two decimals at most, numeric(5,2)) in whole hundredths of a kg."""
    return round(kg * 100)


def _exactHundredths(setting: float) -> Fraction:
    """A setting from the file in hundredths of a kg, exactly as written (0.125 stays 12.5)."""
    return Fraction(str(setting)) * 100


# --- Blocks and baselines ------------------------------------------------------------------------

def blockOf(settings: BulkCheckSettings, date: dt.date) -> int:
    """The index of the block holding a date (negative before the first block)."""
    return (date - settings.firstBlockStart).days // blockDays


def block(settings: BulkCheckSettings, weights: Mapping[dt.date, float], index: int) -> Block:
    """A block with its weigh-ins (every one, whatever the day, AM10.1) and their average."""
    start = settings.firstBlockStart + dt.timedelta(days=blockDays * index)
    inside = [_hundredths(kg) for date, kg in weights.items() if start <= date < start + dt.timedelta(days=blockDays)]
    average = _roundHalfAway(Fraction(sum(inside), len(inside))) / 100 if inside else None
    return Block(index, start, len(inside), average)


def calorieChangeDates(imports: Sequence[TargetsImport], changes: Sequence[AppliedChange]) -> list[dt.date]:
    """The days calorie changes count from (4g): every applied change, and every import whose kcal (training or
    rest day) differs from the targets in effect just before it. The first import isn't a change."""
    dates = [change.fromDate for change in changes]
    ordered = sorted(imports, key=lambda found: (found.effectiveDate, found.importedAt, found.importId))
    for position, found in enumerate(ordered):
        before = ordered[:position]
        for kind in dayKinds:
            previous = targetsOn(before, changes, found.effectiveDate, kind)
            if previous is not None and previous.kcal != found.targets.forKind(kind).kcal:
                dates.append(found.effectiveDate)
                break
    return sorted(dates)


def baselineFor(settings: BulkCheckSettings, changeDates: Sequence[dt.date], index: int) -> int:
    """The baseline block in effect for block `index`: the first block, or after a calorie change the first block
    starting on or after the day it counts from (applied on a check Sunday or the Monday after, that's the
    block starting that Monday, any later the one after)."""
    baseline = 0
    for date in changeDates:
        first = -(-(date - settings.firstBlockStart).days // blockDays)  # the first block starting on or after it
        if baseline < first <= index:
            baseline = first
    return baseline


# --- The checks ----------------------------------------------------------------------------------

def checkBlock(settings: BulkCheckSettings, weights: Mapping[dt.date, float], changeDates: Sequence[dt.date],
               index: int) -> BlockCheck:
    """Both checks on block `index`'s last day (4g)."""
    newest = block(settings, weights, index)
    baseline = baselineFor(settings, changeDates, index)

    def compare(rule: str, weeks: int) -> Comparison | Skipped:
        back = index - weeks // 2
        if newest.weighIns < settings.minWeighIns:
            return Skipped(rule, "thin", None, None)
        if back < baseline:
            first = block(settings, weights, baseline + weeks // 2)
            return Skipped(rule, "tooSoon", None, first.end)
        compared = block(settings, weights, back)
        if compared.weighIns < settings.minWeighIns:
            return Skipped(rule, "comparedThin", compared, None)
        difference = _hundredths(newest.averageKg) - _hundredths(compared.averageKg)
        if rule == "regular":
            rate = _roundHalfAway(Fraction(difference, weeks))
            low, high = _exactHundredths(settings.rateMinKg), _exactHundredths(settings.rateMaxKg)
            kcal, reason = ((settings.stepKcal, "rate") if rate < low else
                            (-settings.stepKcal, "rate") if rate > high else (0, None))
            return Comparison(rule, compared, difference / 100, rate / 100, kcal, reason)
        kcal, reason = ((settings.bigStepKcal, "bigMissLow") if difference < 0 else
                        (-settings.bigStepKcal, "bigMissHigh") if difference > _exactHundredths(settings.bigGainKg)
                        else (0, None))
        return Comparison(rule, compared, difference / 100, None, kcal, reason)

    return BlockCheck(newest, compare("regular", settings.regularWeeks), compare("bigMiss", settings.bigMissWeeks),
                      settings.minWeighIns)


def settingsOn(imports: Sequence[TargetsImport], date: dt.date) -> BulkCheckSettings | None:
    """The bulk check's settings from the targets file in effect on a date. None: the check is off."""
    found = importInEffect(imports, date)
    return found.targets.bulkCheck if found else None


def latestCheck(imports: Sequence[TargetsImport], changes: Sequence[AppliedChange],
                weights: Mapping[dt.date, float], today: dt.date) -> BlockCheck | None:
    """The newest check day's outcome by today, with the settings of the file in effect today. None when the
    check is off (no targets file, or one without bulkCheck) or no block has ended yet."""
    settings = settingsOn(imports, today)
    if settings is None:
        return None
    index = blockOf(settings, today + dt.timedelta(days=1)) - 1  # the newest block ending by today
    if index < 0:
        return None
    return checkBlock(settings, weights, calorieChangeDates(imports, changes), index)


def nextCheckDate(imports: Sequence[TargetsImport], today: dt.date) -> dt.date | None:
    """The next check day after today. None when the check is off."""
    settings = settingsOn(imports, today)
    if settings is None:
        return None
    index = max(0, blockOf(settings, today + dt.timedelta(days=1)))
    return settings.firstBlockStart + dt.timedelta(days=blockDays * (index + 1) - 1)
