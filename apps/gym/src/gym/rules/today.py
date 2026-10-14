"""What the Today screen shows (plan 6, SC2.1): the day's step and its place in the cycle, the
exercises with their targets and what's been logged, rest days with Train anyway, the week's count
and the day's steps.

Pure logic: no screen, database, network or clock; "today" and every fact are passed in. Targets come
straight from the plan in 0.1-alpha (repsMin at the plan's weight); progression suggestions (7) come
with 0.2-alpha.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gym.rules.cycle import LoggedWorkout, PlanStart, dayCycle
from gym.rules.planFile import Plan, PlanExercise
from gym.rules.week import weeklyTarget, workoutsInWeek


@dataclass(frozen=True, slots=True)
class ImportedPlan:
    """A plan import as the rules need it: when it starts (for the cycle) and the plan itself."""

    start: PlanStart
    plan: Plan


@dataclass(frozen=True, slots=True)
class SetDone:
    """One set as logged: reps, and the weight for weighted exercises (one dumbbell for dumbbells)."""

    reps: int
    weightKg: float | None = None


@dataclass(frozen=True, slots=True)
class LoggedExercise:
    """One exercise logged on a day (an exerciseLogs row that isn't deleted)."""

    exerciseId: str
    sets: tuple[SetDone, ...] = ()
    minutes: int | None = None  # cardio
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class ExerciseLine:
    """One line on Today: the exercise, its target, and what's been logged."""

    exercise: PlanExercise
    targetSets: int | None
    targetReps: int | None
    targetWeightKg: float | None
    targetMinutes: int | None
    status: str  # "todo", "done", "skipped", or "autoSkipped" (untouched in a finished workout, 19.1b-1)
    logged: LoggedExercise | None


@dataclass(frozen=True, slots=True)
class TodayView:
    """Everything the Today screen draws."""

    date: dt.date
    hasPlan: bool  # False: "Import your plan in the PC view" (first launch, 10)
    title: str  # the step's title from your plan, like "Push" or "Rest"
    stepNumber: int  # its place in the cycle, from 1 ("day 1 of 5"); 0 without a plan
    stepCount: int
    isRestDay: bool  # a rest day with nothing logged, Train anyway not pressed
    nextWorkoutTitle: str  # on a rest day: what comes next ("Rest day · next: Pull"), "" if nothing does
    planImportId: str | None  # the plan and step new logs belong to
    stepIndex: int | None
    exercises: tuple[ExerciseLine, ...]
    workoutExists: bool  # something is logged today (one workout per day, DT1.1)
    finished: bool
    weekDone: int  # workouts this week ("week 2/4")
    weekTarget: int | None
    stepsToday: int | None  # "Steps today: 14,000" (CA1.1)


def todayView(
    plans: Sequence[ImportedPlan],
    workouts: Sequence[LoggedWorkout],
    logsToday: Mapping[str, LoggedExercise],
    knownExercises: Mapping[str, PlanExercise],
    stepsToday: int | None,
    today: dt.date,
    trainAnyway: bool = False,
) -> TodayView:
    """Works out Today from the facts. trainAnyway: you pressed Train anyway on a rest day."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    day = dayCycle(starts, workouts, today)
    weekDone, weekTarget = workoutsInWeek(workouts, today), weeklyTarget(starts, today)
    common = {"date": today, "weekDone": weekDone, "weekTarget": weekTarget, "stepsToday": stepsToday}

    if day.planImportId is None and day.workout is None:
        return TodayView(hasPlan=False, title="", stepNumber=0, stepCount=0, isRestDay=False, nextWorkoutTitle="",
                         planImportId=None, stepIndex=None, exercises=(), workoutExists=False, finished=False,
                         **common)

    workout = day.workout
    planImportId = workout.planImportId if workout else day.planImportId
    plan = plansById.get(planImportId)
    steps = plan.steps if plan else ()
    nextIndex = day.nextWorkoutIndex
    nextTitle = steps[nextIndex].title if plan and nextIndex is not None and nextIndex < len(steps) else ""

    if workout is not None:
        stepIndex = workout.stepIndex
    elif day.isRest and (not trainAnyway or nextIndex is None):
        restTitle = steps[day.stepIndex].title if day.stepIndex is not None and day.stepIndex < len(steps) else "Rest"
        return TodayView(hasPlan=True, title=restTitle, stepNumber=(day.stepIndex or 0) + 1, stepCount=len(steps),
                         isRestDay=True, nextWorkoutTitle=nextTitle, planImportId=planImportId,
                         stepIndex=day.stepIndex, exercises=(), workoutExists=False, finished=False, **common)
    elif day.isRest:
        stepIndex = nextIndex  # Train anyway: the next workout (19.1c-2)
    else:
        stepIndex = day.stepIndex

    step = steps[stepIndex] if stepIndex is not None and 0 <= stepIndex < len(steps) else None
    finished = workout is not None and workout.finished
    lines = [_line(exercise, logsToday.get(exercise.exerciseId), finished) for exercise in
             (step.exercises if step else ())]
    # Anything logged today that isn't in the step (logged from another device or plan) still shows.
    shown = {line.exercise.exerciseId for line in lines}
    for exerciseId, logged in logsToday.items():
        if exerciseId not in shown:
            exercise = knownExercises.get(exerciseId) or PlanExercise(exerciseId, exerciseId, "strength")
            lines.append(ExerciseLine(exercise, None, None, None, None, "skipped" if logged.skipped else "done",
                                      logged))
    return TodayView(hasPlan=True, title=step.title if step else "Workout", stepNumber=(stepIndex or 0) + 1,
                     stepCount=len(steps), isRestDay=False, nextWorkoutTitle=nextTitle, planImportId=planImportId,
                     stepIndex=stepIndex, exercises=tuple(lines), workoutExists=workout is not None,
                     finished=finished, **common)


def _line(exercise: PlanExercise, logged: LoggedExercise | None, finished: bool) -> ExerciseLine:
    """A planned exercise with its target: repsMin at the plan's weight for now (12.1)."""
    if logged is not None:
        status = "skipped" if logged.skipped else "done"
    else:
        status = "autoSkipped" if finished else "todo"
    if exercise.isCardio:
        return ExerciseLine(exercise, None, None, None, exercise.minutes, status, logged)
    return ExerciseLine(exercise, exercise.sets, exercise.repsMin, exercise.weightKg, None, status, logged)


def targetText(line: ExerciseLine) -> str:
    """The target as Today writes it: "4×8 @ 80 kg", "3×8" (bodyweight) or "15 min"."""
    if line.targetMinutes is not None:
        return f"{line.targetMinutes} min"
    if line.targetSets is None or line.targetReps is None:
        return ""
    text = f"{line.targetSets}×{line.targetReps}"
    return text + (f" @ {_kilograms(line.targetWeightKg)} kg" if line.targetWeightKg is not None else "")


def headerText(view: TodayView) -> str:
    """The top line (SC2.1): "Push · day 1 of 5 · week 2/4"."""
    if not view.hasPlan:
        return "Today"
    parts = [view.title, f"day {view.stepNumber} of {view.stepCount}"]
    if view.weekTarget is not None:
        parts.append(f"week {view.weekDone}/{view.weekTarget}")
    return " · ".join(parts)


def _kilograms(weightKg: float) -> str:
    """82.5 as "82.5" and 80.0 as "80"."""
    return f"{weightKg:.2f}".rstrip("0").rstrip(".")
