"""Importing a plan file, step by step (plan 4 and 10, SC6.1): pick the file → problems listed in plain
words (G8a) → "is this the same exercise?" for likely matches (11.3) → the week at a glance and Import
→ it takes effect (PF1). Used by the PC view's Plans tab and the phone's file import fallback. There's
no starting step to choose: today's weekday decides the session (WD1.1).

Each step returns a new PlanImport describing what to show next; nothing is saved until the last one,
which builds the plans row.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from gym.rules.planFile import Plan, PlanCheck, PlanExercise, checkPlan, readPlanFile
from gym.rules.planImport import SameExerciseQuestion, effectiveDate, keptWeights, renameExercises, sameExerciseQuestions
from gym.rules.progression import Training
from usefulShared.tables import newRowId


@dataclass(frozen=True, slots=True)
class PlanImport:
    """Where an import is up to, and what the screen shows for it."""

    step: str  # "problems" (refused, errors listed), "questions" or "ready"
    fileName: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    questions: tuple[SameExerciseQuestion, ...] = ()
    planJson: Any = None  # the file as read, with matched IDs once the questions are answered
    plan: Plan | None = None
    takesEffect: dt.date | None = None
    keptWeights: tuple[str, ...] = ()  # plan weights it won't use: you've trained those already (WD3.9)


def startImport(fileName: str, content: bytes, known: Mapping[str, PlanExercise], today: dt.date,
                workoutLoggedToday: bool, training: Training | None = None) -> PlanImport:
    """Reads and checks the picked file; asks about likely matches if there are any."""
    check = readPlanFile(content)
    if check.plan is None:
        return PlanImport("problems", fileName, check.errors, check.warnings)
    questions = sameExerciseQuestions(check.plan, known)
    return PlanImport("questions" if questions else "ready", fileName, (), check.warnings, tuple(questions),
                      check.planJson, check.plan, effectiveDate(today, workoutLoggedToday),
                      keptWeights(check.plan, training) if training and not questions else ())


def answerQuestions(flow: PlanImport, sameAs: Sequence[bool], training: Training | None = None) -> PlanImport:
    """Your answers, one per question: True = the same exercise, so it keeps the known ID and its history."""
    if len(sameAs) != len(flow.questions):
        raise ValueError("one answer per question")
    renames = {question.newId: question.knownId for question, same in zip(flow.questions, sameAs) if same}
    planJson = renameExercises(flow.planJson, renames)
    check: PlanCheck = checkPlan(planJson)
    if check.plan is None:  # matched IDs can clash, say two settings for one exercise
        return replace(flow, step="problems", errors=check.errors)
    return replace(flow, step="ready", planJson=planJson, plan=check.plan,
                   keptWeights=keptWeights(check.plan, training) if training else ())


def finishImport(flow: PlanImport, userId: str, now: dt.datetime) -> dict[str, Any]:
    """The plans row for the import (random ID): the plan as read with matched IDs and the day it takes
    effect. The store stamps the edit time. startStep is always 0: the column stays (cloud upgrades only add,
    UP1.1), but the week has no starting step (WD1.1)."""
    if flow.step != "ready" or flow.plan is None or flow.takesEffect is None:
        raise ValueError("the import isn't ready to finish")
    return {"id": newRowId(), "userId": userId, "deleted": False, "importedAt": now,
            "effectiveDate": flow.takesEffect, "startStep": 0, "planJson": flow.planJson, "archived": False}
