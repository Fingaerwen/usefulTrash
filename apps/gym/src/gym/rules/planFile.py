"""Plan file checks (plan 4 and 12b): reads a plan file, lists every problem in it in plain words
(G8a) and turns a valid one into a Plan for the other rules.

Pure logic: no screen, database or network. A file being imported is checked strictly, so typos are
caught (an unknown field is an error). A plan that's already stored is read leniently: fields that a
newer app version might add are ignored, so an older app can still read it. Each problem names its
place (Monday "Upper", exercise 2 "Dips") and the field, so the list can be pasted back to whoever
wrote the plan. Problems that would lose or garble something are errors (the plan is refused);
harmless ones are warnings (it's imported anyway).

A plan is a week, Monday to Sunday (WD1.1). Inside the app each day is a step: step 0 is Monday.
"""

import dataclasses
import difflib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

from gym.rules.schedule import ScheduleDay, weekdayNames

maxFileBytes = 1_000_000  # a plan is a few KB; a file this big isn't one
idPattern = re.compile(r"[a-z][A-Za-z0-9]{0,99}")  # camelCase (11.4c), at most 100 characters
equipmentKinds = ("barbell", "dumbbell", "bodyweight", "machine")
plateLoaded = ("barbell", "machine")  # what platesPerSide and barKg are for (WD1.3)
bodyParts = ("upper", "lower")
exerciseKinds = ("strength", "cardio")
defaultIncrementKg = {"upper": 2.5, "lower": 5.0}  # used when the plan gives no incrementKg (9.1)
placeholderKg = 1.0  # the weight your plans give every weighted exercise: a placeholder, set in the app (PF2)

# The how-to shown when you tap an exercise on Today (SC7.1): what you need, the steps, form cues.
howToFields = ("setup", "howTo", "form")
maxSetupLength = 300
maxHowToLines, maxHowToLineLength = 12, 200  # for each of howTo and form

# How volume and estimated 1RM count the weight (WD1.3), and the lifts the deload trigger watches; read
# now, used from 0.2-alpha.
loadFields = ("dumbbells", "platesPerSide", "barKg", "compound")

# The fields each block may have.
planFields = ("planId", "name", "version", "weeklyTarget", "week")
dayFields = ("day", "title", "restDay", "makeUp", "moves", "exercises")
moveFields = ("exerciseId", "from", "to", "when")
strengthFields = ("exerciseId", "name", "type", "equipment", "body", "sets", "repsMin", "repsMax", "weightKg",
                  "incrementKg", *loadFields, "restSec", "notes", *howToFields)
cardioFields = ("exerciseId", "name", "type", "minutes", "notes", *howToFields)
exerciseFields = tuple(dict.fromkeys(strengthFields + cardioFields))  # every field any exercise may have

# What must match when one exercise is on several days. Notes and rest time are display only, and the
# number of sets may differ (WD1.4): progress is about reps and weight.
sameEverywhere = ("name", "kind", "equipment", "body", "repsMin", "repsMax", "weightKg", "incrementKg", "dumbbells",
                  "platesPerSide", "barKg", "compound", "minutes")
fieldNames = {"kind": "type"}  # PlanExercise names that differ from the file's


@dataclass(frozen=True, slots=True)
class PlanExercise:
    """One exercise of a plan step, checked, with its weight increment worked out."""

    exerciseId: str
    name: str
    kind: str  # "strength" or "cardio"
    equipment: str | None = None  # barbell, dumbbell, bodyweight or machine; None for cardio
    body: str | None = None  # upper or lower, if the plan says
    sets: int | None = None
    repsMin: int | None = None
    repsMax: int | None = None
    weightKg: float | None = None  # for dumbbells, one dumbbell (plan 4); None for bodyweight and cardio
    incrementKg: float | None = None  # added when you top the rep range: from the plan, else from body (9.1)
    dumbbells: int | None = None  # dumbbell exercises: 1 or 2 dumbbells, for volume (WD1.3)
    platesPerSide: bool = False  # weights are the plates on one side: doubled for volume and 1RM (WD1.3)
    barKg: float | None = None  # the bar's or sled's own weight, added for volume and 1RM (WD1.3)
    compound: bool = False  # a compound lift, watched by the deload trigger (0.2-alpha)
    restSec: int | None = None  # shown on Today, no timer (17.3a)
    notes: str | None = None  # form cues shown on Today (17.3a)
    minutes: int | None = None  # the cardio target
    setup: str | None = None  # how-to (SC7.1): the machine or equipment needed and how to set it up
    howTo: tuple[str, ...] = ()  # how-to: the steps, in order
    form: tuple[str, ...] = ()  # how-to: form cues

    @property
    def isCardio(self) -> bool:
        return self.kind == "cardio"


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One day of the week: a workout with its exercises, or a rest day."""

    title: str
    isRest: bool
    exercises: tuple[PlanExercise, ...]
    makeUp: tuple[int, ...] = ()  # the flex day: the earlier days it makes up, by priority (0 = Monday)


@dataclass(frozen=True, slots=True)
class ExerciseMove:
    """An exercise that moves to another day in a week the flex day makes up one of `when` (WD1.2)."""

    exerciseId: str
    fromDay: int  # 0 = Monday
    toDay: int  # the flex day itself means the end of the session it makes up
    when: tuple[int, ...]
    exercise: PlanExercise  # as the from day has it


@dataclass(frozen=True, slots=True)
class Plan:
    """A checked plan."""

    planId: str
    name: str
    version: int
    weeklyTarget: int  # workouts a week (17.1a)
    steps: tuple[PlanStep, ...]  # the 7 days, Monday first
    moves: tuple[ExerciseMove, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanCheck:
    """The result of checking a plan: the plan if it's valid, otherwise every error; warnings either way."""

    plan: Plan | None
    planJson: Any  # the plan as read from the file, which is what gets stored (plans.planJson, plan 14)
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def readPlanFile(content: bytes | str) -> PlanCheck:
    """Reads a plan file chosen for import and checks it strictly."""
    if len(content) > maxFileBytes:
        return _refused("The file is too big to be a plan file (over 1 MB).")
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return _refused("The file isn't a text file: a plan file is JSON text (UTF-8).")
    content = content.removeprefix("\ufeff")  # the invisible marker some editors put first

    repeatedFields: list[str] = []

    def oneOfEach(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        """Builds each {…} block, noting fields that appear twice (Python would keep the last silently)."""
        block = dict(pairs)
        if len(block) < len(pairs):
            repeatedFields.extend(key for key, count in Counter(key for key, _ in pairs).items() if count > 1)
        return block

    try:
        data = json.loads(content, object_pairs_hook=oneOfEach, parse_constant=_refuseConstant)
    except _SpecialNumber as problem:
        return _refused(f"The plan file uses {problem.args[0]}, which isn't a number a plan can use.")
    except json.JSONDecodeError as problem:
        return _refused(f"The file isn't valid JSON: {problem.msg} (line {problem.lineno}, column {problem.colno}).")
    except RecursionError:
        return _refused("The file is nested too deeply to be a plan file.")

    result = checkPlan(data, strict=True)
    if not repeatedFields:
        return result
    repeats = tuple(f'The plan file has "{key}" twice in one block; each field may appear only once.'
                    for key in dict.fromkeys(repeatedFields))
    return PlanCheck(None, data, repeats + result.errors, result.warnings)


def checkPlan(data: Any, strict: bool = True) -> PlanCheck:
    """Checks a plan read from JSON and lists every problem.

    strict: unknown fields are errors (importing a file). Otherwise they're ignored (a stored plan).
    """
    if not isinstance(data, dict):
        return _refused('The file must hold one plan: a {…} block with "planId", "name", "version", '
                        '"weeklyTarget" and "week".')
    problems = _Problems(strict)
    place = "The plan"
    oldFormat = "cycle" in data and "week" not in data  # said once, in plain words, by _week
    problems.unknownFields(data, planFields + (("cycle",) if oldFormat else ()), place)
    planId = problems.identifier(data, "planId", place)
    name = problems.text(data, "name", place, maxLength=100)
    version = problems.wholeNumber(data, "version", place, 1, 1_000_000)
    weeklyTarget = problems.wholeNumber(data, "weeklyTarget", place, 1, 7)  # F12.1
    steps, moves = _week(data, problems)

    # There's no Train anyway (WD1.1), so a target above the week's workout days can never be met.
    workoutDays = sum(not step.isRest for step in steps)
    if workoutDays and weeklyTarget is not None and weeklyTarget > workoutDays:
        problems.error(f'The plan: "weeklyTarget" ({weeklyTarget}) is more than the week\'s {workoutDays} workout '
                       "days, so it could never be met.")
    if problems.errors:
        return PlanCheck(None, data, tuple(problems.errors), tuple(problems.warnings))
    plan = Plan(planId, name, version, weeklyTarget, tuple(steps), tuple(moves))
    return PlanCheck(plan, data, (), tuple(problems.warnings))


def scheduleDays(plan: Plan) -> tuple[ScheduleDay, ...]:
    """What the schedule rules need from a plan: each day's title, whether it's a rest day, and what the
    flex day makes up."""
    return tuple(ScheduleDay(step.title, step.isRest, step.makeUp) for step in plan.steps)


def planExercises(plan: Plan) -> dict[str, PlanExercise]:
    """The plan's exercises by exerciseId, in the order they first appear in the week."""
    exercises: dict[str, PlanExercise] = {}
    for step in plan.steps:
        for exercise in step.exercises:
            exercises.setdefault(exercise.exerciseId, exercise)
    return exercises


# --- The blocks of a plan -----------------------------------------------------------------------

def _week(data: dict[str, Any], problems: "_Problems") -> tuple[list[PlanStep], list[ExerciseMove]]:
    """Checks the week's 7 days and the flex day's moves. Returns them only if every day is valid; every
    problem goes into `problems`."""
    if "week" not in data:
        if "cycle" in data:
            problems.error('The plan: "cycle" is the old format; plans now run on weekdays. Give "week" with the 7 '
                           "days, Monday to Sunday, instead.")
        else:
            problems.error('The plan: "week" is missing.')
        return [], []
    week = data["week"]
    if not isinstance(week, list) or len(week) != len(weekdayNames):
        has = f"it has {len(week)}" if isinstance(week, list) else f"not {_shown(week)}"
        problems.error(f'The plan: "week" must be a list of the 7 days, Monday to Sunday; {has}.')
        return [], []

    places = [_dayPlace(index, rawDay) for index, rawDay in enumerate(week)]
    checked = [_step(index, rawDay, problems) for index, rawDay in enumerate(week)]
    if all(step is not None and step.isRest for step in checked):
        problems.error("The plan: the week has no workout; every day is a rest day.")
    valid = [(place, step) for place, step in zip(places, checked) if step is not None]
    _sameSettingsEverywhere(valid, problems)
    filledIn = iter(_howToGivenOnce([step for _, step in valid]))
    steps = [next(filledIn) if step is not None else None for step in checked]
    flexIndex, makeUp, moves = _flexDay(week, places, steps, problems)
    if any(step is None for step in steps):
        return [], []
    if flexIndex is not None:
        steps[flexIndex] = dataclasses.replace(steps[flexIndex], makeUp=makeUp)
    return steps, moves


def _step(index: int, rawStep: Any, problems: "_Problems") -> PlanStep | None:
    """Checks one day of the week; None if it has errors. Its "makeUp" and "moves" are checked by _flexDay."""
    place = _dayPlace(index, rawStep)
    if not isinstance(rawStep, dict):
        problems.error(f'{place} must be a {{…}} block with "day" and "title".')
        return None
    errorsBefore = len(problems.errors)
    problems.unknownFields(rawStep, dayFields, place)
    if problems.present(rawStep, "day", place, required=True) and rawStep["day"] != weekdayNames[index]:
        problems.error(f'{place}: "day" must be "{weekdayNames[index]}" (the week runs Monday to Sunday, in order), '
                       f'not {_shown(rawStep["day"])}.')
    title = problems.text(rawStep, "title", place, maxLength=50)
    isRest = problems.flag(rawStep, "restDay", place)

    exercises: list[PlanExercise] = []
    if isRest:
        if rawStep.get("exercises") not in (None, []):
            problems.error(f"{place}: a rest day can't have exercises.")
    elif "exercises" not in rawStep:
        problems.error(f'{place}: "exercises" is missing (for a rest day, add "restDay": true).')
    elif not isinstance(rawStep["exercises"], list) or not rawStep["exercises"]:
        problems.error(f'{place}: "exercises" must be a list with at least one exercise.')
    else:
        for exerciseIndex, rawExercise in enumerate(rawStep["exercises"]):
            exercise = _exercise(f"{place}, exercise {exerciseIndex + 1}", rawExercise, problems)
            if exercise is not None:
                exercises.append(exercise)
        # A day logs each exercise once (one exerciseLogs row per exercise and day, plan 14).
        for exerciseId, count in Counter(exercise.exerciseId for exercise in exercises).items():
            if count > 1:
                problems.error(f'{place}: "{exerciseId}" appears more than once; each exercise can be in a day '
                               "only once.")

    if len(problems.errors) > errorsBefore:
        return None
    return PlanStep(title, isRest, tuple(exercises))


def _exercise(basePlace: str, raw: Any, problems: "_Problems") -> PlanExercise | None:
    """Checks one exercise; None if it has errors."""
    if not isinstance(raw, dict):
        problems.error(f'{basePlace} must be a {{…}} block with an "exerciseId" and a "name".')
        return None
    name = raw.get("name")
    place = f'{basePlace} "{name.strip()}"' if _fitsInAPlace(name, maxLength=100) else basePlace
    errorsBefore = len(problems.errors)
    problems.unknownFields(raw, exerciseFields, place)
    exerciseId = problems.identifier(raw, "exerciseId", place)
    name = problems.text(raw, "name", place, maxLength=100)
    kind = problems.choice(raw, "type", place, exerciseKinds, required=False) or "strength"
    notes = problems.text(raw, "notes", place, maxLength=500, required=False)
    howTo = {"setup": problems.text(raw, "setup", place, maxLength=maxSetupLength, required=False),
             "howTo": problems.lines(raw, "howTo", place, maxHowToLines, maxHowToLineLength),
             "form": problems.lines(raw, "form", place, maxHowToLines, maxHowToLineLength)}
    if "type" in raw and raw["type"] not in exerciseKinds:
        return None  # the kind is unknown, so its other fields can't be checked
    if kind == "cardio":
        details = _cardioDetails(raw, place, problems)
    else:
        details = _strengthDetails(raw, place, problems)
    if len(problems.errors) > errorsBefore:
        return None
    return PlanExercise(exerciseId=exerciseId, name=name, kind=kind, notes=notes, **howTo, **details)


def _cardioDetails(raw: dict[str, Any], place: str, problems: "_Problems") -> dict[str, Any]:
    """A cardio exercise has a minutes target and nothing else besides its name, notes and how-to."""
    allowed = [f'"{key}"' for key in cardioFields if key not in ("exerciseId", "name", "type")]
    for key in raw:
        if key in strengthFields and key not in cardioFields:
            problems.error(f'{place}: "{key}" doesn\'t belong to a cardio exercise; it has only '
                           f'{", ".join(allowed[:-1])} and {allowed[-1]}.')
    return {"minutes": problems.wholeNumber(raw, "minutes", place, 1, 600)}


def _strengthDetails(raw: dict[str, Any], place: str, problems: "_Problems") -> dict[str, Any]:
    """Sets, the rep range and the weight; the increment comes from the plan or from body (9.1)."""
    if "minutes" in raw:
        problems.error(f'{place}: "minutes" is only for cardio exercises (add "type": "cardio").')
    equipment = problems.choice(raw, "equipment", place, equipmentKinds)
    body = problems.choice(raw, "body", place, bodyParts, required=False)
    sets = problems.wholeNumber(raw, "sets", place, 1, 20)
    repsMin = problems.wholeNumber(raw, "repsMin", place, 1, 100)
    repsMax = problems.wholeNumber(raw, "repsMax", place, 1, 100)
    if repsMin is not None and repsMax is not None and repsMin > repsMax:
        problems.error(f'{place}: "repsMin" ({repsMin}) is more than "repsMax" ({repsMax}).')
    restSec = problems.wholeNumber(raw, "restSec", place, 0, 3600, required=False)

    weightKg = incrementKg = None
    if equipment == "bodyweight":
        # Bodyweight exercises progress in reps only, with no weight suggestions (10.9a).
        if "weightKg" in raw:
            problems.error(f'{place}: a bodyweight exercise has no "weightKg"; its progress is counted in reps.')
        if "incrementKg" in raw:
            problems.warn(f'{place}: "incrementKg" is ignored, because a bodyweight exercise progresses in reps.')
    elif equipment is not None:
        weightKg = problems.kilograms(raw, "weightKg", place, 0, 1000)
        if "incrementKg" in raw:
            incrementKg = problems.kilograms(raw, "incrementKg", place, 0.01, 100)
        elif body is not None:
            incrementKg = defaultIncrementKg[body]
        elif "body" not in raw:
            problems.error(f'{place}: needs "body" ("upper" or "lower") or "incrementKg", to know how much weight '
                           "to add.")
    return {"equipment": equipment, "body": body, "sets": sets, "repsMin": repsMin, "repsMax": repsMax,
            "weightKg": weightKg, "incrementKg": incrementKg, "restSec": restSec,
            **_loadDetails(raw, equipment, place, problems)}


def _loadDetails(raw: dict[str, Any], equipment: str | None, place: str, problems: "_Problems") -> dict[str, Any]:
    """How volume and estimated 1RM count the weight (WD1.3): the number of dumbbells, or plates logged per
    side plus the bar's or sled's weight. And whether it's a compound lift (the deload trigger's)."""
    details: dict[str, Any] = {"compound": problems.flag(raw, "compound", place)}
    if equipment is None:
        return details  # its error is listed already; the rest can't be judged
    if equipment == "dumbbell":
        if "dumbbells" not in raw:
            problems.error(f'{place}: "dumbbells" is missing: 2 for one in each hand, 1 for a single dumbbell.')
        else:
            details["dumbbells"] = problems.wholeNumber(raw, "dumbbells", place, 1, 2)
    elif "dumbbells" in raw:
        problems.error(f'{place}: "dumbbells" is only for dumbbell exercises.')
    if equipment in plateLoaded:
        details["platesPerSide"] = problems.flag(raw, "platesPerSide", place)
        if "barKg" in raw:
            details["barKg"] = problems.kilograms(raw, "barKg", place, 0, 1000)
    else:
        for key in ("platesPerSide", "barKg"):
            if key in raw:
                problems.error(f'{place}: "{key}" is only for barbell and plate-loaded machine exercises.')
    return details


def _flexDay(week: list[Any], places: list[str], steps: list[PlanStep | None],
             problems: "_Problems") -> tuple[int | None, tuple[int, ...], list[ExerciseMove]]:
    """The flex day (WD1.1): the earlier days it makes up, by priority, and the exercises that move when it
    makes up certain days (WD1.2). At most one day has "makeUp", and "moves" goes only with it.

    Returns the flex day (or None), its makeUp and the moves; anything wrong goes into `problems`.
    """
    blocks = [rawDay if isinstance(rawDay, dict) else {} for rawDay in week]
    for place, block in zip(places, blocks):
        if "moves" in block and "makeUp" not in block:
            problems.error(f'{place}: "moves" only goes with "makeUp", on the flex day.')
    flexDays = [index for index, block in enumerate(blocks) if "makeUp" in block]
    if len(flexDays) > 1:
        problems.error(f'The plan: only one day can make up missed days, but {_inWords([places[i] for i in flexDays])} '
                       'all have "makeUp".')
    if len(flexDays) != 1:
        return None, (), []
    flex = flexDays[0]
    block, place, flexName = blocks[flex], places[flex], weekdayNames[flex]
    if block.get("restDay") is True:
        problems.error(f'{place}: a rest day can\'t make up missed days; give it exercises (its bonus workout) or '
                       'leave "makeUp" out.')
        return None, (), []

    makeUp = problems.days(block, "makeUp", place)
    if makeUp is None:
        return None, (), []  # the moves depend on it, so they're checked once it's right
    for index in makeUp:
        if index >= flex:
            problems.error(f'{place}: "makeUp" can only list days before {flexName}, not "{weekdayNames[index]}".')
        elif steps[index] is not None and steps[index].isRest:
            problems.error(f'{place}: "makeUp" lists "{weekdayNames[index]}", which is a rest day.')

    rawMoves = block.get("moves", [])
    if not isinstance(rawMoves, list):
        problems.error(f'{place}: "moves" must be a list of moves, like [{{"exerciseId": "…", "from": "friday", '
                       f'"to": "{flexName}", "when": ["monday"]}}].')
        rawMoves = []
    moves: list[ExerciseMove] = []
    movedAlready: set[tuple[str, int, int]] = set()
    for number, rawMove in enumerate(rawMoves, start=1):
        move = _move(f"{place}, move {number}", rawMove, flex, makeUp, places, steps, movedAlready, problems)
        if move is not None:
            moves.append(move)
    return flex, makeUp, moves


def _move(place: str, raw: Any, flex: int, makeUp: tuple[int, ...], places: list[str],
          steps: list[PlanStep | None], movedAlready: set[tuple[str, int, int]],
          problems: "_Problems") -> ExerciseMove | None:
    """Checks one of the flex day's moves; None if it has errors."""
    if not isinstance(raw, dict):
        problems.error(f'{place} must be a {{…}} block with "exerciseId", "from", "to" and "when".')
        return None
    errorsBefore = len(problems.errors)
    problems.unknownFields(raw, moveFields, place)
    exerciseId = problems.identifier(raw, "exerciseId", place)
    fromDay, toDay = problems.day(raw, "from", place), problems.day(raw, "to", place)
    when = problems.days(raw, "when", place)
    if len(problems.errors) > errorsBefore:
        return None

    if fromDay == flex:
        problems.error(f'{place}: "from" can\'t be the flex day itself; its own exercises are only its bonus workout.')
    elif fromDay == toDay:
        problems.error(f'{place}: "from" and "to" are the same day.')
    for key, index in (("from", fromDay), ("to", toDay)):
        if steps[index] is not None and steps[index].isRest:
            problems.error(f'{place}: "{key}" is {weekdayNames[index]}, a rest day.')
    for index in when:
        if index not in makeUp:
            problems.error(f'{place}: "when" lists "{weekdayNames[index]}", which "makeUp" doesn\'t.')
    if len(problems.errors) > errorsBefore or steps[fromDay] is None:
        return None  # a day with errors of its own is listed already

    exercise = next((e for e in steps[fromDay].exercises if e.exerciseId == exerciseId), None)
    if exercise is None:
        problems.error(f'{place}: "{exerciseId}" isn\'t in {places[fromDay]}.')
        return None
    # Moved to the flex day, it joins the end of the session made up; otherwise the end of its "to" day.
    for target in (when if toDay == flex else (toDay,)):
        if steps[target] is not None and any(e.exerciseId == exerciseId for e in steps[target].exercises):
            madeUp = f", which {weekdayNames[flex].capitalize()} makes up" if toDay == flex else ""
            problems.error(f'{place}: "{exerciseId}" is already in {places[target]}{madeUp}; an exercise can be in a '
                           "workout only once.")
    for index in when:
        if (exerciseId, fromDay, index) in movedAlready:
            problems.error(f'{place}: "{exerciseId}" already moves from {weekdayNames[fromDay]} when '
                           f"{weekdayNames[flex]} makes up {weekdayNames[index]}.")
        movedAlready.add((exerciseId, fromDay, index))
    if len(problems.errors) > errorsBefore:
        return None
    return ExerciseMove(exerciseId, fromDay, toDay, when, exercise)


def _sameSettingsEverywhere(placedSteps: list[tuple[str, PlanStep]], problems: "_Problems") -> None:
    """An exercise on several days needs the same settings on each, since progress is tracked per
    exercise (7). Notes, rest time and the number of sets may differ."""
    firstSeen: dict[str, tuple[str, PlanExercise]] = {}
    for place, step in placedSteps:
        for exercise in step.exercises:
            if exercise.exerciseId not in firstSeen:
                firstSeen[exercise.exerciseId] = (place, exercise)
                continue
            firstPlace, first = firstSeen[exercise.exerciseId]
            differences = [
                f"{fieldNames.get(field, field)} {_setting(getattr(first, field))} vs "
                f"{_setting(getattr(exercise, field))}"
                for field in sameEverywhere if getattr(first, field) != getattr(exercise, field)
            ]
            if differences:
                problems.error(f'"{exercise.exerciseId}" is on {firstPlace} and {place} with different settings '
                               f"({', '.join(differences)}). Give it the same settings on both, or a different "
                               "exerciseId on one.")


def _howToGivenOnce(steps: list[PlanStep]) -> list[PlanStep]:
    """The how-to belongs to the exercise, so the plan gives it once (SC7.1): a day that leaves a how-to
    field out shows the one from the first day that gives it. A day's own always wins."""
    given: dict[str, dict[str, Any]] = {}
    for step in steps:
        for exercise in step.exercises:
            fields = given.setdefault(exercise.exerciseId, {})
            for field in howToFields:
                if getattr(exercise, field) and field not in fields:
                    fields[field] = getattr(exercise, field)

    def filledIn(exercise: PlanExercise) -> PlanExercise:
        missing = {field: value for field, value in given[exercise.exerciseId].items()
                   if not getattr(exercise, field)}
        return dataclasses.replace(exercise, **missing) if missing else exercise

    return [dataclasses.replace(step, exercises=tuple(filledIn(exercise) for exercise in step.exercises))
            for step in steps]


# --- Checking single fields ---------------------------------------------------------------------

class _Problems:
    """Collects a plan's errors (it's refused) and warnings (it's imported anyway), and checks fields.

    Each field check returns the field's value if it's valid, else None after noting the error.
    """

    def __init__(self, strict: bool):
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def unknownFields(self, block: dict[str, Any], allowed: tuple[str, ...], place: str) -> None:
        """Strict only: a field the format doesn't have is an error, with the closest real one as a hint."""
        if not self.strict:
            return
        for key in block:
            if key not in allowed:
                closest = difflib.get_close_matches(key, allowed, n=1)
                hint = f' (did you mean "{closest[0]}"?)' if closest else ""
                self.error(f'{place}: unknown field "{key}"{hint}.')

    def present(self, block: dict[str, Any], key: str, place: str, required: bool) -> bool:
        """Whether the block has the field; a missing required one is an error."""
        if key in block:
            return True
        if required:
            self.error(f'{place}: "{key}" is missing.')
        return False

    def wholeNumber(self, block, key, place, low: int, high: int, required: bool = True) -> int | None:
        if not self.present(block, key, place, required):
            return None
        value = block[key]
        if isinstance(value, bool) or not isinstance(value, int):  # JSON true would pass as 1
            self.error(f'{place}: "{key}" must be a whole number, not {_shown(value)}.')
            return None
        if not low <= value <= high:
            self.error(f'{place}: "{key}" must be between {low} and {high}, not {value}.')
            return None
        return value

    def kilograms(self, block, key, place, low: float, high: float, required: bool = True) -> float | None:
        """A weight in kg with at most 2 decimals, as the cloud stores it (numeric(6, 2))."""
        if not self.present(block, key, place, required):
            return None
        value = block[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.error(f'{place}: "{key}" must be a number, not {_shown(value)}.')
            return None
        if not low <= value <= high:
            self.error(f'{place}: "{key}" must be between {_number(low)} and {_number(high)}, not {_number(value)}.')
            return None
        if abs(value * 100 - round(value * 100)) > 1e-6:
            self.error(f'{place}: "{key}" can have at most 2 decimals, not {_number(value)}.')
            return None
        return round(float(value), 2)

    def text(self, block, key, place, maxLength: int, required: bool = True) -> str | None:
        """Text on one line, trimmed; empty optional text counts as not given."""
        if not self.present(block, key, place, required):
            return None
        return self._oneLine(block[key], f'"{key}"', place, maxLength, required)

    def lines(self, block, key, place, maxLines: int, maxLength: int) -> tuple[str, ...]:
        """An optional list of one-line texts, like a how-to's steps; an empty list counts as not given.
        Every line must have something in it."""
        if not self.present(block, key, place, required=False):
            return ()
        value = block[key]
        if not isinstance(value, list):
            self.error(f'{place}: "{key}" must be a list of lines, like ["First step", "Second step"], not '
                       f"{_shown(value)}.")
            return ()
        if len(value) > maxLines:
            self.error(f'{place}: "{key}" has {len(value)} lines; at most {maxLines} are allowed.')
            return ()
        checked = [self._oneLine(line, f'"{key}" line {number}', place, maxLength, required=True)
                   for number, line in enumerate(value, start=1)]
        return () if None in checked else tuple(checked)

    def _oneLine(self, value, what: str, place, maxLength: int, required: bool) -> str | None:
        """Checks one text (`what` names it in errors, like "notes" or "howTo" line 2), trimmed."""
        if not isinstance(value, str):
            self.error(f"{place}: {what} must be text, not {_shown(value)}.")
            return None
        value = value.strip()
        if not value:
            if required:
                self.error(f"{place}: {what} is empty.")
            return None
        if len(value) > maxLength:
            self.error(f"{place}: {what} is longer than {maxLength} characters.")
            return None
        if _hasControlCharacters(value):
            self.error(f"{place}: {what} can't have line breaks or other control characters.")
            return None
        return value

    def identifier(self, block, key, place) -> str | None:
        """A camelCase ID such as an exerciseId (11.4c)."""
        if not self.present(block, key, place, required=True):
            return None
        value = block[key]
        if not isinstance(value, str) or not idPattern.fullmatch(value):
            self.error(f'{place}: "{key}" must be camelCase letters and digits starting with a small letter, like '
                       f'"benchPress", not {_shown(value)}.')
            return None
        return value

    def choice(self, block, key, place, options: tuple[str, ...], required: bool = True) -> str | None:
        if not self.present(block, key, place, required):
            return None
        value = block[key]
        if not isinstance(value, str) or value not in options:
            quoted = [f'"{option}"' for option in options]
            self.error(f'{place}: "{key}" must be {", ".join(quoted[:-1])} or {quoted[-1]}, not {_shown(value)}.')
            return None
        return value

    def flag(self, block, key, place) -> bool:
        """true or false; a missing flag is false."""
        if key not in block:
            return False
        value = block[key]
        if not isinstance(value, bool):
            self.error(f'{place}: "{key}" must be true or false, not {_shown(value)}.')
            return False
        return value

    def day(self, block, key, place) -> int | None:
        """A required day of the week, like "friday", as its index (0 = Monday)."""
        if not self.present(block, key, place, required=True):
            return None
        value = block[key]
        if value not in weekdayNames:
            self.error(f'{place}: "{key}" must be a day, "monday" to "sunday", not {_shown(value)}.')
            return None
        return weekdayNames.index(value)

    def days(self, block, key, place) -> tuple[int, ...] | None:
        """A required list of days, in an order that matters, each once: ["monday", "thursday"]."""
        if not self.present(block, key, place, required=True):
            return None
        value = block[key]
        if not isinstance(value, list) or not value:
            self.error(f'{place}: "{key}" must be a list of days, like ["monday", "thursday"], not {_shown(value)}.')
            return None
        errorsBefore = len(self.errors)
        for name in value:
            if name not in weekdayNames:
                self.error(f'{place}: "{key}" has {_shown(name)}, which isn\'t a day; days are "monday" to "sunday".')
        for name, count in Counter(name for name in value if name in weekdayNames).items():
            if count > 1:
                self.error(f'{place}: "{key}" has "{name}" more than once.')
        if len(self.errors) > errorsBefore:
            return None
        return tuple(weekdayNames.index(name) for name in value)


class _SpecialNumber(ValueError):
    """The file uses NaN or Infinity, which Python's JSON reader would otherwise accept."""


def _refuseConstant(name: str) -> Any:
    raise _SpecialNumber(name)


def _refused(*errors: str) -> PlanCheck:
    return PlanCheck(None, None, errors, ())


def _dayPlace(index: int, rawDay: Any) -> str:
    """How errors name a day, by its place in the week: Thursday "Pull", or just Thursday if its title is
    unusable."""
    weekday = weekdayNames[index].capitalize()
    title = rawDay.get("title") if isinstance(rawDay, dict) else None
    return f'{weekday} "{title.strip()}"' if _fitsInAPlace(title, maxLength=50) else weekday


def _fitsInAPlace(value: Any, maxLength: int) -> bool:
    """Whether a title or name is valid text, so errors can use it to say where they are."""
    return (isinstance(value, str) and 0 < len(value.strip()) <= maxLength
            and not _hasControlCharacters(value.strip()))


def _hasControlCharacters(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _shown(value: Any) -> str:
    """A value as it looks in the file, cut short if it's long."""
    shown = json.dumps(value, ensure_ascii=False)
    return shown if len(shown) <= 40 else shown[:39] + "…"


def _setting(value: Any) -> str:
    """A setting in a "different settings" error."""
    if value is None:
        return "not set"
    if isinstance(value, bool):
        return json.dumps(value)  # true or false, as the file has it
    if isinstance(value, str):
        return f'"{value}"'
    return _number(value)


def _number(value: float) -> str:
    """82.5 as 82.5 and 80.0 as 80."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _inWords(items: list[str]) -> str:
    """["a", "b", "c"] as "a, b and c"."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
