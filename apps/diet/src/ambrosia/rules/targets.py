"""Targets (apps/diet/docs/plan.md 4f, AM3.1, AM3.2): the file your Claude project writes, checked with every
problem in plain words (like Talon's plan import, G8a); the day's targets from the import that applies then
plus the bulk-check changes you applied to it; and whether a day is a training day or a rest day, from the
Talon plan in effect and whether you trained (AM3.2).

The bulk check itself (4g) is built at max effort (gate 2); this module only reads its settings.
"""

import datetime as dt
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

fileFormat = "ambrosiaTargets"
fileVersion = 1
macroKcal = {"carbs": 4, "fat": 9}  # kcal a gram, for the macro that takes a change (4f)
dayKinds = ("training", "rest")


@dataclass(frozen=True, slots=True)
class DayTargets:
    kcal: int
    proteinG: int
    fatG: int
    carbsG: int

    def changed(self, kcal: int, macro: str, grams: int) -> "DayTargets":
        """With a bulk-check change: kcal, and the grams on the macro that takes it."""
        moved = replace(self, kcal=self.kcal + kcal)
        if macro == "fat":
            return replace(moved, fatG=max(0, moved.fatG + grams))
        return replace(moved, carbsG=max(0, moved.carbsG + grams))


@dataclass(frozen=True, slots=True)
class BulkCheckSettings:
    """The bulk check's settings from the file (4f, 4g), so your Claude project owns the protocol."""

    firstBlockStart: dt.date  # a Monday
    rateMinKg: float  # a week: 0.15
    rateMaxKg: float  # 0.35
    stepKcal: int  # 150
    bigStepKcal: int  # 250
    bigGainKg: float  # 1.0
    minWeighIns: int  # 8
    changeMacro: str  # carbs or fat


@dataclass(frozen=True, slots=True)
class TargetsFile:
    name: str
    trainingDay: DayTargets
    restDay: DayTargets
    waterMl: int | None
    bulkCheck: BulkCheckSettings | None  # None: the check is off (a cut, say)

    def forKind(self, kind: str) -> DayTargets:
        return self.trainingDay if kind == "training" else self.restDay


@dataclass(frozen=True, slots=True)
class FileCheck:
    """A file as checked: the targets if it's usable, every problem in plain words, and warnings that don't
    stop the import (macros that don't add up to the kcal)."""

    targets: TargetsFile | None
    problems: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def readTargetsFile(text: str | bytes) -> FileCheck:
    """Checks a targets file; see targetsFromJson."""
    try:
        data = json.loads(text)
    except (UnicodeDecodeError, ValueError):
        return FileCheck(None, ("This isn't a targets file: it can't be read as JSON.",))
    return targetsFromJson(data)


def targetsFromJson(data: Any) -> FileCheck:
    """A targets file (4f) as written by your Claude project, checked. Every problem is listed at once."""
    problems: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return FileCheck(None, ("A targets file is a JSON object: { … }.",))
    if data.get("format") != fileFormat:
        problems.append(f'"format" must be "{fileFormat}": is this a targets file?')
    if data.get("version") != fileVersion:
        problems.append(f'"version" must be {fileVersion}.')
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        problems.append('"name" must be a short text, like "Bulk from 26 Oct".')
        name = ""
    days = {kind: _dayTargets(data.get(f"{kind}Day"), f"{kind}Day", problems, warnings) for kind in dayKinds}
    water = data.get("waterMl")
    if water is not None and not _whole(water, 0, 10_000):
        problems.append('"waterMl" must be a whole number of ml from 0 to 10,000, or left out.')
        water = None
    settings = _bulkCheck(data.get("bulkCheck"), problems) if "bulkCheck" in data else None
    known = {"format", "version", "name", "trainingDay", "restDay", "waterMl", "bulkCheck"}
    problems += [f'"{key}" isn\'t a targets field: check the spelling.' for key in data if key not in known]
    if problems or None in days.values():
        return FileCheck(None, tuple(problems), tuple(warnings))
    return FileCheck(TargetsFile(name.strip(), days["training"], days["rest"], water, settings), (), tuple(warnings))


def _whole(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _number(value: Any, low: float, high: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def _dayTargets(data: Any, where: str, problems: list[str], warnings: list[str]) -> DayTargets | None:
    if not isinstance(data, dict):
        problems.append(f'"{where}" is missing: kcal, proteinG, fatG and carbsG for that kind of day.')
        return None
    limits = {"kcal": (800, 8000), "proteinG": (0, 500), "fatG": (0, 400), "carbsG": (0, 1500)}
    bad = False
    for key, (low, high) in limits.items():
        if not _whole(data.get(key), low, high):
            problems.append(f'"{where}.{key}" must be a whole number from {low:,} to {high:,}.')
            bad = True
    problems += [f'"{where}.{key}" isn\'t a field there: check the spelling.' for key in data if key not in limits]
    if bad:
        return None
    targets = DayTargets(data["kcal"], data["proteinG"], data["fatG"], data["carbsG"])
    fromMacros = 4 * targets.proteinG + 9 * targets.fatG + 4 * targets.carbsG
    if abs(fromMacros - targets.kcal) > 0.1 * targets.kcal:
        warnings.append(f"{where}: protein, fat and carbs add up to {fromMacros:,} kcal, more than 10% from "
                        f"its {targets.kcal:,} kcal.")
    return targets


def _bulkCheck(data: Any, problems: list[str]) -> BulkCheckSettings | None:
    if not isinstance(data, dict):
        problems.append('"bulkCheck" must be an object with the check\'s settings, or left out to switch it off.')
        return None
    count = len(problems)
    try:
        start = dt.date.fromisoformat(data.get("firstBlockStart", ""))
    except (TypeError, ValueError):
        start = None
    if start is None or start.weekday() != 0:
        problems.append('"bulkCheck.firstBlockStart" must be a Monday, written like "2026-10-26".')
    rate = data.get("rateKgPerWeek")
    if (not isinstance(rate, dict) or not _number(rate.get("min"), -2, 2) or not _number(rate.get("max"), -2, 2)
            or rate["min"] >= rate["max"]):
        problems.append('"bulkCheck.rateKgPerWeek" must be like {"min": 0.15, "max": 0.35}, min below max.')
    if not _whole(data.get("stepKcal"), 25, 1000):
        problems.append('"bulkCheck.stepKcal" must be a whole number of kcal from 25 to 1,000.')
    if not _whole(data.get("bigStepKcal"), 25, 1000):
        problems.append('"bulkCheck.bigStepKcal" must be a whole number of kcal from 25 to 1,000.')
    if not _number(data.get("bigGainKg"), 0.1, 5):
        problems.append('"bulkCheck.bigGainKg" must be a number of kg from 0.1 to 5.')
    if not _whole(data.get("minWeighIns"), 1, 14):
        problems.append('"bulkCheck.minWeighIns" must be a whole number from 1 to 14.')
    if data.get("changeMacro") not in macroKcal:
        problems.append('"bulkCheck.changeMacro" must be "carbs" or "fat": the macro that takes a change.')
    known = {"firstBlockStart", "rateKgPerWeek", "stepKcal", "bigStepKcal", "bigGainKg", "minWeighIns", "changeMacro"}
    problems += [f'"bulkCheck.{key}" isn\'t a setting: check the spelling.' for key in data if key not in known]
    if len(problems) > count:
        return None
    return BulkCheckSettings(start, float(rate["min"]), float(rate["max"]), data["stepKcal"], data["bigStepKcal"],
                             float(data["bigGainKg"]), data["minWeighIns"], data["changeMacro"])


def macroGrams(kcal: int, macro: str) -> int:
    """The grams of the macro that take a kcal change, a half rounding away from zero (150 kcal = 38 g of carbs)."""
    grams = abs(kcal) / macroKcal[macro]
    whole = int(grams + 0.5)
    return whole if kcal >= 0 else -whole


# --- The targets on a day ------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TargetsImport:
    """A dietTargets row that isn't deleted, with its file read."""

    importId: str
    importedAt: dt.datetime
    effectiveDate: dt.date
    targets: TargetsFile


@dataclass(frozen=True, slots=True)
class AppliedChange:
    """A targetChanges row that isn't deleted (4e): a bulk-check change, counting from fromDate."""

    targetsImportId: str
    fromDate: dt.date
    kcalChange: int
    macro: str
    macroChangeG: int


def importsFromRows(rows: Iterable[Mapping[str, Any]]) -> list[TargetsImport]:
    """The imports that can still be read (a file the app can't read any more is left out)."""
    found = []
    for row in rows:
        if row.get("deleted"):
            continue
        checked = targetsFromJson(row["targetsJson"])
        if checked.targets is not None:
            found.append(TargetsImport(row["id"], row["importedAt"], row["effectiveDate"], checked.targets))
    return found


def changesFromRows(rows: Iterable[Mapping[str, Any]]) -> list[AppliedChange]:
    return [AppliedChange(row["targetsImportId"], row["fromDate"], row["kcalChange"], row["macro"], row["macroChangeG"])
            for row in rows if not row.get("deleted")]


def importInEffect(imports: Sequence[TargetsImport], date: dt.date) -> TargetsImport | None:
    """The import that applies on a date: the latest to take effect by then (the later import on a tie)."""
    started = [found for found in imports if found.effectiveDate <= date]
    return max(started, key=lambda found: (found.effectiveDate, found.importedAt, found.importId), default=None)


def targetsOn(imports: Sequence[TargetsImport], changes: Sequence[AppliedChange], date: dt.date,
              kind: str) -> DayTargets | None:
    """A day's targets (4f): the import in effect, plus that import's changes counting by then."""
    found = importInEffect(imports, date)
    if found is None:
        return None
    targets = found.targets.forKind(kind)
    for change in sorted(changes, key=lambda change: change.fromDate):
        if change.targetsImportId == found.importId and change.fromDate <= date:
            targets = targets.changed(change.kcalChange, change.macro, change.macroChangeG)
    return targets


# --- Training day or rest day (AM3.2) ------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PlanWeek:
    """What Ambrosia reads from a Talon plan import: each weekday's kind, workout, rest or flex."""

    planImportId: str
    effectiveDate: dt.date
    importedAt: dt.datetime
    days: tuple[str, ...]  # 7 of "workout", "rest", "flex"; Monday first


def planWeekFromRow(row: Mapping[str, Any]) -> PlanWeek | None:
    """A Talon plans row as a week, or None if it can't be read (Talon's own format, plans/planFormat.md)."""
    week = row.get("planJson", {}).get("week") if isinstance(row.get("planJson"), dict) else None
    if not isinstance(week, list) or len(week) != 7 or not all(isinstance(day, dict) for day in week):
        return None
    days = tuple("rest" if day.get("restDay") else "flex" if day.get("makeUp") else "workout" for day in week)
    return PlanWeek(row["id"], row["effectiveDate"], row["importedAt"], days)


def dayKind(plans: Sequence[PlanWeek], trainedDays: set[dt.date], date: dt.date) -> str:
    """AM3.2: a weekday with a fixed session in the Talon plan in effect is a training day, the flex day once
    you've trained on it, a rest day a rest day. Without a plan Ambrosia can read, every day is a training
    day (a bulk needs the food more than the rest)."""
    started = [plan for plan in plans if plan.effectiveDate <= date]
    plan = max(started, key=lambda plan: (plan.effectiveDate, plan.importedAt, plan.planImportId), default=None)
    if plan is None:
        return "training"
    kind = plan.days[date.weekday()]
    if kind == "flex":
        return "training" if date in trainedDays else "rest"
    return "training" if kind == "workout" else "rest"


def trainedDays(exerciseLogRows: Iterable[Mapping[str, Any]]) -> set[dt.date]:
    """The days you trained (4g, AM3.2): at least one exercise done in Talon that day, sets or minutes, not
    skipped (Talon's own "done")."""
    return {row["date"] for row in exerciseLogRows
            if not row.get("deleted") and not row.get("skipped") and (row.get("sets") or row.get("minutes") is not None)}
