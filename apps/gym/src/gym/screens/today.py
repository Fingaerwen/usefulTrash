"""The Today tab (plan 6, SC2.1), as approved, with the weekday in the header (WD1.1):

    Upper · Monday · week 2/5         3 waiting  ⋮
    Bench Press   4×9 @ 82.5 kg              [✓]
      rest 2:00 · "pause at bottom"  ▾ sets · skip
    ...
                  [ Finish workout ]
      Steps today: 14,000 ✎

A rest day shows "Rest day · next: Upper". No plan yet: "Import your plan in the PC view", with "Import a
file" as the fallback (G2b-2). Tapping an exercise's name unfolds the plan's how-to under it: Setup, the
steps and the form cues (SC7.1).
"""

import flet as ft

from gym.rules.today import ExerciseLine, SetDone, headerText, kilogramsUnit, targetText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, tapSize


@ft.component
def TodayTab(app, model):
    view = model.today
    if view is None:
        return ft.Column([quiet("Loading…")])
    header = ft.Row([
        ft.Text(headerText(view), size=16, weight=ft.FontWeight.BOLD, expand=True),
        quiet(f"{model.waiting} waiting") if model.waiting else ft.Container(visible=False),  # SC1.1
        Menu(app, app.menuItems),
    ])
    if not view.hasPlan:
        body = [NoPlan(app)]
    elif view.isRestDay:
        body = [RestDay(app, view)]
    else:
        body = [ExerciseRow(app, line, key=line.exercise.exerciseId) for line in view.exercises]
        body.append(FinishLine(app, view))
    return ft.Column([header, Banners(model), Notice(app, model), ft.Divider(), *body, ft.Divider(),
                      StepsLine(app, view.stepsToday, key=f"steps{view.date}")],
                     spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def NoPlan(app):
    async def importFile(e):
        await app.pickPlanFile()

    return ft.Column([ft.Text("Import your plan in the PC view."),
                      ft.OutlinedButton("Import a file", icon=ft.Icons.UPLOAD_FILE, on_click=importFile)], spacing=gap)


@ft.component
def RestDay(app, view):
    """Rest day · next: Upper. Rest days are rest: today's weekday decides the session (WD1.1)."""
    nextText = f"Rest day · next: {view.nextWorkoutTitle}" if view.nextWorkoutTitle else "Rest day"
    return ft.Column([ft.Text(nextText, size=16)], spacing=gap)


@ft.component
def ExerciseRow(app, line: ExerciseLine):
    """One exercise: name, target, [✓]; underneath rest time, form cues, ▾ sets and skip (19.1). Tapping
    the name unfolds its how-to (SC7.1)."""
    editing, setEditing = ft.use_state(False)
    showingHowTo, setShowingHowTo = ft.use_state(False)
    exercise = line.exercise
    done, skipped = line.status == "done", line.status in ("skipped", "autoSkipped")

    async def check(e):
        await app.check(line)

    async def skip(e):
        await app.skip(line)

    shown = _loggedText(line) if done else targetText(line)
    top = ft.Row([
        ft.Container(ft.Text(exercise.name, size=16, weight=ft.FontWeight.W_500,
                             color=ft.Colors.GREY_500 if skipped else None),
                     expand=True, height=tapSize, alignment=ft.Alignment.CENTER_LEFT, ink=True,
                     tooltip=f"{exercise.name}: {'hide how to' if showingHowTo else 'how to'}",
                     on_click=lambda e: setShowingHowTo(not showingHowTo)),
        ft.Text(shown, color=ft.Colors.GREY_500 if skipped else None),
        ft.IconButton(ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED,
                      tooltip=f"{exercise.name}: done as targeted" if not done else f"{exercise.name}: take back",
                      on_click=check,
                      width=tapSize, height=tapSize),
    ])
    details = []
    if exercise.restSec:
        details.append(quiet(f"rest {exercise.restSec // 60}:{exercise.restSec % 60:02d}"))
    if exercise.notes:
        details.append(quiet(f"“{exercise.notes}”"))
    if line.status == "autoSkipped":
        details.append(quiet("skipped (not done when finished)"))
    under = ft.Row([
        *details,
        ft.TextButton("▾ sets" if not exercise.isCardio else "▾ minutes", on_click=lambda e: setEditing(not editing)),
        ft.TextButton("unskip" if line.status == "skipped" else "skip", on_click=skip),
    ], spacing=4, wrap=True)
    parts = [top, under]
    if showingHowTo:
        parts.append(HowTo(exercise))
    if editing:
        parts.append(SetsEditor(app, line, lambda: setEditing(False)))
    return ft.Column(parts, spacing=0)


@ft.component
def HowTo(exercise):
    """The plan's how-to under an exercise (SC7.1): Setup, the numbered steps, and the form cues."""
    def numbered(mark: str, text: str) -> ft.Row:
        """One step or cue; a long one wraps under its own text, not under the mark."""
        return ft.Row([ft.Text(mark, width=20), ft.Text(text, expand=True)],
                      spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)

    parts = []
    if exercise.setup:
        parts.append(ft.Text(f"Setup: {exercise.setup}"))
    if exercise.howTo:
        parts.append(ft.Text("How to", weight=ft.FontWeight.W_500))
        parts += [numbered(f"{number}.", step) for number, step in enumerate(exercise.howTo, start=1)]
    if exercise.form:
        parts.append(ft.Text("Form", weight=ft.FontWeight.W_500))
        parts += [numbered("•", cue) for cue in exercise.form]
    if not parts:
        parts.append(quiet("Your plan has no how-to for this exercise."))
    return ft.Container(ft.Column(parts, spacing=4),
                        border=ft.Border.only(left=ft.BorderSide(2, ft.Colors.OUTLINE)),
                        padding=ft.Padding.only(left=12, top=4, bottom=4), margin=ft.Margin.only(left=12, bottom=8))


@ft.component
def SetsEditor(app, line: ExerciseLine, close):
    """▾ sets: one row per set, pre-filled with what's logged or the target (19.1a-1). Cardio: minutes."""
    exercise = line.exercise
    weighted = not exercise.isCardio and exercise.equipment != "bodyweight"
    startSets = line.logged.sets if line.logged and line.logged.sets else (
        (SetDone(line.targetReps or 0, line.targetWeightKg),) * (line.targetSets or 1))
    rows, setRows = ft.use_state([[str(done.reps), _kgText(done.weightKg)] for done in startSets])
    minutes, setMinutes = ft.use_state(str((line.logged.minutes if line.logged else None) or line.targetMinutes or ""))
    problem, setProblem = ft.use_state("")

    def changeCell(index: int, column: int, value: str):
        changed = [list(row) for row in rows]
        changed[index][column] = value
        setRows(changed)

    async def save(e):
        try:
            if exercise.isCardio:
                await app.saveSets(line, [], _whole(minutes, "Minutes"))
            else:
                sets = [SetDone(_whole(reps, "Reps"), _kilograms(kg) if weighted else None) for reps, kg in rows]
                await app.saveSets(line, sets)
        except ValueError as refused:
            setProblem(str(refused))
            return
        close()

    if exercise.isCardio:
        fields = [ft.TextField(label="Minutes", value=minutes, keyboard_type=ft.KeyboardType.NUMBER, width=120,
                               on_change=lambda e: setMinutes(e.control.value))]
    else:
        fields = []
        for index, (reps, kg) in enumerate(rows):
            cells = [quiet(f"Set {index + 1}"),
                     ft.TextField(label="Reps", value=reps, keyboard_type=ft.KeyboardType.NUMBER, width=90,
                                  on_change=lambda e, i=index: changeCell(i, 0, e.control.value))]
            if weighted:
                cells.append(ft.TextField(label=kilogramsUnit(exercise), value=kg, keyboard_type=ft.KeyboardType.NUMBER,
                                          width=100,
                                          on_change=lambda e, i=index: changeCell(i, 1, e.control.value)))
            fields.append(ft.Row(cells, spacing=gap))
        fields.append(ft.Row([
            ft.TextButton("+ set", on_click=lambda e: setRows([*rows, list(rows[-1]) if rows else ["0", ""]])),
            ft.TextButton("− set", on_click=lambda e: setRows(rows[:-1]), disabled=len(rows) <= 1),
        ]))
    return ft.Container(ft.Column([
        *fields,
        quiet(problem) if problem else ft.Container(visible=False),
        ft.Row([ft.Button("Save", on_click=save), ft.TextButton("Cancel", on_click=lambda e: close())]),
    ], spacing=gap), padding=ft.Padding.only(left=12, bottom=8))


@ft.component
def FinishLine(app, view):
    """Finish workout: anything untouched counts as skipped (19.1b-1). Available once something's logged."""
    async def finish(e):
        await app.finish()

    if view.finished:
        return ft.Row([quiet("Workout finished ✓")], alignment=ft.MainAxisAlignment.CENTER)
    return ft.Row([ft.Button("Finish workout", on_click=finish, disabled=not view.workoutExists, height=tapSize)],
                  alignment=ft.MainAxisAlignment.CENTER)


@ft.component
def StepsLine(app, stepsToday: int | None):
    """Steps today: 14,000 ✎ (SC4.1); on rest days too. Steps are never a workout (CA1.1)."""
    editing, setEditing = ft.use_state(False)
    typed, setTyped = ft.use_state("" if stepsToday is None else str(stepsToday))
    problem, setProblem = ft.use_state("")

    def open(e):
        setTyped("" if stepsToday is None else str(stepsToday))  # start from what's saved now
        setProblem("")
        setEditing(True)

    async def save(e):
        try:
            steps = _steps(typed) if typed.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        await app.setSteps(steps)
        setProblem("")
        setEditing(False)

    shown = f"{stepsToday:,}" if stepsToday is not None else "—"
    if not editing:
        return ft.Row([ft.Text(f"Steps today: {shown}"),
                       ft.IconButton(ft.Icons.EDIT, tooltip="Enter steps", on_click=open)])
    return ft.Column([
        ft.Row([ft.TextField(label="Steps today", value=typed, keyboard_type=ft.KeyboardType.NUMBER, width=160,
                             on_change=lambda e: setTyped(e.control.value)),
                ft.Button("Save", on_click=save), ft.TextButton("Cancel", on_click=lambda e: setEditing(False))]),
        quiet(problem) if problem else ft.Container(visible=False),
    ])


def _loggedText(line: ExerciseLine) -> str:
    """What was logged, written like the target: "4×9 @ 82.5 kg", or each set when they differ."""
    logged = line.logged
    if logged is None:
        return ""
    if logged.minutes is not None and not logged.sets:
        return f"{logged.minutes} min"
    if not logged.sets:
        return ""
    if len(set(logged.sets)) == 1:
        first = logged.sets[0]
        text = f"{len(logged.sets)}×{first.reps}"
        return text + (f" @ {_kgText(first.weightKg)} {kilogramsUnit(line.exercise)}" if first.weightKg is not None
                       else "")
    return " · ".join(f"{done.reps}" + (f"@{_kgText(done.weightKg)}" if done.weightKg is not None else "")
                      for done in logged.sets)


def _kgText(weightKg: float | None) -> str:
    return "" if weightKg is None else f"{weightKg:.2f}".rstrip("0").rstrip(".")


def _whole(text: str, what: str) -> int:
    """A typed whole number, like reps or minutes."""
    cleaned = text.strip()
    if not cleaned.isdigit():
        raise ValueError(f"{what}: type a whole number.")
    return int(cleaned)


def _steps(text: str) -> int:
    """A typed step total; "14,000", "14.000" and "14 000" all mean 14000."""
    return _whole(text.replace(",", "").replace(".", "").replace(" ", ""), "Steps")


def _kilograms(text: str) -> float:
    """A typed weight; a comma works as the decimal point too ("82,5")."""
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        raise ValueError("Weight: type a number, like 82.5.") from None
