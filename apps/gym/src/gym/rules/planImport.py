"""Plan import steps (plan 4 and 10): which of your earlier exercises a new plan's exercises are
probably the same as (11.3), applying your answers, and when a new plan takes effect.

Pure logic: no screen, database, network or clock; "today" is passed in. The exercise list isn't
stored anywhere: it's every exercise of every plan imported so far (plan 14).
"""

import copy
import datetime as dt
import difflib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from gym.rules.planFile import Plan, PlanExercise, placeholderKg, planExercises
from gym.rules.progression import Training
from gym.rules.schedule import weekdayNames
from gym.rules.stats import kgText, unit

likenessNeeded = 0.8  # how alike two names must be (0 to 1) to ask whether they're the same exercise
containedLikeness = 0.9  # one name inside the other, like "Bench Press" in "Barbell Bench Press" ...
minContainedLength = 4  # ... counts if the shorter name has at least this many letters and digits


@dataclass(frozen=True, slots=True)
class SameExerciseQuestion:
    """Is the new plan's exercise the same as one from your earlier plans? Yes carries its history on."""

    newId: str
    newName: str
    knownId: str
    knownName: str


def knownExercises(imports: Iterable[tuple[dt.datetime, Plan]]) -> dict[str, PlanExercise]:
    """Every exercise of the plans imported so far (importedAt, plan), as the latest import has it."""
    known: dict[str, PlanExercise] = {}
    for _, plan in sorted(imports, key=lambda item: item[0]):
        known.update(planExercises(plan))
    return known


def sameExerciseQuestions(plan: Plan, known: Mapping[str, PlanExercise]) -> list[SameExerciseQuestion]:
    """What to ask about a new plan's exercises before importing it (11.3), in the plan's order.

    An exercise whose exerciseId is already known is that exercise, so nothing is asked. For a new
    ID, a known exercise is a likely match if it's the same kind with the same equipment, its ID
    isn't used in the new plan, and the names are alike. Each new and each known exercise is asked
    about at most once, best match first.
    """
    newExercises = planExercises(plan)
    candidates = []
    for new in newExercises.values():
        if new.exerciseId in known:
            continue
        for old in known.values():
            if old.exerciseId in newExercises or (old.kind, old.equipment) != (new.kind, new.equipment):
                continue
            likeness = nameLikeness(new.name, old.name)
            if likeness >= likenessNeeded:
                candidates.append((likeness, new, old))

    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1].exerciseId, candidate[2].exerciseId))
    questions: dict[str, SameExerciseQuestion] = {}
    knownAskedAbout: set[str] = set()
    for _, new, old in candidates:
        if new.exerciseId in questions or old.exerciseId in knownAskedAbout:
            continue
        questions[new.exerciseId] = SameExerciseQuestion(new.exerciseId, new.name, old.exerciseId, old.name)
        knownAskedAbout.add(old.exerciseId)
    return [questions[exerciseId] for exerciseId in newExercises if exerciseId in questions]


def nameLikeness(first: str, second: str) -> float:
    """How alike two exercise names are, from 0 to 1, ignoring case, spaces and punctuation."""
    first, second = _simplified(first), _simplified(second)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= minContainedLength and shorter in longer:
        return containedLikeness
    return difflib.SequenceMatcher(None, first, second).ratio()


def renameExercises(planJson: Mapping[str, Any], sameAs: Mapping[str, str]) -> dict[str, Any]:
    """The plan with each exercise you said is the same as a known one given that one's ID, so its
    history carries on (plans.planJson stores the matched IDs, plan 14). Check the result again."""
    renamed = copy.deepcopy(dict(planJson))
    for step in renamed.get("week", []):
        if not isinstance(step, dict):
            continue
        for exercise in step.get("exercises") or []:
            if isinstance(exercise, dict) and exercise.get("exerciseId") in sameAs:
                exercise["exerciseId"] = sameAs[exercise["exerciseId"]]
    return renamed


def keptWeights(plan: Plan, training: Training) -> tuple[str, ...]:
    """The plan weights an import won't use (WD3.9): exercises you've trained or set a weight for keep
    theirs on each day, so where the plan says otherwise, the import says so. "Bench Press (Mon): keeps
    82.5 kg, not the plan's 80 kg". The 1 kg placeholder your plans give every weight isn't listed (PF5)."""
    kept = []
    for weekday, step in enumerate(plan.steps):
        for exercise in step.exercises:
            if exercise.isCardio or exercise.equipment == "bodyweight" or exercise.weightKg in (None, placeholderKg):
                continue  # no weight to keep, or only the 1 kg placeholder (PF5)
            weightKg = training.target(exercise, weekday, now=True).weightKg
            if weightKg is not None and abs(weightKg - exercise.weightKg) > 0.001:
                kept.append(f"{exercise.name} ({weekdayNames[weekday][:3].capitalize()}): keeps {kgText(weightKg)} "
                            f"{unit(exercise)}, not the plan's {kgText(exercise.weightKg)} {unit(exercise)}")
    return tuple(kept)


def effectiveDate(today: dt.date, workoutLoggedToday: bool) -> dt.date:
    """When a new plan takes effect: today, or tomorrow if a workout is already logged today, so one
    day's workout never mixes two plans."""
    return today + dt.timedelta(days=1) if workoutLoggedToday else today


def _simplified(name: str) -> str:
    """A name in lower case with only its letters and digits: "Bench-Press" -> "benchpress"."""
    return "".join(character for character in name.casefold() if character.isalnum())
