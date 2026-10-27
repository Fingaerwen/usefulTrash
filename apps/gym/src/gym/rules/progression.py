"""Progression (plan 7) and deloads (WD2.4): each exercise's target on each day, worked out from the facts.

Pure logic: no screen, database, network or clock. "today" is passed in. Nothing is stored (F10.1):
the whole history is replayed day by day, so the phone and the PC view always agree.

Double progression, per track (WD2.3: an exercise's target, weight and drop-backs are its own on each
day. sessions.py says which day a logged exercise belongs to):
- One rep target for all sets. A new track starts at repsMin (12.1).
- Every set reaches repsMax → the weight step (per side for a plates-per-side lift) and back to repsMin:
  Today marks it ↑new. Undo on it (UN1.1) means not today: that session's target is the last weight at
  repsMax, judged there as usual, so topping the range again suggests the step again.
  Otherwise every set hits the target → next target = the lowest set + 1 (R6a).
- Miss = 2 or more sets under repsMin (a 1-set exercise: that set) (8.14a). Two misses in a row → back
  to the last lower weight that worked, with the reps last achieved there (R7b). After such a drop, two
  sessions in a row at the top of the range before going heavier again (R7c-1). No lower weight → the
  target stays (8.10).
- A session at another weight than the target starts afresh at that weight: judged against repsMin.
- Bodyweight exercises: reps only, past repsMax too (10.9a). Cardio: the plan's minutes, no progression.
- Where a track starts (WD3.9): a weight set in the app (WD3.7, reps back to repsMin), else the
  exercise's latest weight on any day, else the latest weight set in the app on any other day (PF6), else
  the plan's weight. A plan's 1 kg is only a placeholder (PF2): until one of the others exists, the
  exercise needs its weight (PF3), and Today asks for it instead of offering 1 kg.
- Weights and weight steps set in the app count from their dates on: sessions before one keep what
  they had, so a change never rewrites earlier progression or deloads.

Deloads (WD2.4, WD3.2–WD3.5):
- A lift goes backwards when, at its target weight, the same set falls short of the rep target in two
  sessions in a row on that day. Two or more compound lifts going backwards start a deload the next
  Monday, for one week (Monday to Sunday). Only lifts in the plan in effect count: one you no longer
  do isn't going anywhere.
- By week 8 at the latest: weeks count from the end of the last deload (the first time, from the week
  of your first workout that counts, WD4.1), and week 8 is a deload.
- A deload started by hand begins on its stored day and lasts 7 days. It replaces one that's only
  scheduled.
- In a deload: the same weight, half the sets rounded up, the rep target 3 lower (at least 1). Deload
  sessions don't count for progression or for going backwards: afterwards everything picks up where it
  left off. A deload session doesn't start a track either.
"""

import datetime as dt
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from gym.rules.facts import ImportedPlan, LoggedExercise, SetDone, StepEdit, WeightEdit
from gym.rules.planFile import PlanExercise, placeholderKg, planExercises
from gym.rules.schedule import LoggedWorkout, daySchedules, planInEffect
from gym.rules.sessions import sessionExercises

oneDay = dt.timedelta(days=1)
oneWeek = dt.timedelta(days=7)
deloadWeek = 8  # week 8 since the last deload is a deload at the latest (WD3.3)
liftsGoingBackwards = 2  # this many compound lifts going backwards start a deload
deloadRepsShort = 3  # a deload's rep target is this much lower (WD3.5)


@dataclass(frozen=True, slots=True)
class Target:
    """What a track asks for next: the weight (None for bodyweight) and the rep target. steppedUpFrom is the
    last weight when this one is a step up from it (↑new, UN1.1)."""

    weightKg: float | None
    reps: int
    steppedUpFrom: float | None = field(default=None, compare=False)  # what's asked is the weight and reps


@dataclass(frozen=True, slots=True)
class Deload:
    """A deload week: 7 days from start. reason: "backwards", "week8" or "manual"."""

    start: dt.date
    reason: str

    @property
    def end(self) -> dt.date:
        return self.start + 6 * oneDay

    def covers(self, date: dt.date) -> bool:
        return self.start <= date <= self.end


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Every track's target at one moment, with weights set for days that have no session yet, each
    exercise's latest weight on any day, and its latest weight set in the app on any day."""

    targets: Mapping[tuple[str, int], Target]
    edits: Mapping[tuple[str, int], float]
    latest: Mapping[str, float]
    latestSet: Mapping[str, float]

    def startKg(self, exerciseId: str) -> float | None:
        """Where a day with no session yet starts, if not from the plan: the latest weight lifted on any
        day, else the latest set in the app on any day (PF6)."""
        return self.latest.get(exerciseId, self.latestSet.get(exerciseId))


@dataclass(frozen=True, slots=True)
class Training:
    """What the replay found, as of `date` (today)."""

    date: dt.date
    today: _Snapshot  # before today's sessions: what Today asks for
    now: _Snapshot  # after them: what comes next (Progress)
    deloads: tuple[Deload, ...]  # every deload that has started by tomorrow
    nextDeload: Deload | None  # the next one after those, if one is known
    steps: Mapping[str, float]  # weight steps set in the app (WD2.1) in effect now, by exerciseId

    def deloadOn(self, date: dt.date) -> Deload | None:
        return next((deload for deload in self.deloads if deload.covers(date)), None)

    def upcomingDeload(self, date: dt.date) -> Deload | None:
        """The first deload starting after the date (tomorrow's is in `deloads` already)."""
        later = [deload for deload in self.deloads if deload.start > date]
        if self.nextDeload is not None:
            later.append(self.nextDeload)
        return min(later, key=lambda deload: deload.start, default=None)

    def stepKg(self, exercise: PlanExercise) -> float | None:
        """The exercise's weight step: the one set in the app, else the plan's."""
        return self.steps.get(exercise.exerciseId, exercise.incrementKg)

    def target(self, exercise: PlanExercise, trackDay: int, now: bool = False) -> Target:
        """The exercise's target on a day: today's (before today's session), or now's (what comes next)."""
        snapshot = self.now if now else self.today
        key = (exercise.exerciseId, trackDay)
        if key in snapshot.targets:
            return snapshot.targets[key]
        if key in snapshot.edits and exercise.equipment != "bodyweight" and not exercise.isCardio:
            return Target(snapshot.edits[key], exercise.repsMin or 0)
        return startingTarget(exercise, snapshot.startKg(exercise.exerciseId))

    def needsWeight(self, exercise: PlanExercise, trackDay: int, now: bool = False) -> bool:
        """True while a weighted exercise's target is the plan's 1 kg placeholder (PF2, PF3): no session on
        that day, and no weight lifted or set in the app on any day."""
        if exercise.equipment == "bodyweight" or exercise.isCardio or exercise.weightKg != placeholderKg:
            return False
        snapshot = self.now if now else self.today
        key = (exercise.exerciseId, trackDay)
        return key not in snapshot.targets and key not in snapshot.edits and snapshot.startKg(key[0]) is None


def startingTarget(exercise: PlanExercise, latestKg: float | None) -> Target:
    """A track with no history (WD3.9): the exercise's latest weight on any day (or the latest set in the
    app, PF6), else the plan's. repsMin."""
    if exercise.equipment == "bodyweight" or exercise.isCardio:
        return Target(None, exercise.repsMin or 0)
    return Target(latestKg if latestKg is not None else exercise.weightKg, exercise.repsMin or 0)


def deloadSets(sets: int) -> int:
    """Half the sets, rounded up (WD3.5): 5 → 3, 3 → 2, 1 → 1."""
    return math.ceil(sets / 2)


def deloadReps(reps: int) -> int:
    """The rep target 3 lower, at least 1 (WD3.5)."""
    return max(1, reps - deloadRepsShort)


def workingWeight(sets: Sequence[SetDone]) -> float | None:
    """The weight most sets used (the heavier on a tie). None if no set has a weight."""
    weights = Counter(done.weightKg for done in sets if done.weightKg is not None)
    if not weights:
        return None
    return max(weights, key=lambda weightKg: (weights[weightKg], weightKg))


def training(plans: Sequence[ImportedPlan], workouts: Sequence[LoggedWorkout],
             logs: Mapping[dt.date, Mapping[str, LoggedExercise]], edits: Sequence[WeightEdit],
             stepEdits: Sequence[StepEdit], manualDeloads: Sequence[dt.date], today: dt.date) -> Training:
    """Replays the history up to and including today, and what's known about tomorrow. Weights and steps
    set in the app are given oldest first. On the same day the later one wins."""
    sessions = _sessionsByDate(plans, workouts, logs)
    editsByDate: dict[dt.date, list[WeightEdit]] = {}
    for edit in edits:
        editsByDate.setdefault(edit.fromDate, []).append(edit)
    stepsByDate: dict[dt.date, list[StepEdit]] = {}
    for stepEdit in stepEdits:
        stepsByDate.setdefault(stepEdit.fromDate, []).append(stepEdit)
    manualStarts = set(manualDeloads)
    workoutDates = {workout.date for workout in workouts if workout.counts}  # week 1 starts with one that counts
    compound = _CompoundLifts(plans)
    until = today + oneDay

    replay = _Replay()
    atToday: _Snapshot | None = None
    date = min([*sessions, *editsByDate, *stepsByDate, *manualStarts, *workoutDates], default=until)
    while date <= until:
        replay.startDay(date, date in manualStarts)
        for stepEdit in stepsByDate.get(date, ()):
            replay.steps[stepEdit.exerciseId] = stepEdit.incrementKg
        for edit in editsByDate.get(date, ()):
            replay.edit(edit)
        if date == today:
            atToday = replay.snapshot()
        if date < until:
            replay.workoutOn(date, date in workoutDates)
            for trackDay, exercise, logged in sessions.get(date, ()):
                replay.session(trackDay, exercise, logged)
            replay.endDay(date, compound.on(date))
        date += oneDay
    futureManual = min((start for start in manualStarts if start > until), default=None)
    now = replay.snapshot()
    return Training(today, atToday or now, now, tuple(replay.deloads), replay.nextDeload(until, futureManual),
                    dict(replay.steps))


class _CompoundLifts:
    """The compound lifts of the plan in effect on a day, as tracks (exerciseId, day): the ones whose going
    backwards counts towards a deload."""

    def __init__(self, plans: Sequence[ImportedPlan]):
        self.starts = [imported.start for imported in plans]
        self.plans = {imported.start.planImportId: imported.plan for imported in plans}
        self.byPlan: dict[str, frozenset[tuple[str, int]]] = {}

    def on(self, date: dt.date) -> frozenset[tuple[str, int]]:
        start = planInEffect(self.starts, date)
        if start is None:
            return frozenset()
        if start.planImportId not in self.byPlan:
            plan = self.plans[start.planImportId]
            self.byPlan[start.planImportId] = frozenset(
                (exercise.exerciseId, index) for index, step in enumerate(plan.steps)
                for exercise in step.exercises if exercise.compound)
        return self.byPlan[start.planImportId]


def _sessionsByDate(plans: Sequence[ImportedPlan], workouts: Sequence[LoggedWorkout],
                    logs: Mapping[dt.date, Mapping[str, LoggedExercise]]
                    ) -> dict[dt.date, list[tuple[int, PlanExercise, LoggedExercise]]]:
    """Each day's logged exercises with the day whose targets they belong to (sessions.py) and their
    settings from the plan of that day's workout. Skipped or empty entries don't count."""
    starts = [imported.start for imported in plans]
    plansById = {imported.start.planImportId: imported.plan for imported in plans}
    workoutsByDate = {workout.date: workout for workout in workouts}
    schedules = daySchedules(starts, workouts, logs)
    byDate: dict[dt.date, list[tuple[int, PlanExercise, LoggedExercise]]] = {}
    for date in sorted(logs):
        entries = [logged for logged in logs[date].values() if logged.done]
        if not entries:
            continue
        workout = workoutsByDate.get(date)
        day = schedules[date]
        plan = plansById.get(workout.planImportId if workout else day.planImportId)
        stepIndex = workout.stepIndex if workout else date.weekday()
        shown: dict[str, tuple[int, PlanExercise]] = {}
        if plan is not None and 0 <= stepIndex < len(plan.steps):
            shown = {entry.exercise.exerciseId: (entry.trackDay, entry.exercise)
                     for entry in sessionExercises(plan, date.weekday(), stepIndex, day.flexMakesUp)}
        known = planExercises(plan) if plan is not None else {}
        for logged in entries:
            if logged.exerciseId in shown:
                trackDay, exercise = shown[logged.exerciseId]
            elif logged.exerciseId in known:  # logged outside its session: it counts for this day's session
                trackDay, exercise = stepIndex, known[logged.exerciseId]
            else:
                continue  # an exercise the plan doesn't know can't progress
            byDate.setdefault(date, []).append((trackDay, exercise, logged))
    return byDate


@dataclass
class _Track:
    """One exercise on one day, as the replay goes."""

    exercise: PlanExercise
    weightKg: float | None
    reps: int
    missesInRow: int = 0
    dropped: bool = False  # after a drop-back: two sessions at the top before going heavier (R7c-1)
    toppedInRow: int = 0
    worked: dict[float, int] = field(default_factory=dict)  # weight → the reps last achieved there (R7b)
    underTarget: frozenset[int] = frozenset()  # the sets under target last time, at the target weight
    backwards: bool = False  # the same set fell short of the target twice in a row (WD3.2)
    steppedUpFrom: float | None = None  # the weight is a step up from this one (↑new, UN1.1)

    def restart(self, weightKg: float | None) -> None:
        """A weight set in the app (WD3.7): from there at repsMin, with a clean slate."""
        self.weightKg, self.reps = weightKg, self.exercise.repsMin or 0
        self.missesInRow, self.dropped, self.toppedInRow = 0, False, 0
        self.underTarget, self.backwards, self.steppedUpFrom = frozenset(), False, None


class _Replay:
    """The replay's state: every track, the deloads, and the week-8 count."""

    def __init__(self):
        self.steps: dict[str, float] = {}  # weight steps set in the app, as of the day being replayed
        self.tracks: dict[tuple[str, int], _Track] = {}
        self.pendingEdits: dict[tuple[str, int], float] = {}  # weights set for days with no session yet
        self.latest: dict[str, float] = {}  # each exercise's weight in its latest session on any day (WD3.9)
        self.latestSet: dict[str, float] = {}  # each exercise's latest weight set in the app on any day (PF6)
        self.deloads: list[Deload] = []
        self.active: Deload | None = None
        self.scheduled: Deload | None = None
        self.weekOne: dt.date | None = None  # the Monday of week 1 for the week-8 rule (WD3.3)

    def snapshot(self) -> _Snapshot:
        return _Snapshot({key: Target(track.weightKg, track.reps, track.steppedUpFrom)
                          for key, track in self.tracks.items()},
                         dict(self.pendingEdits), dict(self.latest), dict(self.latestSet))

    # --- Days and deloads --------------------------------------------------------------------

    def startDay(self, date: dt.date, manualStart: bool) -> None:
        """A deload ending yesterday ends. One may start today."""
        if self.active is not None and date > self.active.end:
            self.active = None
            self.weekOne = _monday(date)  # weeks count from the end of the last deload
            for track in self.tracks.values():
                track.underTarget, track.backwards = frozenset(), False
        if self.active is not None:
            return  # a deload started by hand during a running one changes nothing
        if manualStart:
            self.active = Deload(date, "manual")
        elif self.scheduled is not None and self.scheduled.start == date:
            self.active = self.scheduled
        elif self.weekOne is not None and date == self.weekOne + (deloadWeek - 1) * oneWeek:
            self.active = Deload(date, "week8")
        if self.active is not None:
            self.scheduled = None
            self.deloads.append(self.active)

    def workoutOn(self, date: dt.date, hasWorkout: bool) -> None:
        """The first workout ever starts week 1 of the week-8 count."""
        if hasWorkout and self.weekOne is None:
            self.weekOne = _monday(date)

    def endDay(self, date: dt.date, compound: frozenset[tuple[str, int]]) -> None:
        """Two or more compound lifts of the plan in effect going backwards start a deload next Monday
        (WD3.2, WD3.4)."""
        if self.active is not None or self.scheduled is not None:
            return
        goingBackwards = {key[0] for key, track in self.tracks.items() if track.backwards and key in compound}
        if len(goingBackwards) >= liftsGoingBackwards:
            self.scheduled = Deload(_monday(date) + oneWeek, "backwards")

    def nextDeload(self, until: dt.date, futureManual: dt.date | None) -> Deload | None:
        """The next deload that hasn't started by `until`: one scheduled, started by hand for later, or
        week 8. None while one is running (what follows it isn't known yet)."""
        if self.active is not None:
            return None
        candidates = []
        if self.scheduled is not None:
            candidates.append(self.scheduled)
        if futureManual is not None:
            candidates.append(Deload(futureManual, "manual"))
        if self.weekOne is not None:
            weekEight = self.weekOne + (deloadWeek - 1) * oneWeek
            if weekEight > until:
                candidates.append(Deload(weekEight, "week8"))
        return min(candidates, key=lambda deload: deload.start, default=None)

    # --- Tracks ------------------------------------------------------------------------------

    def edit(self, edit: WeightEdit) -> None:
        """A weight set in the app (WD3.7). A day with no session yet starts from it when it gets one, and
        so do the exercise's other days with no weight of yours yet (PF6)."""
        self.latestSet[edit.exerciseId] = edit.weightKg
        track = self.tracks.get((edit.exerciseId, edit.weekday))
        if track is None:
            self.pendingEdits[(edit.exerciseId, edit.weekday)] = edit.weightKg
        else:
            track.restart(edit.weightKg)

    def session(self, trackDay: int, exercise: PlanExercise, logged: LoggedExercise) -> None:
        """One logged exercise. In a deload it doesn't count (WD3.5)."""
        if exercise.isCardio or not logged.sets:
            return
        key = (exercise.exerciseId, trackDay)
        track = self.tracks.get(key)
        if track is None:
            if self.active is not None:
                return  # a deload session doesn't start a track: the day still starts where it would have
            start = startingTarget(exercise, self.latest.get(key[0], self.latestSet.get(key[0])))
            track = self.tracks[key] = _Track(exercise, start.weightKg, start.reps)
            if key in self.pendingEdits:
                track.restart(self.pendingEdits.pop(key))
        track.exercise = exercise  # a newer plan's settings (rep range, step) apply from now on
        if self.active is not None:
            return
        if exercise.equipment == "bodyweight":
            _bodyweightSession(track, [done.reps for done in logged.sets])
            return
        if logged.declinedSuggestion and track.steppedUpFrom is not None:  # Undo on ↑new: not today (UN1.1)
            track.weightKg, track.reps = track.steppedUpFrom, exercise.repsMax or 0
        track.steppedUpFrom = None
        lifted = workingWeight(logged.sets)
        self._weightedSession(track, logged.sets, lifted if lifted is not None else track.weightKg)
        if lifted is not None:
            self.latest[exercise.exerciseId] = lifted

    def _weightedSession(self, track: _Track, sets: Sequence[SetDone], weightKg: float | None) -> None:
        if weightKg is None:
            return  # a weighted exercise with no weight anywhere can't progress
        exercise = track.exercise
        repsMin, repsMax = exercise.repsMin or 0, exercise.repsMax or 0
        atTarget = track.weightKg is not None and weightKg is not None and abs(weightKg - track.weightKg) < 0.005
        reps = [done.reps for done in sets if done.weightKg is None or abs(done.weightKg - weightKg) < 0.005]
        if not atTarget:  # done at another weight: a fresh start there, judged against repsMin
            track.restart(weightKg)
        target = track.reps

        under = frozenset(number for number, done in enumerate(reps) if done < target)
        track.backwards = bool(under & track.underTarget) if atTarget else False
        track.underTarget = under if atTarget else frozenset()

        if sum(done < repsMin for done in reps) >= min(2, len(reps)):  # a miss (8.14a)
            track.missesInRow += 1
            track.toppedInRow = 0
            if track.missesInRow >= 2:
                track.missesInRow = 0
                lower = [worked for worked in track.worked if worked < track.weightKg]
                if lower:  # back to the last lower weight that worked, at the reps achieved there (R7b)
                    track.weightKg = max(lower)
                    track.reps = min(max(track.worked[track.weightKg], repsMin), repsMax)
                    track.dropped = True
                    track.underTarget = frozenset()  # a new weight: nothing to compare with yet
            return
        track.missesInRow = 0
        track.worked[track.weightKg] = min(reps)
        stepKg = self.steps.get(exercise.exerciseId, exercise.incrementKg)
        if all(done >= repsMax for done in reps):
            if track.dropped and track.toppedInRow + 1 < 2:  # after a drop: twice at the top first (R7c-1)
                track.toppedInRow += 1
                track.reps = repsMax
            elif stepKg:
                track.steppedUpFrom = track.weightKg
                track.weightKg = round(track.weightKg + stepKg, 2)
                track.reps, track.dropped, track.toppedInRow = repsMin, False, 0
                track.underTarget = frozenset()  # a new weight: nothing to compare with yet
            return
        track.toppedInRow = 0
        if all(done >= target for done in reps):
            track.reps = min(reps) + 1


def _bodyweightSession(track: _Track, reps: list[int]) -> None:
    """Reps only, past repsMax too (10.9a). The same set short of the target twice is going backwards."""
    under = frozenset(number for number, done in enumerate(reps) if done < track.reps)
    track.backwards = bool(under & track.underTarget)
    track.underTarget = under
    if reps and all(done >= track.reps for done in reps):
        track.reps = min(reps) + 1


def _monday(date: dt.date) -> dt.date:
    return date - dt.timedelta(days=date.weekday())
