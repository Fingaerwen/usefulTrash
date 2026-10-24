"""The facts the rules work from, as the rules see them (plan 14, F10.1): plan imports, logged exercises,
and what you set in the app (weights, weight steps, deloads started by hand). Weights and steps set in
the app are dated changes, given oldest first (state.py orders them).

Pure data: no screen, database, network or clock. state.py turns stored rows into these.
"""

import datetime as dt
from dataclasses import dataclass

from gym.rules.planFile import Plan
from gym.rules.schedule import PlanStart


@dataclass(frozen=True, slots=True)
class ImportedPlan:
    """A plan import as the rules need it: when it starts (for the schedule) and the plan itself."""

    start: PlanStart
    plan: Plan


@dataclass(frozen=True, slots=True)
class SetDone:
    """One set as logged: reps, and the weight for weighted exercises (one dumbbell for dumbbells, the
    plates on one side for a plates-per-side lift)."""

    reps: int
    weightKg: float | None = None


@dataclass(frozen=True, slots=True)
class LoggedExercise:
    """One exercise logged on a day (an exerciseLogs row that isn't deleted)."""

    exerciseId: str
    sets: tuple[SetDone, ...] = ()
    minutes: int | None = None  # cardio
    skipped: bool = False
    declinedSuggestion: bool = False  # Undo on ↑new: today's target stays at the last weight (UN1.1)

    @property
    def done(self) -> bool:
        """Something was done: sets or minutes, and not skipped."""
        return not self.skipped and (bool(self.sets) or self.minutes is not None)


@dataclass(frozen=True, slots=True)
class WeightEdit:
    """A weight you set in the app for one exercise on one day (WD2.1): from fromDate on, that day's
    target starts again from this weight at repsMin (WD3.7). Every change is kept, so a later one never
    rewrites what an earlier one did."""

    exerciseId: str
    weekday: int  # 0 = Monday
    weightKg: float
    fromDate: dt.date


@dataclass(frozen=True, slots=True)
class StepEdit:
    """A weight step you set in the app for one exercise (WD2.1): from fromDate on, it replaces the
    plan's incrementKg on every day. Sessions before it keep the step they had."""

    exerciseId: str
    incrementKg: float
    fromDate: dt.date
