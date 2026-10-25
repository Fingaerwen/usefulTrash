"""The Week tab (apps/diet/docs/plan.md 4a): each day's kcal against its target, the week's averages, and your
body weight from Talos's weigh-ins. Weeks run Monday to Sunday, like Talos's (plan 8)."""

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ambrosia.rules.foods import LoggedFood, total
from ambrosia.rules.targets import DayTargets

oneDay = dt.timedelta(days=1)


@dataclass(frozen=True, slots=True)
class WeekDay:
    date: dt.date
    kind: str  # training or rest
    kcal: float  # eaten
    target: DayTargets | None
    logged: bool  # anything eaten logged that day
    upcoming: bool  # after today


@dataclass(frozen=True, slots=True)
class WeekView:
    monday: dt.date
    days: tuple[WeekDay, ...]
    averageKcal: float | None  # over the days logged so far
    averageTargetKcal: float | None  # their targets' average
    averageProteinG: float | None
    averageTargetProteinG: float | None
    weightKg: float | None  # this week's weigh-ins, averaged
    weighIns: int
    weightChangeKg: float | None  # against last week's average


def mondayOf(date: dt.date) -> dt.date:
    return date - dt.timedelta(days=date.weekday())


def weekView(monday: dt.date, today: dt.date, logs: Iterable[LoggedFood], kindOf: Callable[[dt.date], str],
             targetsFor: Callable[[dt.date, str], DayTargets | None], weights: Mapping[dt.date, float]) -> WeekView:
    """The week starting `monday`, as of `today`."""
    logs = list(logs)
    days = []
    for offset in range(7):
        date = monday + offset * oneDay
        kind = kindOf(date)
        eaten = [log for log in logs if log.date == date]
        days.append(WeekDay(date, kind, total(log.values for log in eaten).kcal, targetsFor(date, kind), bool(eaten),
                            date > today))
    counted = [day for day in days if day.logged and not day.upcoming]
    protein = [total(log.values for log in logs if log.date == day.date).proteinG for day in counted]
    withTargets = [day for day in counted if day.target is not None]
    this = _average(weights, monday)
    last = _average(weights, monday - 7 * oneDay)
    return WeekView(
        monday, tuple(days),
        _mean([day.kcal for day in counted]),
        _mean([day.target.kcal for day in withTargets]),
        _mean(protein),
        _mean([day.target.proteinG for day in withTargets]),
        this[0], this[1],
        round(this[0] - last[0], 2) if this[0] is not None and last[0] is not None else None,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _average(weights: Mapping[dt.date, float], monday: dt.date) -> tuple[float | None, int]:
    week = [kg for date, kg in weights.items() if monday <= date < monday + 7 * oneDay]
    return (round(sum(week) / len(week), 2) if week else None), len(week)


def weighIns(bodyWeightRows: Iterable[Mapping[str, Any]]) -> dict[dt.date, float]:
    """Talos's weigh-ins (bodyWeight rows that aren't deleted), by day."""
    return {row["date"]: row["weightKg"] for row in bodyWeightRows if not row.get("deleted")}
