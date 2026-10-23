"""All your facts in memory, and what the screens show, worked out from them (plan 3b, F10.1).

On start the app loads every row (phone: its own database; PC view: the cloud), and loads them again
after each saved change or sync. Nothing worked out here is ever stored: the phone and the PC view
work out the same answers from the same facts.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any

from gym.rules.planFile import Plan, PlanExercise, checkPlan, scheduleDays
from gym.rules.planImport import knownExercises
from gym.rules.schedule import LoggedWorkout, PlanStart
from gym.rules.today import ImportedPlan, LoggedExercise, SetDone, TodayView, todayView


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
        self._planCache: dict[tuple[str, dt.datetime], Plan | None] = {}

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

        self.workouts = [LoggedWorkout(row["date"], row["planImportId"], row["stepIndex"], row["finishedAt"] is not None)
                         for row in self._live("sessions")]
        self.logs = {}
        for row in self._live("exerciseLogs"):
            self.logs.setdefault(row["date"], {})[row["exerciseId"]] = LoggedExercise(
                row["exerciseId"], _readSets(row["sets"]), row["minutes"], row["skipped"])
        self.steps = {row["date"]: row["steps"] for row in self._live("dailySteps")}
        self.weights = {row["date"]: row["weightKg"] for row in self._live("bodyWeight")}

    def today(self, date: dt.date) -> TodayView:
        return todayView(self.plans, self.workouts, self.logs.get(date, {}), self.known, self.steps.get(date), date)

    def planLines(self, today: dt.date) -> tuple[str, ...]:
        """The PC view's Plans tab (SC6.1): the active plan, any taking effect later, and earlier ones."""
        ordered = sorted(self.plans, key=lambda imported: (imported.start.effectiveDate, imported.start.importedAt))
        tookEffect = list({imported.start.effectiveDate: imported for imported in ordered
                           if imported.start.effectiveDate <= today}.values())  # the later import wins a day
        lines = []
        for index, imported in enumerate(tookEffect):
            plan, since = imported.plan, imported.start.effectiveDate
            name = f"{plan.name} (v{plan.version})"
            if index == len(tookEffect) - 1:
                lines.insert(0, f"Active: {name} · since {_shortDate(since)} · {plan.weeklyTarget}/week")
            else:
                until = tookEffect[index + 1].start.effectiveDate - dt.timedelta(days=1)
                lines.append(f"Earlier: {name} · {_shortDate(since)} – {_shortDate(until)}")
        for imported in ordered:
            if imported.start.effectiveDate > today:
                lines.insert(1 if tookEffect else 0,
                             f"From {_shortDate(imported.start.effectiveDate)}: {imported.plan.name} "
                             f"(v{imported.plan.version})")
        return tuple(lines) or ("No plan yet.",)

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
