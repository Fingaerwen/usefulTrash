"""Week numbers (plan 6 and 8): workouts in a week against the weekly target, for the Today header
("week 2/4") and the Week tab. Weeks run Monday to Sunday.

Pure logic: no screen, database, network or clock. The date is passed in.
"""

import datetime as dt
from collections.abc import Iterable

from gym.rules.schedule import LoggedWorkout, PlanStart, planInEffect

oneWeek = dt.timedelta(days=7)


def weekStart(date: dt.date) -> dt.date:
    """The Monday of the date's week."""
    return date - dt.timedelta(days=date.weekday())


def weeklyTarget(plans: Iterable[PlanStart], date: dt.date) -> int | None:
    """The workout target of the date's week: the plan in effect on its Monday decides (17.4a).

    A week whose Monday had no plan yet (your first import) takes the target of the first plan that
    took effect during it. None if no plan applies to the week.
    """
    plans = list(plans)
    monday = weekStart(date)
    plan = planInEffect(plans, monday)
    if plan is None:
        firstStart = min((p.effectiveDate for p in plans if monday < p.effectiveDate < monday + oneWeek and p.days),
                         default=None)
        plan = planInEffect(plans, firstStart) if firstStart else None
    return plan.weeklyTarget if plan else None


def workoutsInWeek(workouts: Iterable[LoggedWorkout], date: dt.date) -> int:
    """How many days of the date's week have a workout that counts (WD4.1). Daily steps are never a workout
    (CA1.1)."""
    monday = weekStart(date)
    return len({workout.date for workout in workouts if workout.counts and monday <= workout.date < monday + oneWeek})
