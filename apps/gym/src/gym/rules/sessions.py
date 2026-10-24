"""What a day's session holds (WD1.2, WD2.3): its exercises, with the plan's moves applied, and the day
each exercise's targets belong to.

Pure logic: no screen, database, network or clock.

An exercise on several days progresses separately on each day (WD2.3), so each one shown has a track
day: the day whose targets it uses and updates. That's the session's own day, which on the flex day is
the day it makes up; a moved exercise keeps the day it came from (WD3.10).
"""

from dataclasses import dataclass

from gym.rules.planFile import Plan, PlanExercise


@dataclass(frozen=True, slots=True)
class SessionExercise:
    """One exercise of a day's session, and the day whose targets it uses (0 = Monday)."""

    exercise: PlanExercise
    trackDay: int


def sessionExercises(plan: Plan, weekday: int, stepIndex: int, flexMakesUp: int | None) -> list[SessionExercise]:
    """A day's exercises (WD1.2): its session's own, with the plan's moves for what the flex day makes up
    this week. A moved exercise leaves its "from" day and joins the end of its "to" day; moved to the flex
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
