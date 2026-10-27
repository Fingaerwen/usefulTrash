"""Numbers for the Progress and Week tabs (plan 8, 10, WD3.6): the real load, volume, estimated 1RM, PRs,
each exercise's history and the week's summary.

Pure logic: no screen, database, network or clock. "today" and every fact are passed in.

The real load (WD1.3): a plates-per-side lift counts double the logged plates plus its bar or sled, the
plan's barKg or else a guess from its name (PF7). A lift with "dumbbells": 2 counts double. A barKg without
platesPerSide is added to the logged weight. Anything else counts as logged. Volume and estimated 1RM use
the real load. Weights are shown as logged (one dumbbell, or kg/side), as on Today (10.4).
"""

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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
minus = "\u2212"  # the minus sign: the built-in font has it, and it's as wide as + (LK1.2)
# The bar or sled of a plates-per-side lift without a barKg (PF7): the first of its equipment's words found
# in the name or ID, else the usual one: a 20 kg barbell, and a lever machine's arms counted as nothing.
barGuesses = {"barbell": (("ez", 10), ("trap bar", 25), ("hex bar", 25)),
              "machine": (("smith", 15), ("hack", 30), ("leg press", 50))}
usualBarKg = {"barbell": 20, "machine": 0}


# --- The real load (WD1.3, PF7) -----------------------------------------------------------------

def words(text: str) -> str:
    """Lowercase words between spaces, camelCase split: "reverseEzBarCurl" gives " reverse ez bar curl "."""
    return f" {' '.join(re.findall(r'[a-z0-9]+', re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text).lower()))} "


def barWeightKg(exercise: PlanExercise) -> float:
    """The bar's or sled's weight added to the load: the plan's barKg, else for plates per side a guess."""
    if exercise.barKg is not None:
        return exercise.barKg
    if not exercise.platesPerSide:
        return 0
    names = (words(exercise.name), words(exercise.exerciseId))
    return next((kg for phrase, kg in barGuesses.get(exercise.equipment, ())
                 if any(f" {phrase} " in name for name in names)), usualBarKg.get(exercise.equipment, 0))


def loadKg(exercise: PlanExercise, loggedKg: float) -> float:
    """The real load of one set's logged weight."""
    load = loggedKg * (2 if exercise.platesPerSide else 1) + barWeightKg(exercise)
    return load * 2 if exercise.dumbbells == 2 else load


def volumeKg(exercise: PlanExercise, sets: Sequence[SetDone]) -> float:
    """Sets × reps × real load. 0 for bodyweight (its reps are kept separate, 10.2)."""
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
    """An exercise's PRs: heaviest weight (as logged), best estimated 1RM, most reps at its current weight.
    For bodyweight, most reps in one set (16.2a, 16.3a, 10.10a)."""

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


def targetText(exercise: PlanExercise, target: Target, needsWeight: bool = False) -> str:
    """"82.5 kg × 9", "25 kg/side × 6", "? kg × 6" (no weight of yours yet, PF3), "12 reps" (bodyweight) or
    "15 min" (cardio)."""
    if exercise.isCardio:
        return f"{exercise.minutes} min"
    if needsWeight:
        return f"? {unit(exercise)} × {target.reps}"
    if target.weightKg is None:
        return f"{target.reps} reps"
    return f"{kgText(target.weightKg)} {unit(exercise)} × {target.reps}"


def setsText(exercise: PlanExercise, sets: Sequence[SetDone], minutes: int | None = None) -> str:
    """What was done, written like a target: "4×9 @ 82.5 kg". Reps that differ as "10 · 9 · 8 @ 82.5 kg", the
    weight once, so it fits next to the name on a phone. Each set's weight only when those differ."""
    if minutes is not None and not sets:
        return f"{minutes} min"
    if not sets:
        return ""
    weights = {done.weightKg for done in sets}
    if len(weights) == 1:
        (weightKg,) = weights
        reps = {done.reps for done in sets}
        text = f"{len(sets)}×{sets[0].reps}" if len(reps) == 1 else " · ".join(f"{done.reps}" for done in sets)
        return text + (f" @ {kgText(weightKg)} {unit(exercise)}" if weightKg is not None else "")
    return " · ".join(f"{done.reps}" + (f"@{kgText(done.weightKg)}" if done.weightKg is not None else "")
                      for done in sets)


def thousands(kilograms: float) -> str:
    """18400.0 as "18,400"."""
    return f"{round(kilograms):,}"


def signed(change: float, text: str | None = None) -> str:
    """A change with its sign: "+5", "−0.4" (no arrows: the built-in font hasn't got them, LK1.2)."""
    return ("+" if change > 0 else minus) + (text if text is not None else kgText(abs(change)))


def evenlyPicked(items: Sequence, count: int = chartPoints) -> list:
    """At most `count` of them, evenly spaced and always ending with the latest (a chart's points)."""
    if len(items) <= count:
        return list(items)
    step = (len(items) - 1) / (count - 1)
    return [items[round(index * step)] for index in range(count)]


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
    chart: "ChartView"  # drawn like the Charts tab (SC8.1)
    chartLabel: str  # what the chart shows: "kg", "kg/side", "reps" or "min"
    recordsText: str
    days: tuple[DayTarget, ...]
    stepKg: float | None
    lines: tuple[str, ...]  # "14 Oct  4×9 @ 82.5 kg · 3,024 kg", newest first
    recordTiles: tuple[tuple[str, str], ...] = ()  # ("Heaviest", "85 kg"), ("Est. 1RM", "~107 kg"), …


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
    """The Progress list (SC3.1): the plan's exercises with what comes next and their PR. Then past
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
        now = (targetText(exercise, training.target(exercise, nextDay, now=True),
                          training.needsWeight(exercise, nextDay, now=True)) if nextDay is not None else "")
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
    label = "min" if exercise.isCardio else "reps" if exercise.equipment == "bodyweight" else unit(exercise)

    found = records(exercise, sessions)
    parts, tiles = [], []
    if found.heaviestKg is not None:
        parts.append(f"heaviest {kgText(found.heaviestKg)} {unit(exercise)}")
        tiles.append(("Heaviest", f"{kgText(found.heaviestKg)} {unit(exercise)}"))
    if found.oneRepMaxKg is not None:
        parts.append(f"1RM ~{kgText(round(found.oneRepMaxKg))} kg")
        tiles.append(("Est. 1RM", f"~{kgText(round(found.oneRepMaxKg))} kg"))
    if found.mostReps is not None:
        parts.append(f"{found.mostReps} reps" + (f" @ {kgText(found.mostRepsAtKg)} {unit(exercise)}"
                                                 if found.mostRepsAtKg is not None else ""))
        tiles.append(("Most reps", f"{found.mostReps}" + (f" @ {kgText(found.mostRepsAtKg)}"
                                                           if found.mostRepsAtKg is not None else "")))

    dayTargets = []
    if not exercise.isCardio:
        for weekday in planDays(current, exercise.exerciseId):
            target = training.target(exercise, weekday, now=True)
            needsWeight = training.needsWeight(exercise, weekday, now=True)
            dayTargets.append(DayTarget(weekday, Target(None, target.reps) if needsWeight else target,
                                        f"{weekdayNames[weekday][:3].capitalize()} "
                                        f"{targetText(exercise, target, needsWeight)}"))
    weighted = not exercise.isCardio and exercise.equipment != "bodyweight"
    lines = []
    for session in reversed(sessions):
        line = f"{session.date.day} {session.date:%b}  {setsText(exercise, session.sets, session.minutes)}"
        volume = volumeKg(exercise, session.sets)
        lines.append(line + (f" · {thousands(volume)} kg" if volume else ""))
    return ExerciseDetail(exercise, chartRange, chartView(exercise, logs, training, today, chartRange), label,
                          "PRs: " + " · ".join(parts) if parts else "", tuple(dayTargets),
                          training.stepKg(exercise) if weighted else None, tuple(lines), tuple(tiles))


# --- The Charts tab (SC8.1) ----------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChartSession:
    """One session on the Charts tab: its working weight as logged, its sets' reps at that weight (lowest and
    highest), cardio's minutes, whether it was in a deload, and the session written out."""

    date: dt.date
    weightKg: float | None  # None for bodyweight and cardio
    lowReps: int | None
    highReps: int | None
    minutes: int | None
    deload: bool  # drawn hollow: its dip is planned
    text: str  # "12 Nov · 10 · 10 · 9 @ 27.5 kg/side"


@dataclass(frozen=True, slots=True)
class ChartView:
    """The Charts tab (SC8.1): one exercise, its sessions in the span (at most 30, oldest first)."""

    exercise: PlanExercise
    chartRange: str
    unit: str  # the kg line's unit: "kg", "kg/side". "min" for cardio
    sessions: tuple[ChartSession, ...]


def chartView(exercise: PlanExercise, logs: Mapping[dt.date, Mapping[str, LoggedExercise]], training: Training,
              today: dt.date, chartRange: str = "3M") -> ChartView:
    """An exercise's sessions for the Charts tab (SC8.1): kg as logged (the weight most sets used) and the reps
    of the sets at that weight. Bodyweight has reps only, cardio minutes. At most 30 sessions, evenly picked
    and always ending with the latest, as Progress's chart."""
    days = chartRanges.get(chartRange)
    shown = evenlyPicked([session for session in history(logs, exercise.exerciseId)
                          if days is None or session.date > today - dt.timedelta(days=days)])
    sessions = []
    for session in shown:
        weightKg = None if exercise.isCardio or exercise.equipment == "bodyweight" else workingWeight(session.sets)
        reps = [done.reps for done in session.sets if weightKg is None or done.weightKg == weightKg]
        sessions.append(ChartSession(
            session.date, weightKg, min(reps, default=None), max(reps, default=None), session.minutes,
            training.deloadOn(session.date) is not None,
            f"{session.date.day} {session.date:%b} · {setsText(exercise, session.sets, session.minutes)}"))
    return ChartView(exercise, chartRange, "min" if exercise.isCardio else unit(exercise), tuple(sessions))


# --- History: days and the monthly diary (HI1.1, DI1.1) ------------------------------------------

@dataclass(frozen=True, slots=True)
class HistoryDay:
    """One day in History's list (SC6.1): "Push · 5 exercises · finished", "Rest · 9,500 steps"."""

    date: dt.date
    text: str


def historyDays(plans: Sequence[ImportedPlan], workouts: Sequence[LoggedWorkout],
                logs: Mapping[dt.date, Mapping[str, LoggedExercise]], steps: Mapping[dt.date, int],
                weights: Mapping[dt.date, float], dates: Sequence[dt.date], today: dt.date) -> tuple[HistoryDay, ...]:
    """History's days (SC6.1, HI1.1), newest first: the session, what was done, the steps and the weigh-in."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    days = replay(starts, workouts, today)
    lines = []
    for date in sorted(dates, reverse=True):
        day = days.get(date)
        parts = []
        plan = plansById.get(day.planImportId) if day else None
        if day is not None and plan is not None and day.stepIndex is not None and day.stepIndex < len(plan.steps):
            title = plan.steps[day.stepIndex].title
            if day.makesUp is not None:
                title += f", for {weekdayNames[day.makesUp].capitalize()}"
            parts.append(title)
            if day.workout is not None:
                done = sum(1 for logged in logs.get(date, {}).values() if logged.done)
                parts.append(f"{done} exercise{'' if done == 1 else 's'}")
                finished = isFinished(day.workout, today)
                parts.append("finished" if finished else "in progress")
                if finished and not day.workout.counts:  # one in progress isn't judged yet (WD4.1)
                    parts.append("over 30% skipped")
            elif day.status == "missed":
                parts.append("missed")
        elif day is None:
            parts.append("before your plan")
        if steps.get(date):
            parts.append(f"{steps[date]:,} steps")
        if date in weights:
            parts.append(f"{kgText(weights[date])} kg")
        lines.append(HistoryDay(date, " · ".join(parts)))
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class DiaryLine:
    """One exercise's month in the diary (DI1.1), or the body weight's (exerciseId "")."""

    exerciseId: str
    name: str
    change: str  # "25 to 30 kg/side  +5"
    detail: str  # "best 3×12 @ 27.5 kg/side · 8 sessions"


@dataclass(frozen=True, slots=True)
class MonthDiary:
    """A month of the progression diary (DI1.1)."""

    month: dt.date  # its first day
    lines: tuple[DiaryLine, ...]
    firstMonth: dt.date  # the earliest month with anything logged or weighed, for ◂


def monthStart(date: dt.date) -> dt.date:
    return date.replace(day=1)


def monthDiary(current: ImportedPlan | None, known: Mapping[str, PlanExercise],
               logs: Mapping[dt.date, Mapping[str, LoggedExercise]], weights: Mapping[dt.date, float],
               month: dt.date) -> MonthDiary:
    """A month of the diary (DI1.1): each exercise done that month (the plan's in plan order, then others by
    name) with the weight it started and ended the month at, its best session and how many. Then the body
    weight's first and last weigh-in that month."""
    month = monthStart(month)
    inPlan = list(dict.fromkeys(exercise.exerciseId for step in (current.plan.steps if current else ())
                                for exercise in step.exercises))
    others = sorted((exerciseId for exerciseId in known if exerciseId not in inPlan),
                    key=lambda exerciseId: known[exerciseId].name.casefold())
    lines = []
    for exerciseId in [*inPlan, *others]:
        exercise = known.get(exerciseId)
        sessions = [session for session in history(logs, exerciseId) if monthStart(session.date) == month]
        if exercise is None or not sessions:
            continue
        count = f"{len(sessions)} session{'' if len(sessions) == 1 else 's'}"
        if exercise.isCardio:
            values, label = [session.minutes or 0 for session in sessions], "min"
            best = max(sessions, key=lambda session: session.minutes or 0)
            bestText = setsText(exercise, best.sets, best.minutes)
        elif exercise.equipment == "bodyweight":
            values, label = [max(done.reps for done in session.sets) for session in sessions], "reps"
            best = max(sessions, key=lambda session: sum(done.reps for done in session.sets))
            bestText = setsText(exercise, best.sets)
        else:
            values = [workingWeight(session.sets) or 0 for session in sessions]
            label, top = unit(exercise), max(values)
            atTop = [[done for done in session.sets if done.weightKg == top] for session in sessions]
            bestSets = max(atTop, key=lambda sets: sum(done.reps for done in sets))
            bestText = setsText(exercise, bestSets)
        lines.append(DiaryLine(exerciseId, exercise.name, _changeText(values[0], values[-1], label),
                               f"best {bestText} · {count}"))
    weighIns = [(date, weights[date]) for date in sorted(weights) if monthStart(date) == month]
    if weighIns:
        lines.append(DiaryLine("", "Body weight", _changeText(weighIns[0][1], weighIns[-1][1], "kg"),
                               f"{len(weighIns)} weigh-in{'' if len(weighIns) == 1 else 's'}"))
    dates = [date for date in logs if any(logged.done for logged in logs[date].values())] + list(weights)
    return MonthDiary(month, tuple(lines), monthStart(min(dates, default=month)))


def _changeText(first: float, last: float, label: str) -> str:
    """"25 to 30 kg/side  +5", or "25 kg/side" when it didn't change."""
    if first == last:
        return f"{kgText(first)} {label}"
    return f"{kgText(first)} to {kgText(last)} {label}  {signed(round(last - first, 2))}"


def monthlyPoints(exercise: PlanExercise | None, logs: Mapping[dt.date, Mapping[str, LoggedExercise]],
                  weights: Mapping[dt.date, float]) -> tuple[tuple[dt.date, float], ...]:
    """The diary's chart (DI1.1): one point per month, as far back as it goes: an exercise's top weight
    that month (bodyweight: most reps in a set, cardio: most minutes), or the body weight's monthly average."""
    byMonth: dict[dt.date, list[float]] = {}
    if exercise is None:
        for date, weightKg in weights.items():
            byMonth.setdefault(monthStart(date), []).append(weightKg)
        return tuple((month, round(sum(values) / len(values), 2)) for month, values in sorted(byMonth.items()))
    for session in history(logs, exercise.exerciseId):
        if exercise.isCardio:
            value = session.minutes or 0
        elif exercise.equipment == "bodyweight":
            value = max((done.reps for done in session.sets), default=0)
        else:
            value = workingWeight(session.sets) or 0
        byMonth.setdefault(monthStart(session.date), []).append(value)
    return tuple((month, max(values)) for month, values in sorted(byMonth.items()))


# --- Export CSV's readable sets, and the last backup (EX1.1, F14.1) ------------------------------

def readableSets(logs: Mapping[dt.date, Mapping[str, LoggedExercise]], known: Mapping[str, PlanExercise]) -> str:
    """sets.csv in Export CSV (EX1.1): one row per set, for a spreadsheet: date, exercise, set, reps, kg (as
    logged: one dumbbell, or the plates on one side) and its unit. Cardio as minutes. Skipped ones are left out."""
    import csv
    import io
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["date", "exercise", "exerciseId", "set", "reps", "kg", "unit", "minutes"])
    for date in sorted(logs):
        for exerciseId, logged in sorted(logs[date].items()):
            if not logged.done:
                continue
            exercise = known.get(exerciseId)
            name, kgUnit = (exercise.name, unit(exercise)) if exercise else (exerciseId, "kg")
            if not logged.sets:
                writer.writerow([date.isoformat(), name, exerciseId, "", "", "", "", logged.minutes])
            for number, done in enumerate(logged.sets, start=1):
                writer.writerow([date.isoformat(), name, exerciseId, number, done.reps,
                                 "" if done.weightKg is None else kgText(done.weightKg),
                                 "" if done.weightKg is None else kgUnit, ""])
    return text.getvalue()


def historyFiles(current: ImportedPlan | None, known: Mapping[str, PlanExercise],
                 logs: Mapping[dt.date, Mapping[str, LoggedExercise]], weights: Mapping[dt.date, float],
                 steps: Mapping[dt.date, int], today: dt.date) -> dict[str, str]:
    """The readable history, for Export CSV (EX1.1) and the history file (BK1.2): every set, every weigh-in,
    every day's steps, and the diary month by month (DI1.1), as CSV files a spreadsheet opens."""
    import csv
    import io

    def table(header: list[str], rows: list[list[Any]]) -> str:
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return text.getvalue()

    diaryRows = []
    month = monthDiary(current, known, logs, weights, today).firstMonth
    while month <= monthStart(today):
        for line in monthDiary(current, known, logs, weights, month).lines:
            diaryRows.append([f"{month:%Y-%m}", line.name, line.change, line.detail])
        month = (month + dt.timedelta(days=32)).replace(day=1)
    return {
        "sets.csv": readableSets(logs, known),
        "weighIns.csv": table(["date", "kg"], [[date.isoformat(), kgText(kg)] for date, kg in sorted(weights.items())]),
        "steps.csv": table(["date", "steps"], [[date.isoformat(), count] for date, count in sorted(steps.items())]),
        "diary.csv": table(["month", "exercise", "weight", "best and sessions"], diaryRows),
    }


def lastBackupText(backupRows: Sequence[Mapping[str, Any]], now: dt.datetime) -> str:
    """"24 Oct 2026 (phone) · 3 days ago", or "none yet" (the Problems page, the PC view's Backup tab)."""
    live = [row for row in backupRows if not row["deleted"]]
    last = max(live, key=lambda row: row["madeAt"], default=None)
    if last is None:
        return "none yet"
    madeAt = last["madeAt"]
    days = (now - madeAt).days
    when = "today" if days == 0 else "1 day ago" if days == 1 else f"{days} days ago"
    by = "PC view" if last["madeBy"] == "pcView" else "phone"
    return f"{madeAt.day} {madeAt:%b %Y} ({by}) · {when}"


# --- The Weight tab (SC5.1) ----------------------------------------------------------------------

weighInDay = 4  # Friday (G9.1): preselected on the Weight tab, and the weigh-in banner's day (18.4a)


@dataclass(frozen=True, slots=True)
class WeightView:
    """The Weight tab (SC5.1): the day preselected, the chart and the last weigh-ins."""

    preselected: dt.date  # the latest Friday up to today
    chartRange: str
    points: tuple[tuple[dt.date, float], ...]  # the weigh-ins in the span, at most 30, for the chart
    lastText: str  # "Last 4:  82.0 · 81.8 · 81.6 · 81.2   (−0.8 kg)". "" before the first weigh-in
    last: tuple[str, ...] = ()  # the last four as written: "82.0", "81.8", …
    changeText: str = ""  # across them: "−0.8 kg". "" without a change


def weightView(weights: Mapping[dt.date, float], today: dt.date, chartRange: str = "3M") -> WeightView:
    """The Weight tab (SC5.1): Friday preselected (any day can be chosen), the weigh-ins in the span for the
    chart, and the last four with the change across them."""
    days = chartRanges.get(chartRange)
    dates = [date for date in sorted(weights) if date <= today]
    shown = evenlyPicked([(date, weights[date]) for date in dates if days is None or date > today - dt.timedelta(days=days)])
    last = [weights[date] for date in dates[-4:]]
    text, changeText = "", ""
    if last:
        text = f"Last {len(last)}:  " + " · ".join(_weighIn(kg) for kg in last)
        change = round(last[-1] - last[0], 2)
        if change:
            changeText = f"{signed(change)} kg"
            text += f"   ({changeText})"
    return WeightView(today - dt.timedelta(days=(today.weekday() - weighInDay) % 7), chartRange, tuple(shown),
                      text, tuple(_weighIn(kg) for kg in last), changeText)


summaryBanner = "Last week's summary is ready."  # Mondays, until you've looked at it (18.4a, BN1.1)
weighInBanner = "Weigh-in due: today's weight goes on the Weight tab."  # Fridays, until you've weighed in (18.4a)


def dayBanners(today: dt.date, weights: Mapping[dt.date, float], hadPlanLastWeek: bool,
               summarySeenFor: dt.date | None) -> tuple[str, ...]:
    """The banners of the day (18.4a): on Mondays last week's summary until it's been seen (summarySeenFor is
    the Monday of the last week looked at, BN1.1), on Fridays the weigh-in until there's a weight for today."""
    banners = []
    lastMonday = weekStart(today) - oneWeek
    if today.weekday() == 0 and hadPlanLastWeek and summarySeenFor != lastMonday:
        banners.append(summaryBanner)
    if today.weekday() == weighInDay and today not in weights:
        banners.append(weighInBanner)
    return tuple(banners)


def _weighIn(weightKg: float) -> str:
    """A weigh-in with at least one decimal, as the sketch has it: 82.0, 81.8, 81.25."""
    text = f"{weightKg:.2f}"
    return text[:-1] if text.endswith("0") else text


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
    """Weeks in a row hitting the weekly target, up to this week (4.8a). This week counts once it's hit.
    Until then the streak runs up to last week."""
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


@dataclass(frozen=True, slots=True)
class WeekTile:
    """One number on the Week tab (SC4.1, LK1.2): "VOLUME / 18,400 kg / +6% vs last week"."""

    name: str
    value: str
    detail: str = ""
    trend: str = ""  # "up" or "down" when the detail is a change, for its arrow icon


def weekTiles(week: WeekSummary) -> list[WeekTile]:
    """The Week tab's numbers in the approved order (SC4.1). Zero parts are left out, and the week's PRs are
    listed under them (week.records)."""
    tiles = [WeekTile("Workouts", f"{week.workouts} of {week.target}" if week.target else f"{week.workouts}")]
    if week.streak:
        tiles.append(WeekTile("Streak", f"{week.streak} week" + ("s" if week.streak != 1 else "")))
    if week.completion is not None:
        tiles.append(WeekTile("Completion", f"{week.completion}%"))
    cardio = week.gymCardio + week.stepsCardio
    if cardio:
        parts = ([f"{week.gymCardio} gym"] if week.gymCardio else []) + (
            [f"{week.stepsCardio} from steps"] if week.stepsCardio else [])
        detail = " + ".join(parts) if len(parts) == 2 else ("gym" if week.gymCardio else "from steps")
        tiles.append(WeekTile("Cardio", f"{cardio} min", detail))
    if week.volumeKg:
        detail, trend = "", ""
        if week.lastWeekVolumeKg:
            change = round((week.volumeKg - week.lastWeekVolumeKg) / week.lastWeekVolumeKg * 100)
            detail = f"{signed(change, f'{abs(change)}%')} vs last week" if change else "same as last week"
            trend = "up" if change > 0 else "down" if change < 0 else ""
        tiles.append(WeekTile("Volume", f"{thousands(week.volumeKg)} kg", detail, trend))
    if week.bodyweightReps:
        tiles.append(WeekTile("Bodyweight", f"{week.bodyweightReps} reps"))
    if week.weightKg is not None:
        change = week.weightChangeKg
        tiles.append(WeekTile("Weight", f"{kgText(week.weightKg)} kg", f"{signed(change)} kg" if change else "",
                              "up" if change and change > 0 else "down" if change else ""))
    return tiles


def workoutVolumeKg(logsToday: Mapping[str, LoggedExercise], known: Mapping[str, PlanExercise]) -> float:
    """A workout's volume (plan 8), for Today's Finish line."""
    return sum(volumeKg(known[logged.exerciseId], logged.sets) for logged in logsToday.values()
               if logged.done and logged.exerciseId in known)
