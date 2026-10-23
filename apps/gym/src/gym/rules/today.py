"""What the Today screen shows (plan 6, SC2.1): the day's session and its weekday, the exercises with
their targets and what's been logged, rest days, the week's count and the day's steps.

Pure logic: no screen, database, network or clock; "today" and every fact are passed in. Targets come
straight from the plan in 0.1-alpha (repsMin at the plan's weight); progression suggestions (7) come
with 0.2-alpha.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gym.rules.planFile import Plan, PlanExercise
from gym.rules.schedule import LoggedWorkout, PlanStart, daySchedule, weekdayNames
from gym.rules.week import weeklyTarget, workoutsInWeek


@dataclass(frozen=True, slots=True)
class ImportedPlan:
    """A plan import as the rules need it: when it starts (for the schedule) and the plan itself."""

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
    title: str  # the session's title from your plan, like "Push" or "Rest"
    weekday: str  # "Monday"
    makesUp: str | None  # the flex day doing a missed session: whose ("Monday"), for "Saturday, for Monday"
    isRestDay: bool  # a rest day with nothing logged
    nextWorkoutTitle: str  # on a rest day: what comes next ("Rest day · next: Upper"), "" if nothing does
    planImportId: str | None  # the plan and session new logs belong to
    stepIndex: int | None  # whose session it is (0 = Monday's)
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
) -> TodayView:
    """Works out Today from the facts."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    day = daySchedule(starts, workouts, today)
    weekDone, weekTarget = workoutsInWeek(workouts, today), weeklyTarget(starts, today)
    common = {"date": today, "weekday": weekdayNames[today.weekday()].capitalize(), "weekDone": weekDone,
              "weekTarget": weekTarget, "stepsToday": stepsToday}

    if day.planImportId is None and day.workout is None:
        return TodayView(hasPlan=False, title="", makesUp=None, isRestDay=False, nextWorkoutTitle="",
                         planImportId=None, stepIndex=None, exercises=(), workoutExists=False, finished=False,
                         **common)

    workout = day.workout
    plan = plansById.get(day.planImportId)
    steps = plan.steps if plan else ()
    nextIndex = day.nextWorkoutIndex
    nextTitle = steps[nextIndex].title if plan and nextIndex is not None and nextIndex < len(steps) else ""
    stepIndex = day.stepIndex
    step = steps[stepIndex] if stepIndex is not None and 0 <= stepIndex < len(steps) else None
    makesUp = weekdayNames[day.makesUp].capitalize() if day.makesUp is not None else None

    if day.isRest:
        return TodayView(hasPlan=True, title=step.title if step else "Rest", makesUp=None, isRestDay=True,
                         nextWorkoutTitle=nextTitle, planImportId=day.planImportId, stepIndex=stepIndex, exercises=(),
                         workoutExists=False, finished=False, **common)

    finished = workout is not None and workout.finished
    exercises = sessionExercises(plan, today.weekday(), stepIndex, day.flexMakesUp) if step else []
    lines = [_line(exercise, logsToday.get(exercise.exerciseId), finished) for exercise in exercises]
    # Anything logged today that isn't in the session (logged from another device or plan) still shows.
    shown = {line.exercise.exerciseId for line in lines}
    for exerciseId, logged in logsToday.items():
        if exerciseId not in shown:
            exercise = knownExercises.get(exerciseId) or PlanExercise(exerciseId, exerciseId, "strength")
            lines.append(ExerciseLine(exercise, None, None, None, None, "skipped" if logged.skipped else "done",
                                      logged))
    return TodayView(hasPlan=True, title=step.title if step else "Workout", makesUp=makesUp, isRestDay=False,
                     nextWorkoutTitle=nextTitle, planImportId=day.planImportId, stepIndex=stepIndex,
                     exercises=tuple(lines), workoutExists=workout is not None, finished=finished, **common)


def sessionExercises(plan: Plan, weekday: int, stepIndex: int, flexMakesUp: int | None) -> list[PlanExercise]:
    """A day's exercises (WD1.2): its session's own, with the plan's moves for what the flex day makes up
    this week. A moved exercise leaves its "from" day and joins the end of its "to" day; moved to the flex
    day, it joins the end of the session made up there."""
    exercises = list(plan.steps[stepIndex].exercises)
    if flexMakesUp is None:
        return exercises
    for move in plan.moves:
        if flexMakesUp not in move.when:
            continue
        if move.fromDay == weekday:
            exercises = [exercise for exercise in exercises if exercise.exerciseId != move.exerciseId]
        if move.toDay == weekday and all(exercise.exerciseId != move.exerciseId for exercise in exercises):
            exercises.append(move.exercise)
    return exercises


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
    """The target as Today writes it: "4×8 @ 80 kg", "4×8 @ 20 kg/side" (plates per side, WD1.3), "3×8"
    (bodyweight) or "15 min"."""
    if line.targetMinutes is not None:
        return f"{line.targetMinutes} min"
    if line.targetSets is None or line.targetReps is None:
        return ""
    text = f"{line.targetSets}×{line.targetReps}"
    if line.targetWeightKg is None:
        return text
    return text + f" @ {_kilograms(line.targetWeightKg)} {kilogramsUnit(line.exercise)}"


def kilogramsUnit(exercise: PlanExercise) -> str:
    """"kg/side" for a lift logged as the plates on one side (WD1.3), else "kg"."""
    return "kg/side" if exercise.platesPerSide else "kg"


def headerText(view: TodayView) -> str:
    """The top line (SC2.1, WD1.1): "Upper · Monday · week 2/5", or on the flex day doing a missed
    session "Upper · Saturday, for Monday · week 4/5"."""
    if not view.hasPlan:
        return "Today"
    parts = [view.title, view.weekday + (f", for {view.makesUp}" if view.makesUp else "")]
    if view.weekTarget is not None:
        parts.append(f"week {view.weekDone}/{view.weekTarget}")
    return " · ".join(parts)


def _kilograms(weightKg: float) -> str:
    """82.5 as "82.5" and 80.0 as "80"."""
    return f"{weightKg:.2f}".rstrip("0").rstrip(".")
