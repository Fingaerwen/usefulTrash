"""Importing a plan file, step by step (plan 4 and 10, SC6.1): pick the file → problems listed in plain
words (G8a) → "is this the same exercise?" for likely matches (11.3) → choose the starting step
(17.2c) → it takes effect (PF1). Used by the PC view's Plans tab and the phone's file import fallback.

Each step returns a new PlanImport describing what to show next; nothing is saved until the last one,
which builds the plans row.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from gym.rules.planFile import Plan, PlanCheck, PlanExercise, checkPlan, readPlanFile
from gym.rules.planImport import SameExerciseQuestion, effectiveDate, renameExercises, sameExerciseQuestions
from usefulShared.tables import newRowId


@dataclass(frozen=True, slots=True)
class PlanImport:
    """Where an import is up to, and what the screen shows for it."""

    step: str  # "problems" (refused, errors listed), "questions", "startStep" or "done"
    fileName: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    questions: tuple[SameExerciseQuestion, ...] = ()
    planJson: Any = None  # the file as read, with matched IDs once the questions are answered
    plan: Plan | None = None
    stepTitles: tuple[str, ...] = ()  # for "choose the starting step"
    takesEffect: dt.date | None = None


def startImport(fileName: str, content: bytes, known: Mapping[str, PlanExercise], today: dt.date,
                workoutLoggedToday: bool) -> PlanImport:
    """Reads and checks the picked file; asks about likely matches if there are any."""
    check = readPlanFile(content)
    if check.plan is None:
        return PlanImport("problems", fileName, check.errors, check.warnings)
    questions = sameExerciseQuestions(check.plan, known)
    return PlanImport("questions" if questions else "startStep", fileName, (), check.warnings, tuple(questions),
                      check.planJson, check.plan, tuple(step.title for step in check.plan.steps),
                      effectiveDate(today, workoutLoggedToday))


def answerQuestions(flow: PlanImport, sameAs: Sequence[bool]) -> PlanImport:
    """Your answers, one per question: True = the same exercise, so it keeps the known ID and its history."""
    if len(sameAs) != len(flow.questions):
        raise ValueError("one answer per question")
    renames = {question.newId: question.knownId for question, same in zip(flow.questions, sameAs) if same}
    planJson = renameExercises(flow.planJson, renames)
    check: PlanCheck = checkPlan(planJson)
    if check.plan is None:  # matched IDs can clash, say two settings for one exercise
        return replace(flow, step="problems", errors=check.errors)
    return replace(flow, step="startStep", planJson=planJson, plan=check.plan)


def finishImport(flow: PlanImport, startStep: int, userId: str, now: dt.datetime) -> dict[str, Any]:
    """The plans row for the import (random ID): the plan as read with matched IDs, the starting step
    you chose and the day it takes effect. The store stamps the edit time."""
    if flow.step != "startStep" or flow.plan is None or flow.takesEffect is None:
        raise ValueError("the import isn't ready to finish")
    if not 0 <= startStep < len(flow.plan.steps):
        raise ValueError("the starting step must be one of the plan's steps")
    return {"id": newRowId(), "userId": userId, "deleted": False, "importedAt": now,
            "effectiveDate": flow.takesEffect, "startStep": startStep, "planJson": flow.planJson, "archived": False}
