"""Talon's rows read as the rules' facts (plan 14, F10.1): plan imports, workouts and the exercises logged in them.
Talon's state reads them through here, and so does Ambrosia, which only reads Talon's rows and never writes them
(apps/diet/docs/plan.md 4e). One reader means the two apps can't disagree about which workouts count.

Pure logic: rows in, facts out. A deleted row is left out.
"""

import datetime as dt
from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any

from usefulShared.training.facts import ImportedPlan, LoggedExercise, SetDone
from usefulShared.training.planFile import Plan, checkPlan, scheduleDays
from usefulShared.training.schedule import LoggedWorkout, PlanStart, isFinished
from usefulShared.training.sessions import withCounts

PlanCache = MutableMapping[tuple[str, Any], Plan | None]


def readPlan(row: Mapping[str, Any], cache: PlanCache | None = None) -> Plan | None:
    """A stored plan, read leniently (fields from newer app versions are ignored). None if it can't be read. With a
    cache, each version of a row is read once."""
    key = (row["id"], row["updatedAt"])
    if cache is not None and key in cache:
        return cache[key]
    plan = checkPlan(row["planJson"], strict=False).plan
    if cache is not None:
        cache[key] = plan
    return plan


def importedPlans(rows: Iterable[Mapping[str, Any]],
                  cache: PlanCache | None = None) -> tuple[list[ImportedPlan], list[str]]:
    """The plan imports that can be read, and the IDs of those that can't."""
    plans, unreadable = [], []
    for row in _live(rows):
        plan = readPlan(row, cache)
        if plan is None:
            unreadable.append(row["id"])
            continue
        start = PlanStart(row["id"], row["effectiveDate"], row["importedAt"], scheduleDays(plan), plan.weeklyTarget)
        plans.append(ImportedPlan(start, plan))
    return plans, unreadable


def loggedExercises(rows: Iterable[Mapping[str, Any]]) -> dict[dt.date, dict[str, LoggedExercise]]:
    """Each day's logged exercises, by exercise ID."""
    logs: dict[dt.date, dict[str, LoggedExercise]] = {}
    for row in _live(rows):
        logs.setdefault(row["date"], {})[row["exerciseId"]] = LoggedExercise(
            row["exerciseId"], readSets(row["sets"]), row["minutes"], row["skipped"],
            bool(row.get("declinedSuggestion")))
    return logs


def loggedWorkouts(sessionRows: Iterable[Mapping[str, Any]], plans: list[ImportedPlan],
                   logs: Mapping[dt.date, Mapping[str, LoggedExercise]]) -> list[LoggedWorkout]:
    """The workouts, each with whether it counts (WD4.1)."""
    workouts = [LoggedWorkout(row["date"], row["planImportId"], row["stepIndex"], row["finishedAt"] is not None)
                for row in _live(sessionRows)]
    return withCounts(plans, workouts, logs)


def finishedWorkoutDays(rowsByTable: Mapping[str, Iterable[Mapping[str, Any]]], today: dt.date) -> set[dt.date]:
    """The days with a finished workout that counts (AM12.4): at most 30% of it skipped or not done (WD4.1), and
    Finish tapped or the day over, since Talon finishes a past day's workout by itself (R5a). A day ahead counts
    once it's finished too, as Talon lets you log one (DY1.1)."""
    plans, _ = importedPlans(rowsByTable.get("plans", ()))
    logs = loggedExercises(rowsByTable.get("exerciseLogs", ()))
    workouts = loggedWorkouts(rowsByTable.get("sessions", ()), plans, logs)
    return {workout.date for workout in workouts if workout.counts and isFinished(workout, today)}


def readSets(sets: Any) -> tuple[SetDone, ...]:
    """The sets of a log row ([{"reps": 9, "weightKg": 82.5}, ...], a drop set's with "dropReps" and "dropKg" too,
    DS1.1). Anything malformed is left out."""
    done = []
    for entry in sets if isinstance(sets, list) else ():
        if not isinstance(entry, dict) or not _isWhole(entry.get("reps")):
            continue
        weightKg, dropReps, dropKg = entry.get("weightKg"), entry.get("dropReps"), entry.get("dropKg")
        drop = (dropReps, float(dropKg)) if _isWhole(dropReps) and _isNumber(dropKg) else (None, None)
        done.append(SetDone(entry["reps"], float(weightKg) if _isNumber(weightKg) else None, *drop))
    return tuple(done)


def _live(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in rows if not row["deleted"]]


def _isWhole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _isNumber(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
