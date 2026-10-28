"""What your taps do (plan 6, CS1.1's one write path): each action builds the rows it changes and
hands them to the store in one go, so a workout day and its exercises are saved together. Screens
never write rows themselves, and the store stamps every edit's time.

A day's workout, an exercise on a day and a day's steps have IDs worked out from your user ID and the
date (DT1.1), so the phone and the PC view always change the same rows. Taking something back marks
its row deleted, which syncs like any edit. A weight or weight step set in the app is a new row each
time, dated from when it applies, so it never rewrites earlier progression.
"""

import datetime as dt
import math
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from gym.rules.today import ExerciseLine, SetDone, TodayView
from gym.state import GymState
from gym.tables import exerciseLogs, sessions
from usefulShared.tables import bodyWeight, dailySteps, dayRowId, newRowId


class RowStore(Protocol):
    """Where actions save: the phone's database (then sync) or, in the PC view, the cloud."""

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]: ...


class ActionRefused(ValueError):
    """An entry that can't be saved. The message says why in plain words, for the screen."""


class GymActions:
    """Today's actions for one signed-in user."""

    def __init__(self, store: RowStore, state: GymState, userId: str, clock: Callable[[], dt.datetime]):
        self.store = store
        self.state = state
        self.userId = userId
        self.clock = clock

    # --- Exercises (19.1) --------------------------------------------------------------------

    async def checkExercise(self, view: TodayView, line: ExerciseLine) -> None:
        """[✓]: logs the exercise as targeted. Tapping a logged exercise again takes it back."""
        if line.status == "done":
            await self._takeBack(view, line)
        elif line.exercise.isCardio and line.targetMinutes is not None:
            await self._log(view, line, (), line.targetMinutes, skipped=False)
        elif line.needsWeight:  # Today opens ▾ sets instead (PF3)
            raise ActionRefused("Enter the weight you lifted under Sets: your plan's weight is only a placeholder.")
        elif line.targetReps is not None and line.targetSets:
            await self._log(view, line, (SetDone(line.targetReps, line.targetWeightKg),) * line.targetSets, None,
                            skipped=False)
        else:
            raise ActionRefused("This exercise has no target here: enter what you did under Sets.")

    async def saveSets(self, view: TodayView, line: ExerciseLine, sets: Sequence[SetDone],
                       minutes: int | None = None) -> None:
        """▾ sets: what was actually done, set by set (19.1a-1), or the minutes for cardio. Nothing at
        all takes the exercise back."""
        if line.exercise.isCardio:
            if minutes is None:
                await self._takeBack(view, line)
                return
            _checkWhole(minutes, 0, 1440, "Minutes")
            await self._log(view, line, (), minutes, skipped=False)
            return
        if not sets:
            await self._takeBack(view, line)
            return
        for done in sets:
            _checkWhole(done.reps, 0, 1000, "Reps")
            if line.exercise.equipment == "bodyweight":
                if done.weightKg is not None:
                    raise ActionRefused("A bodyweight exercise has no weight.")
            elif done.weightKg is None or not _isKilograms(done.weightKg):
                raise ActionRefused("Weight must be a number from 0 to 1000 kg, with at most 2 decimals.")
        await self._log(view, line, tuple(sets), None, skipped=False)

    async def skipExercise(self, view: TodayView, line: ExerciseLine) -> None:
        """skip: today only (19.1). Tapping skip on a skipped exercise takes the skip back."""
        if line.status == "skipped":
            await self._takeBack(view, line)
        else:
            await self._log(view, line, (), None, skipped=True)

    async def declineSuggestion(self, view: TodayView, line: ExerciseLine, declined: bool) -> None:
        """Undo on ↑new (UN1.1): not today, so today's target is the last weight at the top of the range. Redo
        takes that back. Stored on the exercise's entry for the day, which logging keeps. On its own it isn't
        an entry, so it never makes a workout."""
        logId = dayRowId(exerciseLogs, self.userId, date=view.date, exerciseId=line.exercise.exerciseId)
        existing = self.state.row("exerciseLogs", logId)
        live = existing is not None and not existing["deleted"]
        if not declined and live and not existing["sets"] and existing["minutes"] is None and not existing["skipped"]:
            await self.store.saveRows([("exerciseLogs", dict(existing, deleted=True))])  # nothing else in it
            return
        if not declined and not live:
            return
        row = dict(existing) if live else {
            "id": logId, "userId": self.userId, "date": view.date, "exerciseId": line.exercise.exerciseId,
            "targetReps": None, "targetWeightKg": None, "sets": [], "minutes": None, "skipped": False}
        await self.store.saveRows([("exerciseLogs", {**row, "deleted": False, "declinedSuggestion": declined})])

    async def deleteWorkout(self, date: dt.date) -> None:
        """History's "Delete this workout" (HI1.1): the day's workout and every entry in it. Its steps and
        weigh-in stay."""
        edits: list[tuple[str, dict[str, Any]]] = []
        session = self._liveSession(date)
        if session is not None:
            edits.append(("sessions", dict(session, deleted=True)))
        for exerciseId in self.state.logs.get(date, {}):
            row = self.state.row("exerciseLogs", dayRowId(exerciseLogs, self.userId, date=date, exerciseId=exerciseId))
            if row is not None and not row["deleted"]:
                edits.append(("exerciseLogs", dict(row, deleted=True)))
        if edits:
            await self.store.saveRows(edits)

    async def finishWorkout(self, view: TodayView) -> None:
        """Finish: the workout is done. Anything untouched counts as skipped (19.1b-1)."""
        session = self._liveSession(view.date)
        if session is None or session["finishedAt"] is not None:
            return
        await self.store.saveRows([("sessions", dict(session, finishedAt=self.clock()))])

    # --- Steps (CA1.1) -----------------------------------------------------------------------

    async def setSteps(self, date: dt.date, steps: int | None) -> None:
        """A day's step total: entering it again replaces it. None clears it. Steps are never a workout."""
        rowId = dayRowId(dailySteps, self.userId, date=date)
        existing = self.state.row("dailySteps", rowId)
        if steps is None:
            if existing is not None and not existing["deleted"]:
                await self.store.saveRows([("dailySteps", dict(existing, deleted=True))])
            return
        _checkWhole(steps, 0, 200_000, "Steps")
        await self.store.saveRows([("dailySteps", {**(existing or {}), "id": rowId, "userId": self.userId,
                                                   "deleted": False, "date": date, "steps": steps})])

    # --- Body weight (SC5.1, DT2.1) -----------------------------------------------------------

    async def setBodyWeight(self, date: dt.date, today: dt.date, weightKg: float | None) -> None:
        """A day's weigh-in: entering it again replaces it (DT2.1). None clears it. Any day up to today. Saving
        today's keeps the time you saved it (AM6.3). A past day's keeps the time it had, if any."""
        if date > today:
            raise ActionRefused("A weigh-in can't be for a day that hasn't come yet.")
        rowId = dayRowId(bodyWeight, self.userId, date=date)
        existing = self.state.row("bodyWeight", rowId)
        if weightKg is None:
            if existing is not None and not existing["deleted"]:
                await self.store.saveRows([("bodyWeight", dict(existing, deleted=True))])
            return
        if not _isKilograms(weightKg) or not 0 < weightKg < 1000:
            raise ActionRefused("Weight must be a number above 0 and under 1000 kg, with at most 2 decimals.")
        weighedAt = self.clock() if date == today else (existing or {}).get("weighedAt")
        await self.store.saveRows([("bodyWeight", {**(existing or {}), "id": rowId, "userId": self.userId,
                                                   "deleted": False, "date": date, "weightKg": float(weightKg),
                                                   "weighedAt": weighedAt})])

    # --- Weights and weight steps (WD2.1, WD3.7) ----------------------------------------------

    async def setWeight(self, exerciseId: str, weekday: int, weightKg: float, today: dt.date,
                        doneToday: bool) -> None:
        """An exercise's weight on one day: its target there starts again from it, at repsMin. It applies
        from today, or from tomorrow if that day's session already has it logged today (doneToday)."""
        if not _isKilograms(weightKg):
            raise ActionRefused("Weight must be a number from 0 to 1000 kg, with at most 2 decimals.")
        if not 0 <= weekday <= 6:
            raise ActionRefused("That isn't a day of the week.")
        fromDate = today + dt.timedelta(days=1) if doneToday else today
        await self.store.saveRows([("exerciseWeights", {
            "id": newRowId(), "userId": self.userId, "deleted": False, "exerciseId": exerciseId,
            "weekday": weekday, "weightKg": float(weightKg), "fromDate": fromDate})])

    async def setStep(self, exerciseId: str, incrementKg: float, today: dt.date) -> None:
        """An exercise's weight step, on every day (per side for a plates-per-side lift), from today on:
        today's session already uses it for what comes next."""
        if not _isKilograms(incrementKg) or not 0.01 <= incrementKg <= 100:
            raise ActionRefused("The weight step must be a number from 0.01 to 100 kg, with at most 2 decimals.")
        await self.store.saveRows([("exerciseSteps", {
            "id": newRowId(), "userId": self.userId, "deleted": False, "exerciseId": exerciseId,
            "incrementKg": float(incrementKg), "fromDate": today})])

    # --- Deloads by hand (WD2.4, WD3.4) -------------------------------------------------------

    async def startDeload(self, today: dt.date, workoutToday: bool) -> None:
        """Starts a deload: today, or tomorrow if a workout is already logged today. 7 days."""
        if self.state.training(today).deloadOn(today) is not None or self.state.manualDeloadAt(today):
            raise ActionRefused("A deload is already running or about to start.")
        start = today + dt.timedelta(days=1) if workoutToday else today
        await self.store.saveRows([("deloads", {"id": newRowId(), "userId": self.userId, "deleted": False,
                                                "startDate": start})])

    async def stopDeload(self, today: dt.date) -> None:
        """Stops the deload you started by hand (running or still to come)."""
        rowId = self.state.manualDeloadAt(today)
        row = self.state.row("deloads", rowId) if rowId else None
        if row is not None and not row["deleted"]:
            await self.store.saveRows([("deloads", dict(row, deleted=True))])

    # --- Building the rows -------------------------------------------------------------------

    async def _log(self, view: TodayView, line: ExerciseLine, sets: Sequence[SetDone], minutes: int | None,
                   skipped: bool) -> None:
        """Saves one exercise's entry, with the day's workout if this is its first entry (DT1.1)."""
        if view.planImportId is None or view.stepIndex is None:
            raise ActionRefused("There's no plan yet: import one first.")
        edits: list[tuple[str, dict[str, Any]]] = []
        if self._liveSession(view.date) is None:
            sessionId = dayRowId(sessions, self.userId, date=view.date)
            edits.append(("sessions", {**(self.state.row("sessions", sessionId) or {}), "id": sessionId,
                                       "userId": self.userId, "deleted": False, "date": view.date,
                                       "planImportId": view.planImportId, "stepIndex": view.stepIndex,
                                       "finishedAt": None}))
        logId = dayRowId(exerciseLogs, self.userId, date=view.date, exerciseId=line.exercise.exerciseId)
        existing = self.state.row("exerciseLogs", logId)
        edits.append(("exerciseLogs", {
            "id": logId, "userId": self.userId, "deleted": False, "date": view.date,
            "exerciseId": line.exercise.exerciseId, "targetReps": line.targetReps,
            "targetWeightKg": line.targetWeightKg,
            "sets": [{"reps": done.reps} | ({"weightKg": done.weightKg} if done.weightKg is not None else {})
                     for done in sets],
            "minutes": minutes, "skipped": skipped,
            "declinedSuggestion": existing["declinedSuggestion"] if existing else False,
        }))
        await self.store.saveRows(edits)

    async def _takeBack(self, view: TodayView, line: ExerciseLine) -> None:
        """Takes an exercise's entry back. If it was the day's only entry, the workout goes too (finished or
        not): a workout exists only while something is logged in it, so a mistaken tap never counts as a
        workout. An Undo on ↑new stays (UN1.1)."""
        logId = dayRowId(exerciseLogs, self.userId, date=view.date, exerciseId=line.exercise.exerciseId)
        logRow = self.state.row("exerciseLogs", logId)
        if logRow is None or logRow["deleted"]:
            return
        keptUndo = dict(logRow, sets=[], minutes=None, skipped=False)
        edits: list[tuple[str, dict[str, Any]]] = [
            ("exerciseLogs", keptUndo if logRow["declinedSuggestion"] else dict(logRow, deleted=True))]
        othersToday = {exerciseId for exerciseId, logged in self.state.logs.get(view.date, {}).items()
                       if logged.done or logged.skipped} - {line.exercise.exerciseId}  # an Undo alone isn't one
        session = self._liveSession(view.date)
        if session is not None and not othersToday:
            edits.append(("sessions", dict(session, deleted=True)))
        await self.store.saveRows(edits)

    def _liveSession(self, date: dt.date) -> dict[str, Any] | None:
        row = self.state.row("sessions", dayRowId(sessions, self.userId, date=date))
        return row if row is not None and not row["deleted"] else None


def _checkWhole(value: Any, low: int, high: int, what: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ActionRefused(f"{what} must be a whole number from {low:,} to {high:,}.")


def _isKilograms(value: Any) -> bool:
    """0 to 1000 kg with at most 2 decimals, as the cloud stores weights."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    return 0 <= value <= 1000 and abs(value * 100 - round(value * 100)) < 1e-6
