"""What the Today screen shows (plan 6, SC2.1): the day's session and its weekday, the exercises with
their targets and what's been logged, rest days, a deload week, the week's count and the day's steps.

Pure logic: no screen, database, network or clock; "today" and every fact are passed in. Targets come
from progression (progression.py): each exercise's target on the day whose targets it uses (WD2.3,
WD3.10), and in a deload week half the sets, 3 reps short (WD3.5).
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone
from gym.rules.planFile import PlanExercise
from gym.rules.progression import Deload, Training, deloadReps, deloadSets
from gym.rules.schedule import LoggedWorkout, daySchedule, weekdayNames
from gym.rules.sessions import SessionExercise, sessionExercises
from gym.rules.stats import kgText, unit, workoutVolumeKg
from gym.rules.week import weeklyTarget, workoutsInWeek

__all__ = ["ExerciseLine", "ImportedPlan", "LoggedExercise", "SetDone", "TodayView", "deloadText", "headerText",
           "kilogramsUnit", "targetText", "todayView"]

upcomingDays = 7  # a deload starting within this many days shows on Today


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
    trackDay: int | None = None  # the day whose targets it uses and updates (WD2.3); None if it has none
    stepKg: float | None = None  # its weight step: set in the app, else the plan's (WD2.1)
    needsWeight: bool = False  # only the plan's 1 kg placeholder (PF3): "@ ? kg", no target weight, ✓ opens ▾ sets
    isNew: bool = False  # the target is a step up from the last weight: "↑new", with Undo (UN1.1)
    declined: bool = False  # Undo pressed: today's target is the last weight at repsMax, with redo (UN1.1)


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
    deload: Deload | None = None  # the deload week today is in (WD2.4)
    nextDeload: Deload | None = None  # one starting within a week
    volumeKg: float = 0  # the workout's volume so far (plan 8)


def todayView(
    plans: Sequence[ImportedPlan],
    workouts: Sequence[LoggedWorkout],
    logsToday: Mapping[str, LoggedExercise],
    knownExercises: Mapping[str, PlanExercise],
    stepsToday: int | None,
    today: dt.date,
    training: Training | None = None,
) -> TodayView:
    """Works out Today from the facts. Without `training`, targets are the plan's starting ones."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    day = daySchedule(starts, workouts, today)
    weekDone, weekTarget = workoutsInWeek(workouts, today), weeklyTarget(starts, today)
    deload = training.deloadOn(today) if training else None
    upcoming = training.upcomingDeload(today) if training and deload is None else None
    if upcoming is not None and upcoming.start > today + dt.timedelta(days=upcomingDays):
        upcoming = None
    common = {"date": today, "weekday": weekdayNames[today.weekday()].capitalize(), "weekDone": weekDone,
              "weekTarget": weekTarget, "stepsToday": stepsToday, "deload": deload, "nextDeload": upcoming}

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
    entries = sessionExercises(plan, today.weekday(), stepIndex, day.flexMakesUp) if step else []
    lines = [_line(entry, logsToday.get(entry.exercise.exerciseId), finished, training, deload is not None)
             for entry in entries]
    # Anything logged today that isn't in the session (logged from another device or plan) still shows.
    shown = {line.exercise.exerciseId for line in lines}
    for exerciseId, logged in logsToday.items():
        if exerciseId not in shown and (logged.done or logged.skipped):  # an Undo alone isn't an entry
            exercise = knownExercises.get(exerciseId) or PlanExercise(exerciseId, exerciseId, "strength")
            lines.append(ExerciseLine(exercise, None, None, None, None, "skipped" if logged.skipped else "done",
                                      logged))
    return TodayView(hasPlan=True, title=step.title if step else "Workout", makesUp=makesUp, isRestDay=False,
                     nextWorkoutTitle=nextTitle, planImportId=day.planImportId, stepIndex=stepIndex,
                     exercises=tuple(lines), workoutExists=workout is not None, finished=finished,
                     volumeKg=workoutVolumeKg(logsToday, knownExercises), **common)


def _line(entry: SessionExercise, logged: LoggedExercise | None, finished: bool, training: Training | None,
          inDeload: bool) -> ExerciseLine:
    """A planned exercise with its target from progression; in a deload, half the sets, 3 reps short."""
    exercise = entry.exercise
    if logged is not None and (logged.done or logged.skipped):  # an Undo alone isn't an entry (UN1.1)
        status = "skipped" if logged.skipped else "done"
    else:
        status = "autoSkipped" if finished else "todo"
    if exercise.isCardio:
        return ExerciseLine(exercise, None, None, None, exercise.minutes, status, logged, entry.trackDay)
    needsWeight = isNew = declined = False
    if training is not None:
        target = training.target(exercise, entry.trackDay)
        weightKg, reps, stepKg = target.weightKg, target.reps, training.stepKg(exercise)
        needsWeight = training.needsWeight(exercise, entry.trackDay)
        if target.steppedUpFrom is not None and not inDeload:  # ↑new, or Undo pressed on it (UN1.1)
            declined = logged is not None and logged.declinedSuggestion
            isNew = not declined
            if declined:
                weightKg, reps = target.steppedUpFrom, exercise.repsMax
    else:
        weightKg, reps, stepKg = exercise.weightKg, exercise.repsMin, exercise.incrementKg
    if needsWeight:
        weightKg = None  # the plan's weight is only a placeholder (PF2)
    sets = exercise.sets
    if inDeload and sets is not None and reps is not None:
        sets, reps = deloadSets(sets), deloadReps(reps)
    if exercise.equipment == "bodyweight":
        weightKg, stepKg = None, None
    return ExerciseLine(exercise, sets, reps, weightKg, None, status, logged, entry.trackDay, stepKg, needsWeight,
                        isNew, declined)


def targetText(line: ExerciseLine) -> str:
    """The target as Today writes it: "4×8 @ 80 kg", "4×8 @ 20 kg/side" (plates per side, WD1.3), "4×8 @ 82.5 kg
    ↑new" (a step up, UN1.1), "4×8 @ ? kg" (no weight of yours yet, PF3), "3×8" (bodyweight) or "15 min"."""
    if line.targetMinutes is not None:
        return f"{line.targetMinutes} min"
    if line.targetSets is None or line.targetReps is None:
        return ""
    text = f"{line.targetSets}×{line.targetReps}"
    if line.needsWeight:
        return text + f" @ ? {unit(line.exercise)}"
    if line.targetWeightKg is None:
        return text
    return text + f" @ {kgText(line.targetWeightKg)} {unit(line.exercise)}" + (" ↑new" if line.isNew else "")


def kilogramsUnit(exercise: PlanExercise) -> str:
    """"kg/side" for a lift logged as the plates on one side (WD1.3), else "kg"."""
    return unit(exercise)


def headerText(view: TodayView) -> str:
    """The top line (SC2.1, WD1.1): "Upper · Monday · week 2/5", or on the flex day doing a missed
    session "Upper · Saturday, for Monday · week 4/5"."""
    if not view.hasPlan:
        return "Today"
    parts = [view.title, view.weekday + (f", for {view.makesUp}" if view.makesUp else "")]
    if view.weekTarget is not None:
        parts.append(f"week {view.weekDone}/{view.weekTarget}")
    return " · ".join(parts)


def deloadText(view: TodayView) -> str:
    """The deload line on Today (WD2.4): this week's, or one coming up within a week."""
    reasons = {"backwards": "two compound lifts went backwards", "week8": "week 8", "manual": "started by hand"}
    if view.deload is not None:
        end = view.deload.end
        return (f"Deload week until {weekdayNames[end.weekday()][:3].capitalize()} {end.day} {end:%b}: half the "
                "sets, 3 reps short of your usual target, same weights.")
    if view.nextDeload is not None:
        start = view.nextDeload.start
        when = "tomorrow" if start == view.date + dt.timedelta(days=1) else (
            f"{weekdayNames[start.weekday()][:3].capitalize()} {start.day} {start:%b}")
        return f"Deload week from {when} ({reasons.get(view.nextDeload.reason, view.nextDeload.reason)})."
    return ""
