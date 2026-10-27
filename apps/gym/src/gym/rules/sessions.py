"""What a day's session holds (WD1.2, WD2.3): its exercises, with the plan's moves applied, and the day
each exercise's targets belong to.

Pure logic: no screen, database, network or clock.

An exercise on several days progresses separately on each day (WD2.3), so each one shown has a track
day: the day whose targets it uses and updates. That's the session's own day, which on the flex day is
the day it makes up. A moved exercise keeps the day it came from (WD3.10).

Also whether a workout counts (WD4.1): at most 30% of its session's exercises skipped or not done.
"""

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gym.rules.facts import ImportedPlan, LoggedExercise
from gym.rules.planFile import Plan, PlanExercise
from gym.rules.schedule import LoggedWorkout, daySchedule

maxSkippedShare = 0.3  # a workout counts with at most this share of its exercises skipped or not done (WD4.1)


@dataclass(frozen=True, slots=True)
class SessionExercise:
    """One exercise of a day's session, and the day whose targets it uses (0 = Monday)."""

    exercise: PlanExercise
    trackDay: int


def sessionExercises(plan: Plan, weekday: int, stepIndex: int, flexMakesUp: int | None) -> list[SessionExercise]:
    """A day's exercises (WD1.2): its session's own, with the plan's moves for what the flex day makes up
    this week. A moved exercise leaves its "from" day and joins the end of its "to" day. Moved to the flex
    day, it joins the end of the session made up there."""
    exercises = [SessionExercise(exercise, stepIndex) for exercise in plan.steps[stepIndex].exercises]
    if flexMakesUp is None:
        return exercises
    for move in plan.moves:
        if flexMakesUp not in move.when:
            continue
        if move.fromDay == weekday:
            exercises = [entry for entry in exercises if entry.exercise.exerciseId != move.exerciseId]
        if move.toDay == weekday and all(entry.exercise.exerciseId != move.exerciseId for entry in exercises):
            exercises.append(SessionExercise(move.exercise, move.fromDay))
    return exercises


def withCounts(plans: Sequence[ImportedPlan], workouts: Sequence[LoggedWorkout],
               logs: Mapping[dt.date, Mapping[str, LoggedExercise]]) -> list[LoggedWorkout]:
    """Each workout with whether it counts (WD4.1): at most 30% of its session's exercises, moves included,
    skipped or not done (in a finished workout, the untouched ones are skipped). Today's counts once you're
    past that. Worked out in date order: an earlier day that doesn't count is missed, which can change what
    the flex day makes up and so a later day's moves."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    resolved: list[LoggedWorkout] = []
    for workout in sorted(workouts, key=lambda workout: workout.date):
        dayLogs = logs.get(workout.date, {})
        plan = plansById.get(workout.planImportId)
        if plan is not None and 0 <= workout.stepIndex < len(plan.steps):
            flexMakesUp = daySchedule(starts, [*resolved, workout], workout.date).flexMakesUp
            ids = [entry.exercise.exerciseId for entry in
                   sessionExercises(plan, workout.date.weekday(), workout.stepIndex, flexMakesUp)]
        else:
            ids = list(dayLogs)  # a plan this app can't read: what was logged is the session
        done = sum(1 for exerciseId in ids if exerciseId in dayLogs and dayLogs[exerciseId].done)
        counts = done > 0 and (len(ids) - done) <= maxSkippedShare * len(ids) + 1e-9
        resolved.append(dataclasses.replace(workout, counts=counts))
    return resolved
