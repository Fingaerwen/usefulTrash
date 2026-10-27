"""All your facts in memory, and what the screens show, worked out from them (plan 3b, F10.1).

On start the app loads every row (phone: its own database; PC view: the cloud), and loads them again
after each saved change or sync. Nothing worked out here is ever stored: the phone and the PC view
work out the same answers from the same facts.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone, StepEdit, WeightEdit
from gym.rules.planFile import Plan, PlanExercise, checkPlan, scheduleDays
from gym.rules.planImport import knownExercises
from gym.rules.progression import Training, training
from gym.rules.schedule import LoggedWorkout, PlanStart, planInEffect
from gym.rules.sessions import withCounts
from gym.rules.stats import (
    ChartView,
    ExerciseDetail,
    HistoryDay,
    MonthDiary,
    ProgressLine,
    WeekSummary,
    WeightView,
    chartView,
    dayBanners,
    exerciseDetail,
    historyDays,
    historyFiles,
    monthDiary,
    monthlyPoints,
    progressLines,
    weekSummary,
    weightView,
)
from gym.rules.today import TodayView, todayView
from gym.rules.week import weekStart, weeklyTarget


@dataclass(frozen=True, slots=True)
class PlanEntry:
    """One line of the PC view's Plans tab (SC6.1): what it says, and for an earlier plan its row and name, so it
    can be switched back to (SW1.1) or archived (SW1.2)."""

    text: str
    kind: str  # "active", "later" (taking effect later), "earlier", "archived" or "none"
    rowId: str | None = None
    name: str = ""  # "Full Body (v1)"


class GymState:
    """The facts, loaded from rows, and the views worked out from them."""

    def __init__(self):
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}  # table -> id -> row, deleted ones included
        self.plans: list[ImportedPlan] = []
        self.unreadablePlans: list[str] = []  # plan imports whose plan can't be read (Problems page)
        self.workouts: list[LoggedWorkout] = []
        self.logs: dict[dt.date, dict[str, LoggedExercise]] = {}
        self.steps: dict[dt.date, int] = {}
        self.weights: dict[dt.date, float] = {}
        self.known: dict[str, PlanExercise] = {}  # every exercise of every plan so far (R8)
        self.weightEdits: list[WeightEdit] = []  # weights set in the app (WD2.1), oldest first
        self.stepEdits: list[StepEdit] = []  # weight steps set in the app, oldest first
        self.manualDeloads: dict[str, dt.date] = {}  # deloads started by hand: row id -> start (WD2.4)
        self._planCache: dict[tuple[str, dt.datetime], Plan | None] = {}
        self._training: dict[dt.date, Training] = {}  # worked out once per day and load

    def load(self, rowsByTable: Mapping[str, Iterable[dict[str, Any]]]) -> None:
        """Takes in every row of every table and works out the facts again."""
        self.rows = {name: {row["id"]: row for row in rows} for name, rows in rowsByTable.items()}

        self.plans, self.unreadablePlans = [], []
        for row in self._live("plans"):
            plan = self._readPlan(row)
            if plan is None:
                self.unreadablePlans.append(row["id"])
                continue
            start = PlanStart(row["id"], row["effectiveDate"], row["importedAt"], scheduleDays(plan), plan.weeklyTarget)
            self.plans.append(ImportedPlan(start, plan))
        self.known = knownExercises((imported.start.importedAt, imported.plan) for imported in self.plans)

        workouts = [LoggedWorkout(row["date"], row["planImportId"], row["stepIndex"], row["finishedAt"] is not None)
                    for row in self._live("sessions")]
        self.logs = {}
        for row in self._live("exerciseLogs"):
            self.logs.setdefault(row["date"], {})[row["exerciseId"]] = LoggedExercise(
                row["exerciseId"], _readSets(row["sets"]), row["minutes"], row["skipped"],
                bool(row.get("declinedSuggestion")))
        self.workouts = withCounts(self.plans, workouts, self.logs)  # which ones count (WD4.1)
        self.steps = {row["date"]: row["steps"] for row in self._live("dailySteps")}
        self.weights = {row["date"]: row["weightKg"] for row in self._live("bodyWeight")}
        self.weightEdits = [WeightEdit(row["exerciseId"], row["weekday"], row["weightKg"], row["fromDate"])
                            for row in _inOrder(self._live("exerciseWeights"))]
        self.stepEdits = [StepEdit(row["exerciseId"], row["incrementKg"], row["fromDate"])
                          for row in _inOrder(self._live("exerciseSteps"))]
        self.manualDeloads = {row["id"]: row["startDate"] for row in self._live("deloads")}
        self._training = {}

    def training(self, date: dt.date) -> Training:
        """Progression and deloads as of a day (progression.py)."""
        if date not in self._training:
            self._training[date] = training(self.plans, self.workouts, self.logs, self.weightEdits, self.stepEdits,
                                            list(self.manualDeloads.values()), date)
        return self._training[date]

    def today(self, date: dt.date) -> TodayView:
        return todayView(self.plans, self.workouts, self.logs.get(date, {}), self.known, self.steps.get(date), date,
                         self.training(date))

    def currentPlan(self, date: dt.date) -> ImportedPlan | None:
        """The plan in effect on a day."""
        start = planInEffect([imported.start for imported in self.plans], date)
        return next((imported for imported in self.plans if start is not None and imported.start is start), None)

    def progress(self, date: dt.date) -> tuple[tuple[ProgressLine, ...], tuple[ProgressLine, ...]]:
        """The Progress tab's list (SC3.1): the plan's exercises, then past ones."""
        return progressLines(self.currentPlan(date), self.known, self.logs, self.training(date), date)

    def exerciseDetail(self, exerciseId: str, date: dt.date, chartRange: str) -> ExerciseDetail | None:
        """One exercise's page in Progress (SC3.1)."""
        exercise = self.known.get(exerciseId)
        if exercise is None:
            return None
        return exerciseDetail(exercise, self.currentPlan(date), self.logs, self.training(date), date, chartRange)

    def chart(self, exerciseId: str, date: dt.date, chartRange: str) -> ChartView | None:
        """One exercise on the Charts tab (SC8.1)."""
        exercise = self.known.get(exerciseId)
        return chartView(exercise, self.logs, self.training(date), date, chartRange) if exercise else None

    def weightView(self, date: dt.date, chartRange: str) -> WeightView:
        """The Weight tab (SC5.1)."""
        return weightView(self.weights, date, chartRange)

    def historyDays(self, dates: list[dt.date], today: dt.date) -> tuple[HistoryDay, ...]:
        """History's days (SC6.1, HI1.1)."""
        return historyDays(self.plans, self.workouts, self.logs, self.steps, self.weights, dates, today)

    def diary(self, month: dt.date, today: dt.date) -> MonthDiary:
        """A month of the progression diary (DI1.1)."""
        return monthDiary(self.currentPlan(today), self.known, self.logs, self.weights, month)

    def historyFiles(self, date: dt.date) -> dict[str, str]:
        """The readable history (EX1.1, BK1.2): sets, weigh-ins, steps and the diary as CSV files."""
        return historyFiles(self.currentPlan(date), self.known, self.logs, self.weights, self.steps, date)

    def monthlyPoints(self, exerciseId: str) -> tuple[tuple[dt.date, float], ...]:
        """The diary's month-by-month chart for an exercise, or the body weight for "" (DI1.1)."""
        return monthlyPoints(self.known.get(exerciseId) if exerciseId else None, self.logs, self.weights)

    def banners(self, date: dt.date, summarySeenFor: dt.date | None) -> tuple[str, ...]:
        """The banners of the day (18.4a): last week's summary on Mondays, the weigh-in on Fridays."""
        lastMonday = weekStart(date) - dt.timedelta(days=7)
        hadPlan = weeklyTarget([imported.start for imported in self.plans], lastMonday) is not None
        return dayBanners(date, self.weights, hadPlan, summarySeenFor)

    def week(self, monday: dt.date, date: dt.date) -> WeekSummary:
        """The Week tab (SC4.1) for the week starting on `monday`."""
        return weekSummary(self.plans, self.workouts, self.logs, self.known, self.steps, self.weights, monday, date)

    def manualDeloadAt(self, date: dt.date) -> str | None:
        """The row of a deload started by hand that's running or still to come on a day, if there is one."""
        for rowId, start in self.manualDeloads.items():
            if start + dt.timedelta(days=6) >= date:
                return rowId
        return None

    def planEntries(self, today: dt.date) -> tuple[PlanEntry, ...]:
        """The PC view's Plans tab (SC6.1): the active plan, any taking effect later, earlier ones oldest first,
        then the archived ones (SW1.2), which still count everywhere else."""
        ordered = sorted(self.plans, key=lambda imported: (imported.start.effectiveDate, imported.start.importedAt))
        tookEffect = list({imported.start.effectiveDate: imported for imported in ordered
                           if imported.start.effectiveDate <= today}.values())  # the later import wins a day
        active, later, earlier, archived = [], [], [], []
        for index, imported in enumerate(tookEffect):
            plan, since, rowId = imported.plan, imported.start.effectiveDate, imported.start.planImportId
            name = f"{plan.name} (v{plan.version})"
            if index == len(tookEffect) - 1:
                text = f"Active: {name} · since {_shortDate(since)} · {plan.weeklyTarget}/week"
                active.append(PlanEntry(text, "active", rowId, name))
                continue
            until = tookEffect[index + 1].start.effectiveDate - dt.timedelta(days=1)
            stretch = f"{_shortDate(since)} – {_shortDate(until)}"
            if (self.row("plans", rowId) or {}).get("archived"):
                archived.append(PlanEntry(f"{name} · {stretch}", "archived", rowId, name))
            else:
                earlier.append(PlanEntry(f"Earlier: {name} · {stretch}", "earlier", rowId, name))
        for imported in ordered:
            if imported.start.effectiveDate > today:
                name = f"{imported.plan.name} (v{imported.plan.version})"
                text = f"From {_shortDate(imported.start.effectiveDate)}: {name}"
                later.append(PlanEntry(text, "later", imported.start.planImportId, name))
        return tuple(active + later + earlier + archived) or (PlanEntry("No plan yet.", "none"),)

    def row(self, tableName: str, rowId: str) -> dict[str, Any] | None:
        """A stored row, deleted or not (edits start from it)."""
        return self.rows.get(tableName, {}).get(rowId)

    def _live(self, tableName: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.get(tableName, {}).values() if not row["deleted"]]

    def _readPlan(self, row: dict[str, Any]) -> Plan | None:
        """A stored plan, read leniently (fields from newer app versions are ignored). Cached per version."""
        key = (row["id"], row["updatedAt"])
        if key not in self._planCache:
            self._planCache[key] = checkPlan(row["planJson"], strict=False).plan
        return self._planCache[key]


def _inOrder(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Changes set in the app, oldest first: by the day they apply from, then when they were made (the id
    only makes exact ties come out the same everywhere)."""
    return sorted(rows, key=lambda row: (row["fromDate"], row["updatedAt"], row["id"]))


def _shortDate(date: dt.date) -> str:
    """6 Oct."""
    return f"{date.day} {date:%b}"


def _readSets(sets: Any) -> tuple[SetDone, ...]:
    """The sets of a log row ([{"reps": 9, "weightKg": 82.5}, ...]); anything malformed is left out."""
    done = []
    for entry in sets if isinstance(sets, list) else ():
        reps = entry.get("reps") if isinstance(entry, dict) else None
        weightKg = entry.get("weightKg") if isinstance(entry, dict) else None
        if isinstance(reps, int) and not isinstance(reps, bool):
            weightOk = isinstance(weightKg, (int, float)) and not isinstance(weightKg, bool)
            done.append(SetDone(reps, float(weightKg) if weightOk else None))
    return tuple(done)
