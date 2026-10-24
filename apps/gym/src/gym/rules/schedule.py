"""The weekly schedule (plan section 5, WD1.1): which session each day is.

Pure logic: no screen, database, network or clock; "today" is passed in. Nothing is stored: every
answer is worked out from the facts each time (F10.1), so the phone and the PC view always agree and
nothing has to run at midnight. The facts are the plan imports (when each takes effect) and the logged
workouts (each records which session it was, plan 14).

The rules, in plan order:
- Each weekday has its own session, Monday to Sunday, and today's weekday decides it. A missed day
  is just missed: nothing shifts, and rest days are rest (no Train anyway).
- A missed day is a workout day that ended without a workout, under the plan in effect that day.
- The flex day (the one with `makeUp`) shows a session missed earlier in its week: the first missed
  one in the plan's priority order. If none was missed, it shows its own workout (the bonus).
- Days before the flex day decide it as far as they can: on Thursday, Monday to Wednesday are over
  and Thursday and Friday are assumed trained. The plan's exercise moves use this (WD1.2, today.py).
- Calendar: "trained", "rest" (a rest day, or a flex day with nothing to make up), "missed" (any other
  workout day that ended without a workout), or "open" (today, nothing logged yet).
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

oneDay = dt.timedelta(days=1)
weekdayNames = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True, slots=True)
class ScheduleDay:
    """One weekday of a plan: a workout such as "Upper", or a rest day."""

    title: str
    isRest: bool
    makeUp: tuple[int, ...] = ()  # the flex day: the earlier weekdays it makes up, by priority (0 = Monday)


@dataclass(frozen=True, slots=True)
class PlanStart:
    """What the rules need from one plan import (a `plans` row)."""

    planImportId: str
    effectiveDate: dt.date  # the first day this plan applies
    importedAt: dt.datetime  # breaks ties between imports taking effect on the same day
    days: tuple[ScheduleDay, ...]  # Monday to Sunday
    weeklyTarget: int  # workouts a week (17.1a)


@dataclass(frozen=True, slots=True)
class LoggedWorkout:
    """What the schedule needs from one logged workout (a `sessions` row that isn't deleted)."""

    date: dt.date
    planImportId: str
    stepIndex: int  # whose session it was (0 = Monday's); on the flex day, the one it made up, or its own
    finished: bool  # you tapped Finish (a past day's workout counts as finished anyway, R5a)


@dataclass(frozen=True, slots=True)
class DaySchedule:
    """What the schedule says about one day."""

    date: dt.date
    planImportId: str | None  # the plan the day's session belongs to; None before the first plan
    stepIndex: int | None  # the day's session: the workout's, or the weekday's own, or the one it makes up
    isRest: bool  # no workout, and the weekday is a rest day
    makesUp: int | None  # the flex day showing (or having done) a missed session: that weekday
    flexMakesUp: int | None  # what this week's flex day makes up, as far as this day knows (for moves)
    workout: LoggedWorkout | None  # the workout logged that day, if any
    nextWorkoutIndex: int | None  # the next weekday with a workout ("Rest day · next: Upper")
    status: str  # "trained", "rest", "missed", or "open" (today, nothing logged)


def isFinished(workout: LoggedWorkout, today: dt.date) -> bool:
    """A workout is finished once you tap Finish, or once its day is over (auto-finish, R5a)."""
    return workout.finished or workout.date < today


def daySchedule(plans: Iterable[PlanStart], workouts: Iterable[LoggedWorkout], today: dt.date) -> DaySchedule:
    """What the schedule says about today: its session (or the workout done), and what comes next."""
    return _day(list(plans), _oneWorkoutPerDay(workouts), today, today)


def daySchedules(plans: Iterable[PlanStart], workouts: Iterable[LoggedWorkout],
                 dates: Iterable[dt.date]) -> dict[dt.date, DaySchedule]:
    """daySchedule for several days, each as that day saw it, with the workouts sorted only once."""
    plans, workoutsByDate = list(plans), _oneWorkoutPerDay(workouts)
    return {date: _day(plans, workoutsByDate, date, date) for date in dates}


def replay(
    plans: Iterable[PlanStart], workouts: Iterable[LoggedWorkout], today: dt.date
) -> dict[dt.date, DaySchedule]:
    """Every day from the first plan's first day up to and including today (the Week tab's calendar).

    Days before today are over: a workout day without a workout is missed. Today is still open.
    """
    plans, workoutsByDate = list(plans), _oneWorkoutPerDay(workouts)
    date = min((plan.effectiveDate for plan in plans if plan.days), default=None)
    days: dict[dt.date, DaySchedule] = {}
    while date is not None and date <= today:
        days[date] = _day(plans, workoutsByDate, date, today)
        date += oneDay
    return days


def planInEffect(plans: Iterable[PlanStart], date: dt.date) -> PlanStart | None:
    """The plan that applies on a date: the latest to take effect by then (the later import on a tie)."""
    started = [plan for plan in plans if plan.effectiveDate <= date and plan.days]
    return max(started, key=_importOrder, default=None)


def flexDayIndex(days: tuple[ScheduleDay, ...]) -> int | None:
    """The plan's flex day (0 = Monday), if it has one; plan import allows at most one."""
    return next((index for index, day in enumerate(days) if day.makeUp), None)


def _day(plans: list[PlanStart], workoutsByDate: Mapping[dt.date, LoggedWorkout], date: dt.date,
         today: dt.date) -> DaySchedule:
    """What the schedule says about one day, today or earlier."""
    workout = workoutsByDate.get(date)
    plan = planInEffect(plans, date)
    if plan is None:  # no plan applies yet (none imported, or the first takes effect later)
        return DaySchedule(date=date, planImportId=workout.planImportId if workout else None,
                           stepIndex=workout.stepIndex if workout else None, isRest=False, makesUp=None,
                           flexMakesUp=None, workout=workout, nextWorkoutIndex=None,
                           status="trained" if workout else "open")

    weekday, flexIndex = date.weekday(), flexDayIndex(plan.days)
    flexMakesUp = _flexMakesUp(plans, plan, workoutsByDate, date)
    isFlexDay = weekday == flexIndex
    if workout is not None:
        stepIndex = workout.stepIndex
        makesUp = stepIndex if isFlexDay and stepIndex != weekday else None
        isRest, status = False, "trained"
    else:
        makesUp = flexMakesUp if isFlexDay else None
        stepIndex = weekday if makesUp is None else makesUp
        isRest = plan.days[weekday].isRest
        if date == today:
            status = "open"
        elif isRest or (isFlexDay and makesUp is None):
            status = "rest"  # a bonus left out isn't a missed day
        else:
            status = "missed"
    return DaySchedule(date=date, planImportId=workout.planImportId if workout else plan.planImportId,
                       stepIndex=stepIndex, isRest=isRest, makesUp=makesUp, flexMakesUp=flexMakesUp,
                       workout=workout, nextWorkoutIndex=_nextWorkout(plan.days, weekday), status=status)


def _flexMakesUp(plans: list[PlanStart], plan: PlanStart, workoutsByDate: Mapping[dt.date, LoggedWorkout],
                 date: dt.date) -> int | None:
    """What the flex day of the date's week makes up, as far as the date knows; None for the bonus.

    Days before the date (and before the flex day) are over; the others are assumed trained. On or after
    the flex day, a workout logged on it says what it was.
    """
    flexIndex = flexDayIndex(plan.days)
    if flexIndex is None:
        return None
    monday = date - dt.timedelta(days=date.weekday())
    flexDate = monday + dt.timedelta(days=flexIndex)
    logged = workoutsByDate.get(flexDate)
    if date >= flexDate and logged is not None:
        return logged.stepIndex if logged.stepIndex != flexIndex else None
    knownOn = min(date, flexDate)
    for index in plan.days[flexIndex].makeUp:
        missedDate = monday + dt.timedelta(days=index)
        if missedDate < knownOn and _missed(plans, workoutsByDate, missedDate):
            return index
    return None


def _missed(plans: list[PlanStart], workoutsByDate: Mapping[dt.date, LoggedWorkout], date: dt.date) -> bool:
    """Whether a past day was a workout day, under the plan in effect then, that ended without one."""
    plan = planInEffect(plans, date)
    return plan is not None and not plan.days[date.weekday()].isRest and date not in workoutsByDate


def _importOrder(plan: PlanStart) -> tuple[dt.date, dt.datetime, str]:
    """Plans in the order they take over; the id only makes exact ties come out the same every time."""
    return (plan.effectiveDate, plan.importedAt, plan.planImportId)


def _oneWorkoutPerDay(workouts: Iterable[LoggedWorkout]) -> dict[dt.date, LoggedWorkout]:
    """Workouts by date. There's one per day (DT1.1); should two ever exist, the same one always wins."""
    ordered = sorted(workouts, key=lambda w: (w.date, w.planImportId, w.stepIndex, w.finished))
    return {w.date: w for w in ordered}


def _nextWorkout(days: tuple[ScheduleDay, ...], weekday: int) -> int | None:
    """The first weekday with a workout after this one, going round the week; None if there's none."""
    for offset in range(1, len(days) + 1):
        index = (weekday + offset) % len(days)
        if not days[index].isRest:
            return index
    return None
