"""The facts, worked out from every row (plan 3b, F10.1): your foods, what you ate, water, the targets files and
the changes applied to them, and from Talon its plans, the days you trained and your weigh-ins. Everything the
screens show is recalculated from these. Nothing derived is stored.

Rows are plain dicts with the columns of apps/diet/docs/plan.md 4e (and Talon's own for its tables).
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ambrosia.rules.foods import Food, LoggedFood, UsedFood, byMeal, dayTotal, foodFromRow, loggedFromRow, yourFoods
from ambrosia.rules.targets import (
    AppliedChange,
    DayTargets,
    TargetsImport,
    changesFromRows,
    dayKind,
    importInEffect,
    importsFromRows,
    planWeekFromRow,
    targetsOn,
    trainedDays,
)
from ambrosia.rules.today import DayView
from ambrosia.rules.week import WeekView, weekView, weighIns

ambrosiaTables = ("foods", "foodLogs", "water", "dietTargets", "targetChanges", "dietBackups")
talonTables = ("bodyWeight", "plans", "sessions", "exerciseLogs")  # read, never written (4e)


@dataclass(frozen=True, slots=True)
class TargetsView:
    """The Targets tab (4a): the file in effect, today's targets for both kinds of day, the bulk check's dates
    and the changes applied."""

    name: str | None  # the file's name. None before any import
    importedAt: dt.datetime | None
    trainingDay: DayTargets | None
    restDay: DayTargets | None
    waterMl: int | None
    firstBlockStart: dt.date | None  # None: the bulk check is off
    changes: tuple[AppliedChange, ...]


@dataclass(frozen=True, slots=True)
class HistoryDay:
    date: dt.date
    kcal: float
    targetKcal: int | None
    entries: int


class AmbrosiaState:
    def __init__(self):
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.foods: dict[str, Food] = {}
        self.logs: list[LoggedFood] = []
        self.water: dict[dt.date, int] = {}
        self.imports: list[TargetsImport] = []
        self.changes: list[AppliedChange] = []
        self.plans = []
        self.trained: set[dt.date] = set()
        self.weights: dict[dt.date, float] = {}

    def load(self, rowsByTable: Mapping[str, Iterable[dict[str, Any]]]) -> None:
        """Takes in every row of every table and works out the facts again."""
        self.rows = {name: {row["id"]: row for row in rows} for name, rows in rowsByTable.items()}
        self.foods = {row["id"]: foodFromRow(row) for row in self._live("foods")}
        self.logs = [loggedFromRow(row) for row in self._live("foodLogs")]
        self.water = {row["date"]: row["ml"] for row in self._live("water")}
        self.imports = importsFromRows(self._live("dietTargets"))
        self.changes = changesFromRows(self._live("targetChanges"))
        self.plans = [plan for plan in (planWeekFromRow(row) for row in self._live("plans")) if plan is not None]
        self.trained = trainedDays(self._live("exerciseLogs"))
        self.weights = weighIns(self._live("bodyWeight"))

    def _live(self, table: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.get(table, {}).values() if not row.get("deleted")]

    def row(self, table: str, rowId: str) -> dict[str, Any] | None:
        return self.rows.get(table, {}).get(rowId)

    # --- A day ---------------------------------------------------------------------------------

    def dayKind(self, date: dt.date) -> str:
        return dayKind(self.plans, self.trained, date)

    def targetsFor(self, date: dt.date, kind: str | None = None) -> DayTargets | None:
        return targetsOn(self.imports, self.changes, date, kind or self.dayKind(date))

    def waterTarget(self, date: dt.date) -> int | None:
        found = importInEffect(self.imports, date)
        return found.targets.waterMl if found else None

    def dayView(self, date: dt.date, editable: bool = True) -> DayView:
        kind = self.dayKind(date)
        targets = self.targetsFor(date, kind)
        later = targets is None and any(found.effectiveDate > date for found in self.imports)
        return DayView(date, kind, targets, dayTotal(self.logs, date), byMeal(self.logs, date),
                       self.water.get(date, 0), self.waterTarget(date), editable, later)

    def weekView(self, monday: dt.date, today: dt.date) -> WeekView:
        return weekView(monday, today, self.logs, self.dayKind, self.targetsFor, self.weights)

    # --- Your foods ----------------------------------------------------------------------------

    def yourFoods(self) -> list[UsedFood]:
        return yourFoods(self.foods.values(), self.logs)

    def foodWithBarcode(self, barcode: str) -> Food | None:
        return next((food for food in self.foods.values() if food.barcode == barcode), None)

    # --- Targets and History -------------------------------------------------------------------

    def targetsView(self, today: dt.date) -> TargetsView:
        found = importInEffect(self.imports, today)
        if found is None:
            return TargetsView(None, None, None, None, None, None, ())
        settings = found.targets.bulkCheck
        return TargetsView(found.targets.name, found.importedAt, self.targetsFor(today, "training"),
                           self.targetsFor(today, "rest"), found.targets.waterMl,
                           settings.firstBlockStart if settings else None,
                           tuple(sorted((change for change in self.changes if change.targetsImportId == found.importId),
                                        key=lambda change: change.fromDate)))

    def historyDays(self, month: dt.date, today: dt.date) -> list[HistoryDay]:
        """A month's days up to today, newest first, with what was eaten (AM5.5)."""
        first = month.replace(day=1)
        nextMonth = (first + dt.timedelta(days=32)).replace(day=1)
        days = []
        date = min(today, nextMonth - dt.timedelta(days=1))
        while date >= first:
            eaten = [log for log in self.logs if log.date == date]
            target = self.targetsFor(date)
            days.append(HistoryDay(date, sum(log.values.kcal for log in eaten), target.kcal if target else None,
                                   len(eaten)))
            date -= dt.timedelta(days=1)
        return days
