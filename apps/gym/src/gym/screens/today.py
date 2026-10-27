"""The Today tab (plan 6, SC2.1, SC2.3), restyled and simplified (LK1.2):

    Upper                                            ⋮
    Monday · 2 of 5 this week
    ┌ 3 of 10 done                              30% ┐
    └ ━━━━━━━━━━━━──────────────────────────────    ┘
    ┌ Lat pulldown                           ⋯  ( ) ┐   a card per exercise; the big circle ticks it
    │ 3×11 @ 25 kg/side  [new]                      │   "new": a step up, tap for not today (UN1.1)
    │ "RIR 1–2. Set the seat …"                     │
    └ [2:30] [Sets]                                 ┘   2:30 starts the rest timer; Sets opens the sets
    ┌ Chest-supported T-bar row              ⋯  (✓) ┐   done: hollow, what was logged
    └ 3×11 @ 38.75 kg                               ┘
                  [ Finish workout ]
    ┌ STEPS TODAY  14,000                        ✎  ┐
    ┌ Rest · Lat pulldown           1:47  +30 s  ×  ┐   the rest timer, kept at the bottom (RT1.1)

⋯ holds the rest: skip, the weight (✎, WD2.1), the how-to (also a tap on the name, SC7.1) and not today
(UN1.1). A rest day shows "Rest day" and what's next. No plan yet: "Import your plan in the PC view", with
"Import a file" as the fallback (G2b-2). A deload week, or one starting within a week, shows a card under
the header (WD2.4). An exercise with no weight of yours yet shows "@ ? kg", and its tick opens the sets
(PF3). Ticking one of today's exercises starts its rest, unless nothing's left to do.
"""

import asyncio

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.rules.stats import kgText, setsText, thousands
from gym.rules.today import (
    ExerciseLine,
    SetDone,
    clockText,
    deloadText,
    headerParts,
    kilogramsUnit,
    restLeft,
    targetText,
    workoutProgress,
)
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import (
    big,
    card,
    faint,
    field,
    gap,
    header,
    label,
    mainButton,
    pill,
    quiet,
    screen,
    shaped,
    softButton,
    tapSize,
    title,
    track,
)

restOverShownFor = 120  # seconds "Rest over" stays before the bar goes by itself


@ft.component
def TodayTab(app, model):
    view = model.today
    if view is None:
        return ft.Column([quiet("Loading…")])
    heading, subtitle = headerParts(view)
    under = ft.Row([quiet(subtitle, size=14),
                    faint(f"· {model.waiting} waiting", size=14) if model.waiting else ft.Container(visible=False)],
                   spacing=6, wrap=True)  # SC1.1
    parts = [header(heading, under, trailing=[Menu(app, app.menuItems)]), Banners(app, model), Notice(app, model)]
    deload = deloadText(view)
    if deload:
        parts.append(card(ft.Row([ft.Icon(ft.Icons.SELF_IMPROVEMENT, size=22), ft.Text(deload, expand=True)],
                                 spacing=12), raised=True, padding=14))
    if not view.hasPlan:
        parts.append(NoPlan(app))
    elif view.isRestDay:
        parts.append(RestDay(app, view))
    else:
        parts.append(WorkoutProgress(view))
        parts += [ExerciseRow(app, line, key=line.exercise.exerciseId) for line in view.exercises]
        parts.append(FinishLine(app, view))
    parts.append(StepsLine(app, view.stepsToday, key=f"steps{view.date}"))
    return ft.Column([screen(parts), RestTimer(app, model)], spacing=0, expand=True)


@ft.component
def NoPlan(app):
    async def importFile(e):
        await app.pickPlanFile()

    return card(ft.Column([
        ft.Icon(ft.Icons.LIST_ALT, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text("Import your plan in the PC view.", size=16, weight=ft.FontWeight.W_500),
        ft.OutlinedButton("Import a file", icon=ft.Icons.UPLOAD_FILE, on_click=importFile),
    ], spacing=gap, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=24)


@ft.component
def RestDay(app, view):
    """A rest day, and what comes next. Rest days are rest: today's weekday decides the session (WD1.1)."""
    return card(ft.Column([
        ft.Icon(ft.Icons.BEDTIME_OUTLINED, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
        title("Rest day"),
        quiet(f"Next: {view.nextWorkoutTitle}", size=15) if view.nextWorkoutTitle else ft.Container(visible=False),
    ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=ft.Padding.symmetric(vertical=32))


@ft.component
def WorkoutProgress(view):
    """How far the workout is (SC2.4): done (and skipped) of all, with a bar."""
    done, skipped, total = workoutProgress(view)
    fraction = (done + skipped) / total if total else 0
    words = f"{done} of {total} done" + (f" · {skipped} skipped" if skipped else "")
    return card(ft.Column([
        ft.Row([ft.Text(words, weight=ft.FontWeight.W_600), quiet(f"{round(fraction * 100)}%")],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.ProgressBar(value=fraction, bar_height=6, border_radius=0, color=ft.Colors.PRIMARY, bgcolor=track),
    ], spacing=10), padding=ft.Padding.symmetric(horizontal=16, vertical=14))


@ft.component
def ExerciseRow(app, line: ExerciseLine, view=None):
    """One exercise as a card (19.1, SC2.3): name, target, the big tick; under it the cue, the rest time (a tap
    starts the timer) and Sets; ⋯ for the rest. Done or skipped, it turns hollow and shows what was logged.
    Tapping the name unfolds its how-to (SC7.1). History's day editor passes its day's view (HI1.1): a past day
    has no weight, Undo or rest timer, which all work from today."""
    editing, setEditing = ft.use_state(False)
    showingHowTo, setShowingHowTo = ft.use_state(False)
    settingWeight, setSettingWeight = ft.use_state(False)
    exercise = line.exercise
    weighted = (not exercise.isCardio and exercise.equipment != "bodyweight" and line.trackDay is not None
                and view is None)
    done, skipped = line.status == "done", line.status in ("skipped", "autoSkipped")
    canUndo = (line.isNew or line.declined) and line.status == "todo" and view is None

    async def check(e):
        if line.needsWeight and not done:
            setEditing(True)  # the plan's weight is only a placeholder: type the real one (PF3)
            return
        await app.check(line, view)

    async def skip(e):
        await app.skip(line, view)

    async def undo(e):
        await app.declineSuggestion(line, not line.declined)

    async def rest(e):
        await app.startRest(exercise.restSec, exercise.name)

    faded = ft.Colors.ON_SURFACE_VARIANT if done or skipped else None
    name = ft.Container(ft.Text(exercise.name, size=17, weight=ft.FontWeight.W_600, max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS, color=faded),
                        ink=True, tooltip=f"{exercise.name}: {'hide how to' if showingHowTo else 'how to'}",
                        on_click=lambda e: setShowingHowTo(not showingHowTo), border_radius=6)
    if done:
        shown: ft.Control = quiet(_loggedText(line), size=15)
    elif skipped:
        shown = quiet("skipped (not done when finished)" if line.status == "autoSkipped" else "skipped", size=15)
    else:
        shown = ft.Row([ft.Text(targetText(line), size=15, weight=ft.FontWeight.W_500),
                        NewMark(line, undo) if canUndo else ft.Container(visible=False)], spacing=8, wrap=True)
    menu = [ft.PopupMenuItem(content="Sets" if not exercise.isCardio else "Minutes", icon=ft.Icons.EDIT_NOTE,
                             on_click=lambda e: setEditing(not editing)),
            ft.PopupMenuItem(content="Hide how to" if showingHowTo else "How to", icon=ft.Icons.MENU_BOOK_OUTLINED,
                             on_click=lambda e: setShowingHowTo(not showingHowTo))]
    if not done:
        menu.append(ft.PopupMenuItem(content="Unskip" if line.status == "skipped" else "Skip", icon=ft.Icons.SKIP_NEXT,
                                     on_click=skip))
    if weighted:
        menu.append(ft.PopupMenuItem(content="Set the weight", icon=ft.Icons.EDIT_OUTLINED,
                                     on_click=lambda e: setSettingWeight(not settingWeight)))
    if canUndo:  # a step up: not today (UN1.1)
        menu.append(ft.PopupMenuItem(content="Take the step up" if line.declined else "Not today",
                                     icon=ft.Icons.UNDO if not line.declined else ft.Icons.REDO, on_click=undo))
    top = ft.Row([
        ft.Column([name, shown], spacing=4, expand=True),
        ft.PopupMenuButton(icon=ft.Icons.MORE_HORIZ, tooltip=f"{exercise.name}: more", items=menu,
                           icon_color=ft.Colors.ON_SURFACE_VARIANT, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                           shape=ft.RoundedRectangleBorder(radius=14)),
        ft.IconButton(ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED, icon_size=34,
                      icon_color=ft.Colors.PRIMARY if done else ft.Colors.OUTLINE,
                      tooltip=f"{exercise.name}: take back" if done else
                      f"{exercise.name}: enter the weight" if line.needsWeight else f"{exercise.name}: done as targeted",
                      on_click=check, width=tapSize + 4, height=tapSize + 4),
    ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START)
    parts: list[ft.Control] = [top]
    if not done and not skipped:
        if exercise.notes:
            parts.append(quiet(f"“{exercise.notes}”"))
        actions = []
        if exercise.restSec and view is None:
            actions.append(pill(clockText(exercise.restSec), icon=ft.Icons.TIMER_OUTLINED, on_click=rest,
                                tooltip=f"{exercise.name}: start the rest timer"))
        actions.append(pill("Sets" if not exercise.isCardio else "Minutes", icon=ft.Icons.EDIT_NOTE,
                            selected=editing, on_click=lambda e: setEditing(not editing),
                            tooltip=f"{exercise.name}: sets"))
        parts.append(ft.Row(actions, spacing=8, wrap=True))
    if showingHowTo:
        parts.append(HowTo(exercise))
    if editing:
        parts.append(SetsEditor(app, line, lambda: setEditing(False), view))
    if settingWeight:
        parts.append(WeightEditor(app, exercise, line.trackDay, line.targetWeightKg, line.stepKg,
                                  lambda: setSettingWeight(False)))
    return card(ft.Column(parts, spacing=10), padding=ft.Padding.only(left=16, top=10, right=6, bottom=14),
                hollow=done or skipped)


def NewMark(line: ExerciseLine, undo) -> ft.Card:
    """"new" beside a step up (UN1.1), a deep red chip with cut corners (LK1.4); a tap means not today, and again
    takes the step up after all."""
    words = "not today" if line.declined else "new"
    inner = ft.Container(ft.Row([ft.Icon(ft.Icons.UNDO if line.declined else ft.Icons.ARROW_UPWARD, size=13),
                                 ft.Text(words, size=12, weight=ft.FontWeight.W_600)], spacing=3, tight=True),
                         bgcolor=ft.Colors.TERTIARY_CONTAINER, padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                         ink=True, on_click=undo,
                         tooltip=f"{line.exercise.name}: {'take the step up' if line.declined else 'not today'}")
    return shaped(inner, 5)


@ft.component
def RestTimer(app, model):
    """The rest timer (RT1.1), kept at the bottom of Today: the time left with a bar, +30 s and ×. At 0 it
    says so; the phone's alert goes off then too, even with the screen off."""
    tick, setTick = ft.use_state(0)
    until = model.restUntil

    async def ticking():  # only while a rest runs, and the while after it that says so
        while until is not None and (app.clock() - until).total_seconds() <= restOverShownFor:
            await asyncio.sleep(0.5)
            setTick(lambda count: count + 1)

    ft.use_effect(ticking, [until], cleanup=lambda: None)
    if until is None:
        return ft.Container(visible=False)
    now = app.clock()
    left = restLeft(until, now)
    if left == 0 and (now - until).total_seconds() > restOverShownFor:
        return ft.Container(visible=False)

    async def more(e):
        await app.addRest(30)

    async def stop(e):
        await app.stopRest()

    fraction = left / model.restSeconds if model.restSeconds else 0
    words = ft.Column([faint(f"Rest · {model.restName}" if left else "Rest over", size=12, max_lines=1,
                             overflow=ft.TextOverflow.ELLIPSIS),
                       big(clockText(left) if left else "Go", 28)], spacing=0, expand=True)
    return ft.Container(card(ft.Column([
        ft.Row([ft.Icon(ft.Icons.TIMER_OUTLINED, size=26), words,
                softButton("+30 s", more, tooltip="Add 30 seconds"),
                ft.IconButton(ft.Icons.CLOSE, tooltip="Stop the rest timer", on_click=stop)], spacing=12),
        ft.ProgressBar(value=fraction, bar_height=4, border_radius=0,
                       color=ft.Colors.TERTIARY, bgcolor=track),  # the rest timer's bar is red (LK1.3)
    ], spacing=10), raised=True, padding=ft.Padding.only(left=16, top=10, right=8, bottom=14)),
        padding=ft.Padding.only(top=8, bottom=8))


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

    return ft.Column([
        ft.Row([field(f"{dayName}s, {unit}", typedWeight, lambda e: setTypedWeight(e.control.value), width=150),
                field(f"Step, {unit}", typedStep, lambda e: setTypedStep(e.control.value), width=130)],
               spacing=gap, wrap=True),
        quiet(f"A new weight starts {dayName}'s target again at {exercise.repsMin} reps. The step counts on every "
              "day."),
        quiet(problem) if problem else ft.Container(visible=False),
        ft.Row([mainButton("Save", save), ft.TextButton("Cancel", on_click=lambda e: close())]),
    ], spacing=gap)


@ft.component
def HowTo(exercise):
    """The plan's how-to under an exercise (SC7.1): Setup, the numbered steps, and the form cues."""
    def numbered(mark: str, text: str) -> ft.Row:
        """One step or cue; a long one wraps under its own text, not under the mark."""
        return ft.Row([ft.Text(mark, width=20, color=ft.Colors.ON_SURFACE_VARIANT), ft.Text(text, expand=True)],
                      spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)

    parts = []
    if exercise.setup:
        parts += [label("Setup"), ft.Text(exercise.setup)]
    if exercise.howTo:
        parts.append(label("How to"))
        parts += [numbered(f"{number}.", step) for number, step in enumerate(exercise.howTo, start=1)]
    if exercise.form:
        parts.append(label("Form"))
        parts += [numbered("•", cue) for cue in exercise.form]
    if not parts:
        parts.append(quiet("Your plan has no how-to for this exercise."))
    return ft.Container(ft.Column(parts, spacing=6), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=4,
                        padding=14, margin=ft.Margin.only(right=10))


@ft.component
def SetsEditor(app, line: ExerciseLine, close, view=None):
    """Sets: one row per set, pre-filled with what's logged or the target (19.1a-1); with no weight of yours
    yet, the kg fields start empty, and one left empty takes the set above's (PF4). Cardio: minutes."""
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
        fields = [field("Minutes", minutes, lambda e: setMinutes(e.control.value), width=130)]
    else:
        fields = []
        for index, (reps, kg) in enumerate(rows):
            cells = [ft.Container(faint(f"SET {index + 1}", size=11), width=44),
                     field("Reps", reps, lambda e, i=index: changeCell(i, 0, e.control.value), width=96)]
            if weighted:
                cells.append(field(kilogramsUnit(exercise), kg, lambda e, i=index: changeCell(i, 1, e.control.value),
                                   width=110))
            fields.append(ft.Row(cells, spacing=10))
        fields.append(ft.Row([
            ft.TextButton("+ set", icon=ft.Icons.ADD,
                          on_click=lambda e: setRows([*rows, list(rows[-1]) if rows else ["0", ""]])),
            ft.TextButton("− set", icon=ft.Icons.REMOVE, on_click=lambda e: setRows(rows[:-1]),
                          disabled=len(rows) <= 1),
        ], spacing=0))
    return ft.Column([
        *fields,
        quiet(problem) if problem else ft.Container(visible=False),
        ft.Row([mainButton("Save", save), ft.TextButton("Cancel", on_click=lambda e: close())]),
    ], spacing=10)


@ft.component
def FinishLine(app, view):
    """Finish workout: anything untouched counts as skipped (19.1b-1). Available once something's logged."""
    async def finish(e):
        await app.finish()

    if view.finished:
        volume = f" · {thousands(view.volumeKg)} kg" if view.volumeKg else ""
        return card(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, size=22),
                            ft.Text(f"Workout finished{volume}", weight=ft.FontWeight.W_600)],
                           spacing=10, alignment=ft.MainAxisAlignment.CENTER), padding=16, hollow=True)
    return ft.Row([mainButton("Finish workout", finish, disabled=not view.workoutExists, expand=True)])


@ft.component
def StepsLine(app, stepsToday: int | None):
    """Today's steps (SC4.1), on rest days too, with ✎ to enter them. Steps are never a workout (CA1.1)."""
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
        return card(ft.Row([
            ft.Icon(ft.Icons.DIRECTIONS_WALK, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Column([label("Steps today"), big(shown, 20)], spacing=2, expand=True),
            ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Enter steps", on_click=open),
        ], spacing=14), padding=ft.Padding.only(left=16, top=12, right=8, bottom=12))
    return card(ft.Column([
        ft.Row([field("Steps today", typed, lambda e: setTyped(e.control.value), expand=True),
                mainButton("Save", save), ft.TextButton("Cancel", on_click=lambda e: setEditing(False))]),
        quiet(problem) if problem else ft.Container(visible=False),
    ], spacing=8), padding=12)


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
