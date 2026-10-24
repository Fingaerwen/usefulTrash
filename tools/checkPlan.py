"""Checks a plan file the way the app's import does, and shows the week as the app will run it (plan 4, PF1).

PC-only, never shipped: for a plan from your Claude project, before importing it. It prints the problems
the import would list (the same plain words, from gym/rules/planFile.py), then each day with its exercises,
the flex day's make-up order, and what each move does to the week (gym/rules/sessions.py, as Today shows it).

Usage (from the repo root): .venv/bin/python tools/checkPlan.py <plan.json>
Exit code: 0 if the app would import it, 1 if it would refuse it, 2 for a wrong command line.
"""

import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repoRoot / "apps/gym/src"), str(repoRoot / "shared/src")]

from gym.rules.planFile import Plan, PlanExercise, readPlanFile  # noqa: E402
from gym.rules.schedule import weekdayNames  # noqa: E402
from gym.rules.sessions import sessionExercises  # noqa: E402
from gym.rules.stats import kgText, unit  # noqa: E402


def dayName(index: int) -> str:
    return weekdayNames[index].capitalize()


def exerciseText(exercise: PlanExercise) -> str:
    """"Bench Press  3×6–10 @ 25 kg/side, step 1.25, compound" or "Incline Walk  15 min"."""
    if exercise.isCardio:
        return f"{exercise.name}  {exercise.minutes} min"
    text = f"{exercise.name}  {exercise.sets}×{exercise.repsMin}–{exercise.repsMax}"
    if exercise.equipment == "bodyweight":
        text += " (bodyweight)"
    else:
        dumbbells = f", {exercise.dumbbells} dumbbell{'s' if exercise.dumbbells == 2 else ''}" if exercise.dumbbells else ""
        bar = f", bar {kgText(exercise.barKg)} kg" if exercise.barKg else ""
        text += (f" @ {kgText(exercise.weightKg)} {unit(exercise)}, step {kgText(exercise.incrementKg)}"
                 f"{dumbbells}{bar}")
    return text + (", compound" if exercise.compound else "")


def weekLines(plan: Plan) -> list[str]:
    """The week as the app runs it: each day, then each make-up with the moves it brings."""
    lines = [f"{plan.name} (planId {plan.planId}, v{plan.version}) · {plan.weeklyTarget} workouts a week", ""]
    flex = next((index for index, step in enumerate(plan.steps) if step.makeUp), None)
    for index, step in enumerate(plan.steps):
        if step.isRest:
            lines.append(f"{dayName(index)}: {step.title} (rest day)")
            continue
        if index == flex:
            makeUp = ", ".join(dayName(day) for day in step.makeUp)
            lines.append(f"{dayName(index)}: {step.title}, the flex day: makes up the first day missed that week, "
                         f"in this order: {makeUp}; if none was missed, this bonus workout:")
        else:
            lines.append(f"{dayName(index)}: {step.title}")
        lines += [f"    {exerciseText(exercise)}" for exercise in step.exercises]
    if flex is not None and plan.moves:
        lines += ["", "Moves, in the weeks the flex day makes up a day:"]
        for madeUp in plan.steps[flex].makeUp:
            changes = []
            for weekday in range(len(plan.steps)):
                stepIndex = madeUp if weekday == flex else weekday
                if plan.steps[stepIndex].isRest:
                    continue
                usual = [exercise.exerciseId for exercise in plan.steps[stepIndex].exercises]
                shown = sessionExercises(plan, weekday, stepIndex, madeUp)
                gone = [exercise.name for exercise in plan.steps[stepIndex].exercises
                        if exercise.exerciseId not in {entry.exercise.exerciseId for entry in shown}]
                added = [f"{entry.exercise.name} (from {dayName(entry.trackDay)})" for entry in shown
                         if entry.exercise.exerciseId not in usual]
                if gone:
                    changes.append(f"{dayName(weekday)} leaves out {', '.join(gone)}")
                if added:
                    changes.append(f"{dayName(weekday)} ends with {', '.join(added)}")
            if changes:
                lines.append(f"    {dayName(flex)} as {dayName(madeUp)}: " + "; ".join(changes))
    return lines


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print("Usage: .venv/bin/python tools/checkPlan.py <plan.json>")
        return 2
    path = Path(arguments[0])
    try:
        check = readPlanFile(path.read_bytes())
    except OSError as problem:
        print(f"Can't read {path}: {problem.strerror}")
        return 2
    if check.plan is None:
        print(f"❌ The app would refuse {path.name}:")
        print("\n".join(f"  • {error}" for error in check.errors))
    else:
        print(f"✅ The app would import {path.name}.")
    print("\n".join(f"  Note: {warning}" for warning in check.warnings) or "", end="\n" if check.warnings else "")
    if check.plan is not None:
        print()
        print("\n".join(weekLines(check.plan)))
    return 0 if check.plan is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
