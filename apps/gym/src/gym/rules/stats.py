"""Numbers for the Progress and Week tabs (plan 8, 10, WD3.6): the real load, volume, estimated 1RM, PRs,
each exercise's history and the week's summary.

Pure logic: no screen, database, network or clock; "today" and every fact are passed in.

The real load (WD1.3): a plates-per-side lift counts double the logged plates plus barKg; a lift with
"dumbbells": 2 counts double; a barKg without platesPerSide is added to the logged weight; anything else
counts as logged. Volume and estimated 1RM use the real load; weights are shown as logged (one dumbbell,
or kg/side), as on Today (10.4).
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone
from gym.rules.planFile import PlanExercise
from gym.rules.progression import Target, Training, workingWeight
from gym.rules.schedule import LoggedWorkout, daySchedule, isFinished, replay, weekdayNames
from gym.rules.sessions import sessionExercises
from gym.rules.week import weekStart, weeklyTarget, workoutsInWeek

oneDay = dt.timedelta(days=1)
oneWeek = dt.timedelta(days=7)
maxOneRepMaxReps = 10  # estimated 1RM only from sets of 10 reps or fewer (16.2a)
stepsPerMinute = 100  # daily steps count as cardio at 100 steps a minute (CA1.1)
chartRanges = {"3M": 92, "1Y": 365, "All": None}  # days shown (plan 10)
chartPoints = 30  # a chart has at most this many points: it fits a phone's width
sparks = "▁▂▃▄▅▆▇█"


# --- The real load (WD1.3) ----------------------------------------------------------------------

def loadKg(exercise: PlanExercise, loggedKg: float) -> float:
    """The real load of one set's logged weight."""
    load = loggedKg * (2 if exercise.platesPerSide else 1) + (exercise.barKg or 0)
    return load * 2 if exercise.dumbbells == 2 else load


def volumeKg(exercise: PlanExercise, sets: Sequence[SetDone]) -> float:
    """Sets × reps × real load; 0 for bodyweight (its reps are kept separate, 10.2)."""
    return sum(loadKg(exercise, done.weightKg) * done.reps for done in sets if done.weightKg is not None)


def oneRepMaxKg(exercise: PlanExercise, sets: Sequence[SetDone]) -> float | None:
    """The best estimated 1RM (Epley) of the sets, from the real load, using sets of 1 to 10 reps."""
    estimates = [loadKg(exercise, done.weightKg) * (1 + done.reps / 30) if done.reps > 1
                 else loadKg(exercise, done.weightKg)
                 for done in sets if done.weightKg is not None and 1 <= done.reps <= maxOneRepMaxReps]
    return max(estimates, default=None)


# --- Each exercise's history and PRs (plan 8) ----------------------------------------------------

@dataclass(frozen=True, slots=True)
class Session:
    """One day an exercise was done."""

    date: dt.date
    sets: tuple[SetDone, ...]
    minutes: int | None


@dataclass(frozen=True, slots=True)
class Records:
    """An exercise's PRs: heaviest weight (as logged), best estimated 1RM, most reps at its current weight;
    for bodyweight, most reps in one set (16.2a, 16.3a, 10.10a)."""

    heaviestKg: float | None
    oneRepMaxKg: float | None
    mostReps: int | None
    mostRepsAtKg: float | None  # the current weight the reps were done at


def history(logs: Mapping[dt.date, Mapping[str, LoggedExercise]], exerciseId: str) -> list[Session]:
    """Every day the exercise was done, oldest first. Skipped entries don't count."""
    return [Session(date, logged.sets, logged.minutes) for date in sorted(logs)
            if (logged := logs[date].get(exerciseId)) is not None and logged.done]


def records(exercise: PlanExercise, sessions: Sequence[Session]) -> Records:
    allSets = [done for session in sessions for done in session.sets]
    if not allSets:
        return Records(None, None, None, None)
    if exercise.equipment == "bodyweight":
        return Records(None, None, max(done.reps for done in allSets), None)
    weights = [done.weightKg for done in allSets if done.weightKg is not None]
    current = workingWeight(sessions[-1].sets)
    atCurrent = [done.reps for done in allSets if current is not None and done.weightKg == current]
    estimates = [estimate for session in sessions if (estimate := oneRepMaxKg(exercise, session.sets)) is not None]
    return Records(max(weights, default=None), max(estimates, default=None), max(atCurrent, default=None), current)


# --- How things are written (the same style as Today, plan 6) ------------------------------------

def kgText(weightKg: float) -> str:
    """82.5 as "82.5" and 80.0 as "80"."""
    return f"{weightKg:.2f}".rstrip("0").rstrip(".")


def unit(exercise: PlanExercise) -> str:
    """"kg/side" for a lift logged as the plates on one side (WD1.3), else "kg"."""
    return "kg/side" if exercise.platesPerSide else "kg"


def targetText(exercise: PlanExercise, target: Target) -> str:
    """"82.5 kg × 9", "25 kg/side × 6", "12 reps" (bodyweight) or "15 min" (cardio)."""
    if exercise.isCardio:
        return f"{exercise.minutes} min"
    if target.weightKg is None:
        return f"{target.reps} reps"
    return f"{kgText(target.weightKg)} {unit(exercise)} × {target.reps}"


def setsText(exercise: PlanExercise, sets: Sequence[SetDone], minutes: int | None = None) -> str:
    """What was done, written like a target: "4×9 @ 82.5 kg", or each set when they differ."""
    if minutes is not None and not sets:
        return f"{minutes} min"
    if not sets:
        return ""
    if len(set(sets)) == 1:
        first = sets[0]
        text = f"{len(sets)}×{first.reps}"
        return text + (f" @ {kgText(first.weightKg)} {unit(exercise)}" if first.weightKg is not None else "")
    return " · ".join(f"{done.reps}" + (f"@{kgText(done.weightKg)}" if done.weightKg is not None else "")
                      for done in sets)


def thousands(kilograms: float) -> str:
    """18400.0 as "18,400"."""
    return f"{round(kilograms):,}"


def sparkline(values: Sequence[float]) -> str:
    """A tiny chart in text (plan 10's "▁▂▃▃▄▅▅▆"), from lowest to highest of the values shown."""
    if not values:
        return ""
    if len(values) > chartPoints:  # evenly spaced, always ending with the latest
        step = (len(values) - 1) / (chartPoints - 1)
        values = [values[round(index * step)] for index in range(chartPoints)]
    low, high = min(values), max(values)
    if high == low:
        return sparks[3] * len(values)
    return "".join(sparks[round((value - low) / (high - low) * (len(sparks) - 1))] for value in values)


# --- The Progress tab (SC3.1) --------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProgressLine:
    """One exercise in the Progress list: "Bench Press   now 82.5 kg × 9   PR 85 kg   ▸"."""

    exercise: PlanExercise
    now: str
    record: str


@dataclass(frozen=True, slots=True)
class DayTarget:
    """What an exercise asks for next on one day of the plan, for the detail's ✎ (WD2.1)."""

    weekday: int
    target: Target
    text: str


@dataclass(frozen=True, slots=True)
class ExerciseDetail:
    """An exercise's page: chart, PRs, its target on each day, its weight step, its history."""

    exercise: PlanExercise
    chartRange: str
    chart: str
    chartLabel: str  # what the chart shows: "kg", "kg/side", "reps" or "min"
    recordsText: str
    days: tuple[DayTarget, ...]
    stepKg: float | None
    lines: tuple[str, ...]  # "14 Oct  4×9 @ 82.5 kg · 3,024 kg", newest first


def planDays(plan: ImportedPlan | None, exerciseId: str) -> list[int]:
    """The days of the plan that have the exercise (a moved one keeps its own day, WD3.10)."""
    if plan is None:
        return []
    return [index for index, step in enumerate(plan.plan.steps)
            if any(exercise.exerciseId == exerciseId for exercise in step.exercises)]


def recordText(exercise: PlanExercise, found: Records) -> str:
    if exercise.isCardio:
        return ""
    if exercise.equipment == "bodyweight":
        return f"PR {found.mostReps} reps" if found.mostReps is not None else ""
    return f"PR {kgText(found.heaviestKg)} {unit(exercise)}" if found.heaviestKg is not None else ""


def progressLines(current: ImportedPlan | None, known: Mapping[str, PlanExercise],
                  logs: Mapping[dt.date, Mapping[str, LoggedExercise]], training: Training,
                  today: dt.date) -> tuple[tuple[ProgressLine, ...], tuple[ProgressLine, ...]]:
    """The Progress list (SC3.1): the plan's exercises with what comes next and their PR; then past
    exercises (not in the plan, G10a) with their last session."""
    inPlan: dict[str, PlanExercise] = {}
    if current is not None:
        for step in current.plan.steps:
            for exercise in step.exercises:
                inPlan.setdefault(exercise.exerciseId, exercise)
    lines = []
    for exerciseId, exercise in inPlan.items():
        sessions = history(logs, exerciseId)
        nextDay = _nextDay(planDays(current, exerciseId), today, loggedToday=bool(sessions) and sessions[-1].date == today)
        now = targetText(exercise, training.target(exercise, nextDay, now=True)) if nextDay is not None else ""
        lines.append(ProgressLine(exercise, f"now {now}" if now else "", recordText(exercise, records(exercise, sessions))))
    past = []
    for exerciseId, exercise in sorted(known.items(), key=lambda item: item[1].name.casefold()):
        sessions = history(logs, exerciseId)
        if exerciseId in inPlan or not sessions:
            continue
        last = sessions[-1]
        past.append(ProgressLine(exercise, f"last {setsText(exercise, last.sets, last.minutes)}",
                                 recordText(exercise, records(exercise, sessions))))
    return tuple(lines), tuple(past)


def _nextDay(days: Sequence[int], today: dt.date, loggedToday: bool) -> int | None:
    """The next of the days from today (from tomorrow if it's done today), going round the week."""
    first = 1 if loggedToday else 0
    for offset in range(first, first + 7):
        weekday = (today.weekday() + offset) % 7
        if weekday in days:
            return weekday
    return days[0] if days else None


def exerciseDetail(exercise: PlanExercise, current: ImportedPlan | None,
                   logs: Mapping[dt.date, Mapping[str, LoggedExercise]], training: Training, today: dt.date,
                   chartRange: str = "3M") -> ExerciseDetail:
    """An exercise's page (SC3.1): the chart over 3M · 1Y · All, its PRs, its target on each of its days
    with the weight step (WD2.1), and its history, newest first, with each session's volume."""
    sessions = history(logs, exercise.exerciseId)
    days = chartRanges.get(chartRange)
    shown = [session for session in sessions if days is None or session.date > today - dt.timedelta(days=days)]
    if exercise.isCardio:
        values, label = [session.minutes or 0 for session in shown], "min"
    elif exercise.equipment == "bodyweight":
        values, label = [max(done.reps for done in session.sets) for session in shown if session.sets], "reps"
    else:
        values = [weight for session in shown if (weight := workingWeight(session.sets)) is not None]
        label = unit(exercise)

    found = records(exercise, sessions)
    parts = []
    if found.heaviestKg is not None:
        parts.append(f"heaviest {kgText(found.heaviestKg)} {unit(exercise)}")
    if found.oneRepMaxKg is not None:
        parts.append(f"1RM ~{kgText(round(found.oneRepMaxKg))} kg")
    if found.mostReps is not None:
        parts.append(f"{found.mostReps} reps" + (f" @ {kgText(found.mostRepsAtKg)} {unit(exercise)}"
                                                 if found.mostRepsAtKg is not None else ""))

    dayTargets = []
    if not exercise.isCardio:
        for weekday in planDays(current, exercise.exerciseId):
            target = training.target(exercise, weekday, now=True)
            dayTargets.append(DayTarget(weekday, target, f"{weekdayNames[weekday][:3].capitalize()} "
                                                         f"{targetText(exercise, target)}"))
    weighted = not exercise.isCardio and exercise.equipment != "bodyweight"
    lines = []
    for session in reversed(sessions):
        line = f"{session.date.day} {session.date:%b}  {setsText(exercise, session.sets, session.minutes)}"
        volume = volumeKg(exercise, session.sets)
        lines.append(line + (f" · {thousands(volume)} kg" if volume else ""))
    return ExerciseDetail(exercise, chartRange, sparkline(values), label,
                          "PRs: " + " · ".join(parts) if parts else "", tuple(dayTargets),
                          training.stepKg(exercise) if weighted else None, tuple(lines))


# --- The Week tab (SC4.1) ------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WeekSummary:
    """One Monday-to-Sunday week. Parts that are zero or unknown are None, and left out (SC4.1)."""

    monday: dt.date
    workouts: int
    target: int | None
    streak: int  # weeks in a row hitting the target, up to this one (4.8a)
    completion: int | None  # % of the finished workouts' exercises that were done
    gymCardio: int  # minutes
    stepsCardio: int  # minutes from steps (CA1.1)
    volumeKg: float
    lastWeekVolumeKg: float
    bodyweightReps: int
    records: tuple[str, ...]  # "Bench 85 kg"
    weightKg: float | None
    weightChangeKg: float | None
    calendar: tuple[tuple[dt.date, str], ...]  # "trained", "rest", "missed", "open", "later" or "none" (no plan)
    steps: tuple[int | None, ...] = ()  # each day's step total, for the calendar's steps entry (SC4.1)


def weekSummary(plans: Sequence[ImportedPlan], workouts: Sequence[LoggedWorkout],
                logs: Mapping[dt.date, Mapping[str, LoggedExercise]], known: Mapping[str, PlanExercise],
                steps: Mapping[dt.date, int], weights: Mapping[dt.date, float], monday: dt.date,
                today: dt.date) -> WeekSummary:
    """The week that starts on `monday` (SC4.1)."""
    starts = [imported.start for imported in plans]
    sunday = monday + 6 * oneDay
    dates = [monday + offset * oneDay for offset in range(7)]

    def weekLogs(start: dt.date):
        return [(date, logged) for date in sorted(logs) if start <= date < start + oneWeek
                for logged in logs[date].values() if logged.done]

    def weekVolume(start: dt.date) -> float:
        return sum(volumeKg(known[logged.exerciseId], logged.sets) for _, logged in weekLogs(start)
                   if logged.exerciseId in known)

    thisWeek = weekLogs(monday)
    gymCardio = sum(logged.minutes or 0 for _, logged in thisWeek if not logged.sets)
    bodyweightReps = sum(done.reps for _, logged in thisWeek
                         if logged.exerciseId in known and known[logged.exerciseId].equipment == "bodyweight"
                         for done in logged.sets)
    stepsCardio = sum(steps.get(date, 0) for date in dates) // stepsPerMinute

    days = replay(starts, workouts, today) if monday <= today else {}
    calendar = tuple((date, days[date].status if date in days else "later" if date > today else "none")
                     for date in dates)

    latestWeight = max((date for date in weights if monday <= date <= sunday), default=None)
    previousWeight = max((date for date in weights if date < monday), default=None)
    weightKg = weights[latestWeight] if latestWeight else None
    change = round(weightKg - weights[previousWeight], 2) if weightKg is not None and previousWeight else None

    return WeekSummary(
        monday=monday, workouts=workoutsInWeek(workouts, monday), target=weeklyTarget(starts, monday),
        streak=_streak(starts, workouts, monday, today), completion=_completion(plans, workouts, logs, dates, today),
        gymCardio=gymCardio, stepsCardio=stepsCardio, volumeKg=weekVolume(monday),
        lastWeekVolumeKg=weekVolume(monday - oneWeek), bodyweightReps=bodyweightReps,
        records=_weekRecords(logs, known, monday), weightKg=weightKg, weightChangeKg=change, calendar=calendar,
        steps=tuple(steps.get(date) for date in dates))


def _streak(starts, workouts, monday: dt.date, today: dt.date) -> int:
    """Weeks in a row hitting the weekly target, up to this week (4.8a). This week counts once it's hit;
    until then the streak runs up to last week."""
    def hit(week: dt.date) -> bool:
        target = weeklyTarget(starts, week)
        return target is not None and workoutsInWeek(workouts, week) >= target

    week, count = monday, 0
    if not hit(week):
        if weekStart(today) != monday:
            return 0  # a week that's over and missed its target
        week -= oneWeek  # this week isn't over: it doesn't break the streak yet
    while hit(week):
        count += 1
        week -= oneWeek
    return count


def _completion(plans, workouts, logs, dates, today) -> int | None:
    """Of the exercises in the week's finished workouts, the share that was done (plan 8)."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    planned = done = 0
    for workout in workouts:
        if workout.date not in dates or not isFinished(workout, today):
            continue
        plan = plansById.get(workout.planImportId)
        dayLogs = logs.get(workout.date, {})
        ids = set(dayLogs)
        if plan is not None and 0 <= workout.stepIndex < len(plan.steps):
            flexMakesUp = daySchedule(starts, workouts, workout.date).flexMakesUp
            ids |= {entry.exercise.exerciseId for entry in
                    sessionExercises(plan, workout.date.weekday(), workout.stepIndex, flexMakesUp)}
        planned += len(ids)
        done += sum(1 for exerciseId in ids if exerciseId in dayLogs and dayLogs[exerciseId].done)
    return round(done / planned * 100) if planned else None


def _weekRecords(logs, known: Mapping[str, PlanExercise], monday: dt.date) -> tuple[str, ...]:
    """Exercises that beat their earlier best this week: heaviest weight, or most reps for bodyweight."""
    found = []
    for exerciseId, exercise in known.items():
        sessions = history(logs, exerciseId)
        before = [session for session in sessions if session.date < monday]
        during = [session for session in sessions if monday <= session.date < monday + oneWeek]
        if not before or not during:
            continue
        name = exercise.name
        if exercise.equipment == "bodyweight":
            best, earlier = records(exercise, during).mostReps, records(exercise, before).mostReps
            if best is not None and earlier is not None and best > earlier:
                found.append(f"{name} {best} reps")
        elif not exercise.isCardio:
            best, earlier = records(exercise, during).heaviestKg, records(exercise, before).heaviestKg
            if best is not None and earlier is not None and best > earlier:
                found.append(f"{name} {kgText(best)} {unit(exercise)}")
    return tuple(found)


def weekTitle(week: WeekSummary) -> str:
    """"Week 14–20 Oct", or "Week 28 Sep – 4 Oct" across two months (SC4.1)."""
    sunday = week.monday + 6 * oneDay
    if week.monday.month == sunday.month:
        return f"Week {week.monday.day}–{sunday.day} {sunday:%b}"
    return f"Week {week.monday.day} {week.monday:%b} – {sunday.day} {sunday:%b}"


def weekLines(week: WeekSummary) -> list[tuple[str, str]]:
    """The Week tab's lines as (label, text), in the approved order (SC4.1); zero parts are left out."""
    lines = [("Workouts", f"{week.workouts} of {week.target}" if week.target else f"{week.workouts}")]
    if week.streak:
        lines.append(("Streak", f"{week.streak} week" + ("s" if week.streak != 1 else "")))
    if week.completion is not None:
        lines.append(("Completion", f"{week.completion}%"))
    cardio = week.gymCardio + week.stepsCardio
    if cardio:
        parts = ([f"{week.gymCardio} gym"] if week.gymCardio else []) + (
            [f"{week.stepsCardio} from steps"] if week.stepsCardio else [])
        detail = " + ".join(parts) if len(parts) == 2 else ("gym" if week.gymCardio else "from steps")
        lines.append(("Cardio", f"{cardio} min ({detail})"))
    if week.volumeKg:
        text = f"{thousands(week.volumeKg)} kg"
        if week.lastWeekVolumeKg:
            change = round((week.volumeKg - week.lastWeekVolumeKg) / week.lastWeekVolumeKg * 100)
            text += f"   {'↑' if change > 0 else '↓'} {abs(change)}% vs last week" if change else "   same as last week"
        lines.append(("Volume", text))
    if week.bodyweightReps:
        lines.append(("Bodyweight", f"{week.bodyweightReps} reps"))
    if week.records:
        lines.append(("PRs", " · ".join(week.records)))
    if week.weightKg is not None:
        text = f"{kgText(week.weightKg)} kg"
        if week.weightChangeKg:
            text += f"   {'↑' if week.weightChangeKg > 0 else '↓'} {kgText(abs(week.weightChangeKg))} kg"
        lines.append(("Weight", text))
    return lines


calendarMarks = {"trained": "✓", "rest": "·", "missed": "✗"}  # open, later and no plan: blank


def workoutVolumeKg(logsToday: Mapping[str, LoggedExercise], known: Mapping[str, PlanExercise]) -> float:
    """A workout's volume (plan 8), for Today's Finish line."""
    return sum(volumeKg(known[logged.exerciseId], logged.sets) for logged in logsToday.values()
               if logged.done and logged.exerciseId in known)
