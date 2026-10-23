"""What your taps do (plan 6; CS1.1's one write path): each action builds the rows it changes and
hands them to the store in one go, so a workout day and its exercises are saved together. Screens
never write rows themselves, and the store stamps every edit's time.

A day's workout, an exercise on a day and a day's steps have IDs worked out from your user ID and the
date (DT1.1), so the phone and the PC view always change the same rows. Taking something back marks
its row deleted, which syncs like any edit.
"""

import datetime as dt
import math
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from gym.rules.today import ExerciseLine, SetDone, TodayView
from gym.state import GymState
from gym.tables import exerciseLogs, sessions
from usefulShared.tables import dailySteps, dayRowId


class RowStore(Protocol):
    """Where actions save: the phone's database (then sync) or, in the PC view, the cloud."""

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]: ...


class ActionRefused(ValueError):
    """An entry that can't be saved; the message says why in plain words, for the screen."""


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
        elif line.targetReps is not None and line.targetSets:
            await self._log(view, line, (SetDone(line.targetReps, line.targetWeightKg),) * line.targetSets, None,
                            skipped=False)
        else:
            raise ActionRefused("This exercise has no target here: enter what you did with ▾ sets.")

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

    async def finishWorkout(self, view: TodayView) -> None:
        """Finish: the workout is done; anything untouched counts as skipped (19.1b-1)."""
        session = self._liveSession(view.date)
        if session is None or session["finishedAt"] is not None:
            return
        await self.store.saveRows([("sessions", dict(session, finishedAt=self.clock()))])

    # --- Steps (CA1.1) -----------------------------------------------------------------------

    async def setSteps(self, date: dt.date, steps: int | None) -> None:
        """A day's step total: entering it again replaces it; None clears it. Steps are never a workout."""
        rowId = dayRowId(dailySteps, self.userId, date=date)
        existing = self.state.row("dailySteps", rowId)
        if steps is None:
            if existing is not None and not existing["deleted"]:
                await self.store.saveRows([("dailySteps", dict(existing, deleted=True))])
            return
        _checkWhole(steps, 0, 200_000, "Steps")
        await self.store.saveRows([("dailySteps", {**(existing or {}), "id": rowId, "userId": self.userId,
                                                   "deleted": False, "date": date, "steps": steps})])

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
        workout."""
        logId = dayRowId(exerciseLogs, self.userId, date=view.date, exerciseId=line.exercise.exerciseId)
        logRow = self.state.row("exerciseLogs", logId)
        if logRow is None or logRow["deleted"]:
            return
        edits: list[tuple[str, dict[str, Any]]] = [("exerciseLogs", dict(logRow, deleted=True))]
        othersToday = set(self.state.logs.get(view.date, {})) - {line.exercise.exerciseId}
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
