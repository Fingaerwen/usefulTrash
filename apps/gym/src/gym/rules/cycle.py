"""Cycle and rest-day rules (plan section 5): which step of your plan each day is.

Pure logic: no screen, database, network or clock; "today" is passed in. Nothing is stored: every
answer is replayed from the facts each time (F10.1), so the phone and the PC view always agree and
nothing has to run at midnight. The facts are the plan imports (when each takes effect and the
starting step you chose) and the logged workouts (each records which step it was, plan 14).

The rules, in plan order:
- A rotating cycle. A missed day never shifts dates: the next step just waits.
- An unplanned rest day (a training step with no workout) doesn't use up a planned Rest step (13.3).
- A planned Rest step is used up when its day ends without a workout, even if the app was never
  opened that day (R4a).
- Train anyway on a Rest step: the next workout is done and the rest is kept for later
  (19.1c-2 / 13.1a). A kept rest is used up by the next day that ends without a workout.
- "Missed" (calendar only) = the 3rd or later unplanned rest day in a row (4.9a).
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

# How many skipped rests "Train anyway" keeps owed at once; None = every skipped rest stays owed.
defaultKeptRestLimit: int | None = None

oneDay = dt.timedelta(days=1)


@dataclass(frozen=True, slots=True)
class CycleStep:
    """One step of a plan's cycle: a workout such as "Push", or a planned rest day."""

    title: str
    isRest: bool


@dataclass(frozen=True, slots=True)
class PlanStart:
    """What the cycle needs from one plan import (a `plans` row)."""

    planImportId: str
    effectiveDate: dt.date  # the first day this plan applies
    startStep: int  # the cycle step you chose to start on (17.2c)
    importedAt: dt.datetime  # breaks ties between imports taking effect on the same day
    steps: tuple[CycleStep, ...]


@dataclass(frozen=True, slots=True)
class LoggedWorkout:
    """What the cycle needs from one logged workout (a `sessions` row that isn't deleted)."""

    date: dt.date
    planImportId: str
    stepIndex: int  # which step of that plan this workout was
    finished: bool  # you tapped Finish (a past day's workout counts as finished anyway, R5a)


@dataclass(frozen=True, slots=True)
class DayCycle:
    """What the cycle says about one day."""

    date: dt.date
    planImportId: str | None  # the plan the day's step belongs to; None before the first plan
    stepIndex: int | None  # the day's step: the workout's step, or the step that was due
    isRest: bool  # no workout, and the step due was a rest
    isKeptRest: bool  # ... and that rest was kept from an earlier "Train anyway"
    workout: LoggedWorkout | None  # the workout logged that day, if any
    nextWorkoutIndex: int | None  # the workout that comes next (on a rest day: what Train anyway does)
    status: str  # "trained", "plannedRest", "unplannedRest", "missed", or "open" (today, nothing logged)


def isFinished(workout: LoggedWorkout, today: dt.date) -> bool:
    """A workout is finished once you tap Finish, or once its day is over (auto-finish, R5a)."""
    return workout.finished or workout.date < today


def dayCycle(
    plans: Iterable[PlanStart],
    workouts: Iterable[LoggedWorkout],
    today: dt.date,
    keptRestLimit: int | None = defaultKeptRestLimit,
) -> DayCycle:
    """What the cycle says about today: the step due (or done), whether it's a rest day, what's next."""
    workouts = list(workouts)
    days = replay(plans, workouts, today, keptRestLimit)
    if today in days:
        return days[today]
    # No plan applies yet (none imported, or the first one takes effect later).
    loggedToday = _oneWorkoutPerDay(workouts).get(today)
    return DayCycle(
        date=today,
        planImportId=loggedToday.planImportId if loggedToday else None,
        stepIndex=loggedToday.stepIndex if loggedToday else None,
        isRest=False,
        isKeptRest=False,
        workout=loggedToday,
        nextWorkoutIndex=None,
        status="trained" if loggedToday else "open",
    )


def replay(
    plans: Iterable[PlanStart],
    workouts: Iterable[LoggedWorkout],
    today: dt.date,
    keptRestLimit: int | None = defaultKeptRestLimit,
) -> dict[dt.date, DayCycle]:
    """Replays the cycle day by day, from the first plan's first day up to and including today.

    Days before today are over: a rest due on such a day is used up if no workout was logged.
    Today is still open. Each plan import starts its own cycle at its chosen step.
    """
    workoutsByDate = _oneWorkoutPerDay(workouts)
    days: dict[dt.date, DayCycle] = {}
    for plan, endDate in _planPeriods(plans, today):
        _replayPlan(plan, min(endDate - oneDay, today) if endDate else today, today, workoutsByDate,
                    keptRestLimit, days)
    return days


def _oneWorkoutPerDay(workouts: Iterable[LoggedWorkout]) -> dict[dt.date, LoggedWorkout]:
    """Workouts by date. There's one per day (DT1.1); should two ever exist, the same one always wins."""
    ordered = sorted(workouts, key=lambda w: (w.date, w.planImportId, w.stepIndex, w.finished))
    return {w.date: w for w in ordered}


def _planPeriods(plans: Iterable[PlanStart], today: dt.date) -> list[tuple[PlanStart, dt.date | None]]:
    """The plans that have taken effect by today, each with the day the next one takes over (or None).

    Of two imports taking effect on the same day, the later import wins. Plans without steps are
    skipped (plan import refuses them anyway).
    """
    started = sorted(
        (p for p in plans if p.effectiveDate <= today and p.steps),
        key=lambda p: (p.effectiveDate, p.importedAt),
    )
    latestPerDay = list({p.effectiveDate: p for p in started}.values())
    return [
        (plan, latestPerDay[i + 1].effectiveDate if i + 1 < len(latestPerDay) else None)
        for i, plan in enumerate(latestPerDay)
    ]


def _replayPlan(
    plan: PlanStart,
    lastDay: dt.date,
    today: dt.date,
    workoutsByDate: dict[dt.date, LoggedWorkout],
    keptRestLimit: int | None,
    days: dict[dt.date, DayCycle],
) -> None:
    """Replays one plan from its first day to lastDay, writing each day's result into `days`."""
    steps = plan.steps
    stepCount = len(steps)
    position = plan.startStep % stepCount  # the next step due in cycle order
    keptRests: list[int] = []  # rests skipped by "Train anyway", still owed, oldest first
    unplannedRestRun = 0  # unplanned rest days in a row, for "missed"

    date = plan.effectiveDate
    while date <= lastDay:
        workout = workoutsByDate.get(date)
        if workout is not None:
            unplannedRestRun = 0
            if workout.planImportId == plan.planImportId and 0 <= workout.stepIndex < stepCount:
                # Rests passed over on the way to the step done are kept for later (Train anyway);
                # training steps passed over (only possible by editing a day) are just skipped.
                index = position
                while index != workout.stepIndex:
                    if steps[index].isRest:
                        keptRests.append(index)
                    index = (index + 1) % stepCount
                if keptRestLimit is not None:
                    del keptRests[keptRestLimit:]
                position = (workout.stepIndex + 1) % stepCount
            # Otherwise it's another plan's workout (logged offline as a new plan took effect) or a
            # broken one: the day counts as trained, but this plan's cycle stays where it is.
            days[date] = DayCycle(
                date=date,
                planImportId=workout.planImportId,
                stepIndex=workout.stepIndex,
                isRest=False,
                isKeptRest=False,
                workout=workout,
                nextWorkoutIndex=_nextWorkout(steps, position),
                status="trained",
            )
        else:
            if keptRests:
                dueIndex, isRest, isKeptRest = keptRests[0], True, True
            else:
                dueIndex, isRest, isKeptRest = position, steps[position].isRest, False
            if date == today:
                status = "open"
            elif isRest:
                status = "plannedRest"
                unplannedRestRun = 0
            else:
                unplannedRestRun += 1
                status = "missed" if unplannedRestRun >= 3 else "unplannedRest"
            days[date] = DayCycle(
                date=date,
                planImportId=plan.planImportId,
                stepIndex=dueIndex,
                isRest=isRest,
                isKeptRest=isKeptRest,
                workout=None,
                nextWorkoutIndex=_nextWorkout(steps, position),
                status=status,
            )
            if date < today:
                # The day ended without a workout: a rest due that day is used up (kept ones first).
                # An unplanned rest uses nothing up: the training step just waits (13.3).
                if keptRests:
                    keptRests.pop(0)
                elif isRest:
                    position = (position + 1) % stepCount
        date += oneDay


def _nextWorkout(steps: tuple[CycleStep, ...], position: int) -> int | None:
    """The first training step at or after `position`, going round the cycle; None if there's none."""
    for offset in range(len(steps)):
        index = (position + offset) % len(steps)
        if not steps[index].isRest:
            return index
    return None
