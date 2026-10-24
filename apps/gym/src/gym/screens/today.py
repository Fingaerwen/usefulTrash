"""The Today tab (plan 6, SC2.1), as approved, with the weekday in the header (WD1.1):

    Upper · Monday · week 2/5         3 waiting  ⋮
    Bench Press   4×9 @ 82.5 kg              [✓]
      rest 2:00 · "pause at bottom"  ▾ sets · skip
    ...
                  [ Finish workout ]
      Steps today: 14,000 ✎

A rest day shows "Rest day · next: Upper". No plan yet: "Import your plan in the PC view", with "Import a
file" as the fallback (G2b-2). Tapping an exercise's name unfolds the plan's how-to under it: Setup, the
steps and the form cues (SC7.1). ✎ weight sets the exercise's weight on this day and its weight step
(WD2.1). A deload week, or one starting within a week, shows a line under the header (WD2.4). An
exercise with no weight of yours yet shows "@ ? kg", and its ✓ opens ▾ sets (PF3).
"""

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.rules.stats import kgText, setsText, thousands
from gym.rules.today import ExerciseLine, SetDone, deloadText, headerText, kilogramsUnit, targetText
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
    deload = deloadText(view)
    if not view.hasPlan:
        body = [NoPlan(app)]
    elif view.isRestDay:
        body = [RestDay(app, view)]
    else:
        body = [ExerciseRow(app, line, key=line.exercise.exerciseId) for line in view.exercises]
        body.append(FinishLine(app, view))
    return ft.Column([header, Banners(app, model), Notice(app, model),
                      ft.Text(deload) if deload else ft.Container(visible=False), ft.Divider(), *body, ft.Divider(),
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
def ExerciseRow(app, line: ExerciseLine, view=None):
    """One exercise: name, target, [✓]; underneath rest time, form cues, ▾ sets and skip (19.1). Tapping
    the name unfolds its how-to (SC7.1). History's day editor passes its day's view (HI1.1): a past day has no
    ✎ weight or Undo, which both work from today."""
    editing, setEditing = ft.use_state(False)
    showingHowTo, setShowingHowTo = ft.use_state(False)
    settingWeight, setSettingWeight = ft.use_state(False)
    exercise = line.exercise
    weighted = (not exercise.isCardio and exercise.equipment != "bodyweight" and line.trackDay is not None
                and view is None)
    done, skipped = line.status == "done", line.status in ("skipped", "autoSkipped")

    async def check(e):
        if line.needsWeight and not done:
            setEditing(True)  # the plan's weight is only a placeholder: type the real one (PF3)
            return
        await app.check(line, view)

    async def skip(e):
        await app.skip(line, view)

    async def undo(e):
        await app.declineSuggestion(line, not line.declined)

    shown = _loggedText(line) if done else targetText(line)
    # The name and what's shown share the width equally, so a long entry wraps instead of pushing [✓] off the
    # screen, and every [✓] stays at the right edge.
    top = ft.Row([
        ft.Container(ft.Text(exercise.name, size=16, weight=ft.FontWeight.W_500, max_lines=2,
                             overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.GREY_500 if skipped else None),
                     expand=True, height=tapSize, alignment=ft.Alignment.CENTER_LEFT, ink=True,
                     tooltip=f"{exercise.name}: {'hide how to' if showingHowTo else 'how to'}",
                     on_click=lambda e: setShowingHowTo(not showingHowTo)),
        ft.Text(shown, color=ft.Colors.GREY_500 if skipped else None, expand=True, text_align=ft.TextAlign.RIGHT),
        ft.IconButton(ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED,
                      tooltip=f"{exercise.name}: take back" if done else
                      f"{exercise.name}: enter the weight" if line.needsWeight else f"{exercise.name}: done as targeted",
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
        ft.TextButton("✎ weight", on_click=lambda e: setSettingWeight(not settingWeight)) if weighted
        else ft.Container(visible=False),
        ft.TextButton("redo ↑" if line.declined else "undo ↑", on_click=undo)  # ↑new: not today (UN1.1)
        if (line.isNew or line.declined) and line.status == "todo" and view is None else ft.Container(visible=False),
    ], spacing=4, wrap=True)
    parts = [top, under]
    if showingHowTo:
        parts.append(HowTo(exercise))
    if editing:
        parts.append(SetsEditor(app, line, lambda: setEditing(False), view))
    if settingWeight:
        parts.append(WeightEditor(app, exercise, line.trackDay, line.targetWeightKg, line.stepKg,
                                  lambda: setSettingWeight(False)))
    return ft.Column(parts, spacing=0)


@ft.component
def WeightEditor(app, exercise, weekday: int, weightKg, stepKg, close):
    """✎ weight (WD2.1): the exercise's weight on this day (its target restarts there at repsMin, WD3.7)
    and its weight step on every day. Shared with the Progress tab's exercise page."""
    unit = kilogramsUnit(exercise)
    typedWeight, setTypedWeight = ft.use_state("" if weightKg is None else kgText(weightKg))
    typedStep, setTypedStep = ft.use_state("" if stepKg is None else kgText(stepKg))
    problem, setProblem = ft.use_state("")
    dayName = weekdayNames[weekday].capitalize()

    async def save(e):
        try:
            weight, step = _kilograms(typedWeight), _kilograms(typedStep, "Step")
        except ValueError as refused:
            setProblem(str(refused))
            return
        app.model.notice = ""
        if weightKg is None or abs(weight - weightKg) > 0.001:
            await app.setWeight(exercise.exerciseId, weekday, weight)
        if not app.model.notice and (stepKg is None or abs(step - stepKg) > 0.001):
            await app.setStep(exercise.exerciseId, step)
        if not app.model.notice:  # a refused value shows why and keeps the editor open
            close()

    return ft.Container(ft.Column([
        ft.Row([ft.TextField(label=f"{dayName}s, {unit}", value=typedWeight, keyboard_type=ft.KeyboardType.NUMBER,
                             width=140, on_change=lambda e: setTypedWeight(e.control.value)),
                ft.TextField(label=f"Step, {unit}", value=typedStep, keyboard_type=ft.KeyboardType.NUMBER, width=120,
                             on_change=lambda e: setTypedStep(e.control.value))], spacing=gap, wrap=True),
        quiet(f"A new weight starts {dayName}'s target again at {exercise.repsMin} reps. The step counts on every "
              "day."),
        quiet(problem) if problem else ft.Container(visible=False),
        ft.Row([ft.Button("Save", on_click=save), ft.TextButton("Cancel", on_click=lambda e: close())]),
    ], spacing=gap), padding=ft.Padding.only(left=12, bottom=8))


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
def SetsEditor(app, line: ExerciseLine, close, view=None):
    """▾ sets: one row per set, pre-filled with what's logged or the target (19.1a-1); with no weight of
    yours yet, the kg fields start empty, and one left empty takes the set above's (PF4). Cardio: minutes."""
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
                await app.saveSets(line, [], _whole(minutes, "Minutes"), view=view)
            else:
                weights = _setWeights([kg for _, kg in rows]) if weighted else [None] * len(rows)
                sets = [SetDone(_whole(reps, "Reps"), weightKg) for (reps, _), weightKg in zip(rows, weights)]
                await app.saveSets(line, sets, view=view)
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
        volume = f" · {thousands(view.volumeKg)} kg" if view.volumeKg else ""
        return ft.Row([quiet(f"Workout finished ✓{volume}")], alignment=ft.MainAxisAlignment.CENTER)
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
    return setsText(line.exercise, logged.sets, logged.minutes) if logged is not None else ""


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


def _setWeights(typed: list[str]) -> list[float]:
    """Each set's kg as typed; one left empty takes the set above's (PF4), so a weight is typed once."""
    weights: list[float] = []
    for text in typed:
        weights.append(weights[-1] if weights and not text.strip() else _kilograms(text))
    return weights


def _kilograms(text: str, what: str = "Weight") -> float:
    """A typed weight or weight step; a comma works as the decimal point too ("82,5")."""
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"{what}: type a number, like {'82.5' if what == 'Weight' else '2.5'}.") from None
