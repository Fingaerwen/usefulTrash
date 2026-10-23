"""Tests for the plan import steps (plan 4 and 10): matching exercises to earlier ones (11.3) and when a
new plan takes effect. Written before the code."""

import datetime as dt

from gym.rules.planFile import Plan, checkPlan, planExercises
from gym.rules.planImport import (
    SameExerciseQuestion,
    effectiveDate,
    knownExercises,
    nameLikeness,
    renameExercises,
    sameExerciseQuestions,
)


def barbell(exerciseId: str, name: str, **settings) -> dict:
    """A barbell exercise for a plan file."""
    return {"exerciseId": exerciseId, "name": name, "equipment": "barbell", "body": "upper",
            "sets": 3, "repsMin": 8, "repsMax": 12, "weightKg": 60, **settings}


def planFile(*exercises: dict) -> dict:
    """A plan file with one workout on Monday holding the given exercises, and rest the other days."""
    week = [{"day": "monday", "title": "Workout", "exercises": list(exercises)}]
    week += [{"day": name, "title": "Rest", "restDay": True}
             for name in ("tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")]
    return {"planId": "test", "name": "Test", "version": 1, "weeklyTarget": 1, "week": week}


def checked(*exercises: dict) -> Plan:
    result = checkPlan(planFile(*exercises))
    assert result.errors == ()
    return result.plan


def known(*exercises: dict):
    """The known exercises if one earlier plan held these."""
    return planExercises(checked(*exercises))


# --- Is it the same exercise? (11.3) ------------------------------------------------------------

def testSameIdNeedsNoQuestion():
    """Matching is by exerciseId first, so an exercise with a known ID is never asked about, even if
    its name also looks like another known exercise."""
    new = checked(barbell("benchPress", "Bench Press"))
    earlier = known(barbell("benchPress", "Bench Press"), barbell("flatBench", "Flat Bench Press"))
    assert sameExerciseQuestions(new, earlier) == []


def testNewIdWithTheSameNameIsAsked():
    new = checked(barbell("flatBench", "bench press"))
    assert sameExerciseQuestions(new, known(barbell("benchPress", "Bench Press"))) == [
        SameExerciseQuestion(newId="flatBench", newName="bench press", knownId="benchPress", knownName="Bench Press")]


def testCloseOrLongerNameIsAsked():
    earlier = known(barbell("benchPress", "Bench Press"))
    for name in ("Barbell Bench Press", "Bench Pres", "Bench-Press"):
        (question,) = sameExerciseQuestions(checked(barbell("other", name)), earlier)
        assert question.knownId == "benchPress"


def testUnrelatedNameIsNotAsked():
    earlier = known(barbell("benchPress", "Bench Press"), barbell("row", "Row"))
    assert sameExerciseQuestions(checked(barbell("squat", "Squat"), barbell("uprightRow", "Upright Row")),
                                 earlier) == []


def testDifferentEquipmentOrKindIsNotAsked():
    """One dumbbell's weight isn't a barbell's, so their histories can't be joined."""
    earlier = known(barbell("benchPress", "Bench Press"),
                    {"exerciseId": "walk", "name": "Walk", "type": "cardio", "minutes": 10})
    new = checked(barbell("dumbbellBench", "Bench Press", equipment="dumbbell", dumbbells=2),
                  barbell("walking", "Walk"))
    assert sameExerciseQuestions(new, earlier) == []


def testKnownIdStillInTheNewPlanIsNotOffered():
    """The new plan has benchPress itself, so its incline variant can't be the same exercise."""
    new = checked(barbell("benchPress", "Bench Press"), barbell("inclineBench", "Bench Press Incline"))
    assert sameExerciseQuestions(new, known(barbell("benchPress", "Bench Press"))) == []


def testBestMatchIsAskedFirstAndEachExerciseOnlyOnce():
    """"Bench Press" is like both known exercises, but the exact name wins, which leaves "Incline
    Bench Press" for "Incline Bench". Questions come in the new plan's order."""
    earlier = known(barbell("inclineBench", "Incline Bench Press"), barbell("benchPress", "Bench Press"))
    new = checked(barbell("flatBench", "Bench Press"), barbell("incline", "Incline Bench"))
    assert [(q.newId, q.knownId) for q in sameExerciseQuestions(new, earlier)] == [
        ("flatBench", "benchPress"), ("incline", "inclineBench")]
    new = checked(barbell("incline", "Incline Bench"), barbell("flatBench", "Bench Press"))
    assert [(q.newId, q.knownId) for q in sameExerciseQuestions(new, earlier)] == [
        ("incline", "inclineBench"), ("flatBench", "benchPress")]


def testAKnownExerciseIsOfferedOnlyOnce():
    """Two new exercises can't both carry on the same history."""
    new = checked(barbell("flatBench", "Bench Press"), barbell("pausedBench", "Paused Bench Press"))
    assert [(q.newId, q.knownId) for q in sameExerciseQuestions(new, known(barbell("benchPress", "Bench Press")))] == [
        ("flatBench", "benchPress")]


def testNameLikeness():
    assert nameLikeness("Bench Press", "bench-press") == 1.0
    assert nameLikeness("Bench Press", "Barbell Bench Press") == 0.9
    assert nameLikeness("Row", "Upright Row") < 0.8  # a short name inside a longer one isn't enough
    assert nameLikeness("", "Squat") == 0.0


def testYesKeepsTheKnownId():
    """plans.planJson stores the matched IDs (plan 14); the file as read is left alone."""
    data = planFile(barbell("flatBench", "Bench Press"), barbell("row", "Row"))
    renamed = renameExercises(data, {"flatBench": "benchPress"})
    assert [exercise["exerciseId"] for exercise in renamed["week"][0]["exercises"]] == ["benchPress", "row"]
    assert data["week"][0]["exercises"][0]["exerciseId"] == "flatBench"
    assert checkPlan(renamed).errors == ()


def testKnownExercisesTakeTheLatestImport():
    """New plan weights win (8.12); exercises only in older plans stay known (Past exercises)."""
    older = checked(barbell("benchPress", "Bench Press", weightKg=60), barbell("row", "Row"))
    newer = checked(barbell("benchPress", "Bench Press", weightKg=70))
    first = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
    second = dt.datetime(2026, 10, 6, tzinfo=dt.UTC)
    exercises = knownExercises([(second, newer), (first, older)])
    assert exercises["benchPress"].weightKg == 70
    assert exercises["row"].name == "Row"


# --- When it takes effect -----------------------------------------------------------------------

def testNewPlanTakesEffectTodayOrTomorrow():
    """Tomorrow if a workout is already logged today, so one day's workout never mixes two plans."""
    today = dt.date(2026, 10, 14)
    assert effectiveDate(today, workoutLoggedToday=False) == today
    assert effectiveDate(today, workoutLoggedToday=True) == dt.date(2026, 10, 15)
