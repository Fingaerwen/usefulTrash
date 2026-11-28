"""The Today tab (plan 6, SC2.1, SC2.3), restyled and simplified (LK1.2):

    Upper                                            ⋮
    Monday · 2 of 5 this week
    [Mon ·] [Tue] [Wed] [Thu] [Fri] [Sat]              this week's workout days (DY1.1), today with a dot
    ┌ 3 of 10 done                              30% ┐
    └ ━━━━━━━━━━━━──────────────────────────────    ┘
    ┌ Lat pulldown                           ⋯  ( ) ┐   a card per exercise. The big circle ticks a set
    │ 3×11 @ 25 kg/side  [new]                      │   "new": a step up, tap for not today (UN1.1)
    │ "RIR 1–2. Set the seat …"                     │
    └ [2:30] [Sets]                                 ┘   2:30 starts the rest timer. Sets opens the sets
    ┌ Seated cable row                       ⋯ (1/3)┐   part done: a ring, and what's left (TK1.1)
    └ 1 of 3 done · 2×12 @ 45 kg left               ┘
    ┌ Chest-supported T-bar row              ⋯  (✓) ┐   done: hollow, what was logged
    └ 3×11 @ 38.75 kg                               ┘
                  [ Finish workout ]
    ┌ STEPS TODAY  14,000                        ✎  ┐
    ┌ Rest · Lat pulldown           1:47  +30 s  ×  ┐   the rest timer, kept at the bottom (RT1.1)

⋯ holds the rest: all sets done at once, skip, take back, the weight (✎, WD2.1), the how-to (also a tap on the
name, SC7.1) and not today (UN1.1). Each tap on the circle is the next set as targeted (TK1.1), and done, a tap
takes the last set back. A rest day shows "Rest day" and what's next. No plan yet: "Import your plan in the PC view", with
"Import a file" as the fallback (G2b-2). A deload week, or one starting within a week, shows a card under
the header (WD2.4). An exercise with no weight of yours yet shows "@ ? kg", and its tick opens the sets
(PF3). Ticking one of today's exercises starts its rest, unless nothing's left to do.

The strip under the header (DY1.1) shows another of this week's workout days, and so does a flick sideways (to
the left for the next day). That day is laid out the same and edited the same, a day ahead too, like History's
day editor: no rest timer, weight or Not today, which all work from today. A past day has no Finish (it counts as
finished anyway), and a day ahead no steps.
"""

import asyncio

import flet as ft

from usefulShared.training.planFile import dropSuffix
from usefulShared.training.schedule import weekdayNames
from gym.rules.stats import kgText, setsText, thousands
from gym.rules.today import (
    ExerciseLine,
    SetDone,
    clockText,
    deloadText,
    headerParts,
    kilogramsUnit,
    restLeft,
    setsLeftText,
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
swipeSpeed = 300  # a sideways flick at least this fast (pixels a second) changes the day (DY1.1)


@ft.component
def TodayTab(app, model):
    today = model.today
    if today is None:
        return ft.Column([quiet("Loading…")])
    other = model.dayView  # another day of the week picked in the strip (DY1.1), None for today
    view = other or today
    heading, subtitle = headerParts(view, today.date if other is not None else None)
    under = ft.Row([quiet(subtitle, size=14),
                    faint(f"· {model.waiting} waiting", size=14) if model.waiting else ft.Container(visible=False)],
                   spacing=6, wrap=True)  # SC1.1
    parts = [header(heading, under, trailing=[Menu(app, app.menuItems)]), DayStrip(app, model), Banners(app, model),
             Notice(app, model)]
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
        parts += [ExerciseRow(app, line, other, key=f"{view.date}{line.exercise.exerciseId}")
                  for line in view.exercises]
        if view.date >= today.date:  # a past day's workout counts as finished anyway (R5a)
            parts.append(FinishLine(app, view, other))
    if view.date <= today.date:
        parts.append(StepsLine(app, view.stepsToday, view.date if other is not None else None,
                               key=f"steps{view.date}"))

    def swipe(e):
        """A flick sideways (DY1.1): to the left for the next day, to the right for the one before, like pages."""
        speed = e.primary_velocity or 0
        if abs(speed) >= swipeSpeed:
            app.shiftDay(1 if speed < 0 else -1)

    days = ft.GestureDetector(content=screen(parts), on_horizontal_drag_end=swipe, expand=True)
    return ft.Column([days, RestTimer(app, model)], spacing=0, expand=True)


@ft.component
def DayStrip(app, model):
    """This week's workout days (DY1.1), Mon Tue Wed …, the one shown filled. Today has a dot. A tap shows that
    day, and so does a swipe on the screen."""
    days, today = model.weekDays, model.today.date
    if len(days) < 2:
        return ft.Container(visible=False)
    shown = model.dayShown or today
    chips = []
    for date in days:
        name = weekdayNames[date.weekday()]
        words = name[:3].capitalize() + (" ·" if date == today else "")
        chips.append(pill(words, date == shown, on_click=lambda e, date=date: app.showDay(date),
                          tooltip=f"Show {name.capitalize()}" + (" (today)" if date == today else "")))
    return ft.Row(chips, spacing=6, scroll=ft.ScrollMode.AUTO)


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
    """One exercise as a card (19.1, SC2.3): name, target, the big tick. Under it the cue, the rest time (a tap
    starts the timer) and Sets. ⋯ for the rest. Done or skipped, it turns hollow and shows what was logged.
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

    async def tick(e):
        if line.asksWeight and not line.setsDone:
            setEditing(True)  # the plan's weight is only a placeholder: type the real one (PF3)
            return
        await app.checkSet(line, view)

    async def allDone(e):
        await app.check(line, view)

    async def takeBack(e):
        await app.takeBack(line, view)

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
    elif line.setsDone:
        shown = ft.Text(setsLeftText(line), size=15, weight=ft.FontWeight.W_500)  # part done (TK1.1)
    else:
        shown = ft.Row([ft.Text(targetText(line), size=15, weight=ft.FontWeight.W_500),
                        NewMark(line, undo) if canUndo else ft.Container(visible=False)], spacing=8, wrap=True)
    menu = [ft.PopupMenuItem(content="Sets" if not exercise.isCardio else "Minutes", icon=ft.Icons.EDIT_NOTE,
                             on_click=lambda e: setEditing(not editing)),
            ft.PopupMenuItem(content="Hide how to" if showingHowTo else "How to", icon=ft.Icons.MENU_BOOK_OUTLINED,
                             on_click=lambda e: setShowingHowTo(not showingHowTo))]
    if line.status == "todo" and line.setsLeft and not (line.asksWeight and not line.setsDone):
        menu.append(ft.PopupMenuItem(content="All sets done", icon=ft.Icons.DONE_ALL, on_click=allDone))
    if not done:
        menu.append(ft.PopupMenuItem(content="Unskip" if line.status == "skipped" else "Skip", icon=ft.Icons.SKIP_NEXT,
                                     on_click=skip))
    if line.setsDone or (done and line.logged is not None):
        menu.append(ft.PopupMenuItem(content="Take back", icon=ft.Icons.REMOVE_DONE, on_click=takeBack))
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
        SetTick(line, tick),
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
                                  lambda: setSettingWeight(False), line.dropWeightKg))
    return card(ft.Column(parts, spacing=10), padding=ft.Padding.only(left=16, top=10, right=6, bottom=14),
                hollow=done or skipped)


def SetTick(line: ExerciseLine, tick) -> ft.Control:
    """The big circle (TK1.1): empty, a ring filling up with "1/3" as sets are ticked, then the tick. Each tap is
    the next set. Done, a tap takes the last set back."""
    name, done = line.exercise.name, line.status == "done"
    size = tapSize + 4
    if line.setsDone and line.status == "todo" and line.targetSets:
        ring = ft.Stack([
            ft.ProgressRing(value=line.setsDone / line.targetSets, width=30, height=30, stroke_width=3,
                            color=ft.Colors.PRIMARY, bgcolor=track),
            ft.Container(ft.Text(f"{line.setsDone}/{line.targetSets}", size=11, weight=ft.FontWeight.W_600),
                         width=30, height=30, alignment=ft.Alignment.CENTER),
        ], width=30, height=30)
        return ft.Container(ring, width=size, height=size, alignment=ft.Alignment.CENTER, ink=True,
                            border_radius=size / 2, on_click=tick,
                            tooltip=f"{name}: set {line.setsDone + 1} of {line.targetSets} done")
    if done:
        tooltip = f"{name}: take back the last set" if line.setsDone > 1 else f"{name}: take back"
    elif line.asksWeight and not line.setsDone:
        tooltip = f"{name}: enter the weight"
    elif line.setsLeft:
        tooltip = f"{name}: set 1 of {line.targetSets} done"
    else:
        tooltip = f"{name}: done as targeted"
    return ft.IconButton(ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED, icon_size=34,
                         icon_color=ft.Colors.PRIMARY if done else ft.Colors.OUTLINE, tooltip=tooltip,
                         on_click=tick, width=size, height=size)


def NewMark(line: ExerciseLine, undo) -> ft.Card:
    """"new" beside a step up (UN1.1), a deep red chip with cut corners (LK1.4). A tap means not today, and again
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
    says so. The phone's alert goes off then too, even with the screen off."""
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
def WeightEditor(app, exercise, weekday: int, weightKg, stepKg, close, dropKg=None):
    """✎ weight (WD2.1): the exercise's weight on this day (its target restarts there at repsMin, WD3.7)
    and its weight step on every day. A drop set's drop weight on this day too (DS1.1). Shared with the Progress
    tab's exercise page."""
    unit = kilogramsUnit(exercise)
    typedWeight, setTypedWeight = ft.use_state("" if weightKg is None else kgText(weightKg))
    typedStep, setTypedStep = ft.use_state("" if stepKg is None else kgText(stepKg))
    typedDrop, setTypedDrop = ft.use_state("" if dropKg is None else kgText(dropKg))
    problem, setProblem = ft.use_state("")
    dayName = weekdayNames[weekday].capitalize()

    async def save(e):
        try:
            weight, step = _kilograms(typedWeight), _kilograms(typedStep, "Step")
            drop = _kilograms(typedDrop, "Drop") if exercise.hasDrop and typedDrop.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        app.model.notice = ""
        if weightKg is None or abs(weight - weightKg) > 0.001:
            await app.setWeight(exercise.exerciseId, weekday, weight)
        if not app.model.notice and drop is not None and (dropKg is None or abs(drop - dropKg) > 0.001):
            await app.setWeight(exercise.exerciseId + dropSuffix, weekday, drop)
        if not app.model.notice and (stepKg is None or abs(step - stepKg) > 0.001):
            await app.setStep(exercise.exerciseId, step)
        if not app.model.notice:  # a refused value shows why and keeps the editor open
            close()

    return ft.Column([
        ft.Row([field(f"{dayName}s, {unit}", typedWeight, lambda e: setTypedWeight(e.control.value), width=150),
                field(f"Step, {unit}", typedStep, lambda e: setTypedStep(e.control.value), width=130),
                *([field(f"Drop, {unit}", typedDrop, lambda e: setTypedDrop(e.control.value), width=130)]
                  if exercise.hasDrop else [])],
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
        """One step or cue. A long one wraps under its own text, not under the mark."""
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
    """Sets: one row per set, pre-filled with what's logged or the target (19.1a-1). With no weight of yours
    yet, the kg fields start empty, and one left empty takes the set above's (PF4). A drop set (DS1.1) has a
    drop row under each set, its reps and weight, empty for no drop. Cardio: minutes."""
    exercise = line.exercise
    weighted = not exercise.isCardio and exercise.equipment != "bodyweight"
    hasDrop = weighted and exercise.hasDrop
    startSets = line.logged.sets if line.logged and line.logged.sets else (
        (SetDone(line.targetReps or 0, line.targetWeightKg, line.dropReps, line.dropWeightKg),) * (line.targetSets or 1))
    rows, setRows = ft.use_state([[str(done.reps), _kgText(done.weightKg),
                                   "" if done.dropReps is None else str(done.dropReps), _kgText(done.dropKg)]
                                  for done in startSets])
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
                weights = _setWeights([row[1] for row in rows]) if weighted else [None] * len(rows)
                drops = _drops(rows) if hasDrop else [(None, None)] * len(rows)
                sets = [SetDone(_whole(row[0], "Reps"), weightKg, *drop)
                        for row, weightKg, drop in zip(rows, weights, drops)]
                await app.saveSets(line, sets, view=view)
        except ValueError as refused:
            setProblem(str(refused))
            return
        close()

    if exercise.isCardio:
        fields = [field("Minutes", minutes, lambda e: setMinutes(e.control.value), width=130)]
    else:
        fields = []
        for index, (reps, kg, dropReps, dropKg) in enumerate(rows):
            cells = [ft.Container(faint(f"SET {index + 1}", size=11), width=44),
                     field("Reps", reps, lambda e, i=index: changeCell(i, 0, e.control.value), width=96)]
            if weighted:
                cells.append(field(kilogramsUnit(exercise), kg, lambda e, i=index: changeCell(i, 1, e.control.value),
                                   width=110))
            fields.append(ft.Row(cells, spacing=10))
            if hasDrop:
                fields.append(ft.Row([
                    ft.Container(faint("DROP", size=11), width=44),
                    field("Reps", dropReps, lambda e, i=index: changeCell(i, 2, e.control.value), width=96),
                    field(kilogramsUnit(exercise), dropKg, lambda e, i=index: changeCell(i, 3, e.control.value),
                          width=110)], spacing=10))
        fields.append(ft.Row([
            ft.TextButton("+ set", icon=ft.Icons.ADD,
                          on_click=lambda e: setRows([*rows, list(rows[-1]) if rows else ["0", "", "", ""]])),
            ft.TextButton("− set", icon=ft.Icons.REMOVE, on_click=lambda e: setRows(rows[:-1]),
                          disabled=len(rows) <= 1),
        ], spacing=0))
    return ft.Column([
        *fields,
        quiet(problem) if problem else ft.Container(visible=False),
        ft.Row([mainButton("Save", save), ft.TextButton("Cancel", on_click=lambda e: close())]),
    ], spacing=10)


@ft.component
def FinishLine(app, view, other=None):
    """Finish workout: anything untouched counts as skipped (19.1b-1). Available once something's logged. On a day
    ahead in the strip (DY1.1) it finishes that day's workout."""
    async def finish(e):
        await app.finish(other)

    if view.finished:
        volume = f" · {thousands(view.volumeKg)} kg" if view.volumeKg else ""
        return card(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, size=22),
                            ft.Text(f"Workout finished{volume}", weight=ft.FontWeight.W_600)],
                           spacing=10, alignment=ft.MainAxisAlignment.CENTER), padding=16, hollow=True)
    return ft.Row([mainButton("Finish workout", finish, disabled=not view.workoutExists, expand=True)])


@ft.component
def StepsLine(app, stepsToday: int | None, date=None):
    """Today's steps (SC4.1), on rest days too, with ✎ to enter them. Steps are never a workout (CA1.1). An
    earlier day in the strip (DY1.1) passes its date, and its steps go to that day."""
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
        if date is None:
            await app.setSteps(steps)
        else:
            await app.setStepsOn(date, steps)
        setProblem("")
        setEditing(False)

    shown = f"{stepsToday:,}" if stepsToday is not None else "—"
    words = "Steps today" if date is None else "Steps"
    if not editing:
        return card(ft.Row([
            ft.Icon(ft.Icons.DIRECTIONS_WALK, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Column([label(words), big(shown, 20)], spacing=2, expand=True),
            ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Enter steps", on_click=open),
        ], spacing=14), padding=ft.Padding.only(left=16, top=12, right=8, bottom=12))
    return card(ft.Column([
        ft.Row([field(words, typed, lambda e: setTyped(e.control.value), expand=True),
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
    """A typed step total. "14,000", "14.000" and "14 000" all mean 14000."""
    return _whole(text.replace(",", "").replace(".", "").replace(" ", ""), "Steps")


def _setWeights(typed: list[str]) -> list[float]:
    """Each set's kg as typed. One left empty takes the set above's (PF4), so a weight is typed once."""
    weights: list[float] = []
    for text in typed:
        weights.append(weights[-1] if weights and not text.strip() else _kilograms(text))
    return weights


def _drops(rows: list[list[str]]) -> list[tuple[int | None, float | None]]:
    """Each set's drop (DS1.1) as typed: reps and weight, or none when its reps are empty. A weight left empty
    takes the drop above's, like the sets' (PF4)."""
    drops: list[tuple[int | None, float | None]] = []
    lastKg: float | None = None
    for _, _, reps, kg in rows:
        if not reps.strip():
            drops.append((None, None))
            continue
        if kg.strip():
            lastKg = _kilograms(kg, "Drop")
        elif lastKg is None:
            raise ValueError("Drop: type its weight too.")
        drops.append((_whole(reps, "Drop reps"), lastKg))
    return drops


def _kilograms(text: str, what: str = "Weight") -> float:
    """A typed weight or weight step. A comma works as the decimal point too ("82,5")."""
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"{what}: type a number, like {'82.5' if what == 'Weight' else '2.5'}.") from None
