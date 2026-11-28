"""Steps and calories from Health Connect (plan HC1.1 to HC1.4): what Talon read, which days that changes, and how
far back it reads.

OHealth writes your steps, active calories and total calories (active and resting) to Android's Health Connect, and
Talon reads each day's totals from there whenever it opens or comes back on screen (HC1.2). OHealth often hands its
data over late, only once it's opened itself, so every read covers the last 7 days again and a day's numbers are
replaced when they've changed. The first read covers 30 days, as far back as Health Connect lets an app read
without its extra history permission. Health Connect's numbers replace steps you typed (HC1.3).

Pure logic: no screen, database, network or clock. Readings come in as the extension hands them over.
"""

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

firstReadDays = 30  # the first read: as far back as Health Connect allows without READ_HEALTH_DATA_HISTORY
rereadDays = 7  # every read after that: OHealth's late syncs land within a week
maxSteps = 200_000  # the cloud's limits (cloud/001, cloud/004)
maxActiveKcal = 20_000
maxTotalKcal = 30_000


@dataclass(frozen=True, slots=True)
class HealthDay:
    """One day as Health Connect has it: steps (0 when it has calories but no steps) and whole kcal, None for a
    kind of calories it has nothing for."""

    date: dt.date
    steps: int
    activeKcal: int | None
    totalKcal: int | None


@dataclass(frozen=True, slots=True)
class StoredDay:
    """A day's row as Talon has it: its steps and calories, and whether they came from Health Connect."""

    steps: int
    activeKcal: int | None
    totalKcal: int | None
    fromHealth: bool


def readWindow(healthDays: Iterable[dt.date], today: dt.date) -> tuple[dt.date, dt.date]:
    """The days to read, first and last, today included: 30 days until any day came from Health Connect, then 7."""
    days = rereadDays if any(True for _ in healthDays) else firstReadDays
    return today - dt.timedelta(days=days - 1), today


def readHealthDays(raw: Any, today: dt.date) -> tuple[list[HealthDay], list[str]]:
    """The extension's answer as days, and why any were left out. A day with nothing at all, a day after today and
    a day with a number no phone could count are left out. Calories are rounded to whole kcal."""
    days: list[HealthDay] = []
    skipped: list[str] = []
    for entry in raw if isinstance(raw, list) else ():
        if not isinstance(entry, dict):
            skipped.append("an entry that isn't a day")
            continue
        try:
            date = dt.date.fromisoformat(str(entry.get("date")))
        except ValueError:
            skipped.append(f"a day with the date {entry.get('date')!r}")
            continue
        steps, active, total = (_whole(entry.get(name)) for name in ("steps", "activeKcal", "totalKcal"))
        if date > today or (steps is None and active is None and total is None):
            continue
        if any(value is not None and value < 0 for value in (steps, active, total)) or (steps or 0) > maxSteps \
                or (active or 0) > maxActiveKcal or (total or 0) > maxTotalKcal:
            skipped.append(f"{date}: numbers out of range")
            continue
        days.append(HealthDay(date, steps or 0, active, total))
    return days, skipped


def changedDays(days: Iterable[HealthDay], stored: Mapping[dt.date, StoredDay]) -> list[HealthDay]:
    """The days whose row needs writing: new ones, ones whose numbers changed, and typed ones (HC1.3)."""
    changed = []
    for day in days:
        known = stored.get(day.date)
        if known is not None and known.fromHealth and (known.steps, known.activeKcal, known.totalKcal) == (
                day.steps, day.activeKcal, day.totalKcal):
            continue
        changed.append(day)
    return changed


def kcalText(activeKcal: int | None, totalKcal: int | None) -> str:
    """ "Active 412 kcal · Total 2,310 kcal", the parts that are known."""
    parts = []
    if activeKcal is not None:
        parts.append(f"Active {activeKcal:,} kcal")
    if totalKcal is not None:
        parts.append(f"Total {totalKcal:,} kcal")
    return " · ".join(parts)


def _whole(value: Any) -> int | None:
    """A count or kcal from Health Connect as a whole number, half up. None when it isn't a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return int(math.floor(value + 0.5))
