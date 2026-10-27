"""History (HI1.1, SC6.1): the days, to look back on and edit, and the months, a progression diary (DI1.1),
restyled (LK1.2):

    History
    [Days] [Months] [All time]
         ‹      October 2026      ›
    ┌ Mo 13   Push · 5 exercises · finished    ✎ ┐
    └ Su 12   Rest · 9,500 steps               ✎ ┘

    ┌ Lat pulldown            25 to 30 kg/side  +5 ┐   Months: the diary
    │ best 3×12 @ 27.5 · 8 sessions                │
    └ Body weight             82.0 to 81.2 kg −0.8 ┘

The phone opens it from ⋮, the PC view has it as a tab. Both list every day since the plan began, a month at
a time (HI1.2). A day opens laid out like Today: its exercises, steps and weigh-in, and "Delete this
workout". The phone edits only its last 7 days (19.1f-1), so older ones open read-only. In Months, tapping an
exercise (or the body weight) unfolds its chart, one point per month. All time has every exercise's full
chart with its PRs, and the body weight's (DI1.2).
"""

import datetime as dt

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.rules.stats import kgText, setsText
from gym.screens.charts import ExerciseChart, LineChart, dateLabel  # noqa: F401  (dateLabel: shared with tests)
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import (
    card,
    faint,
    field,
    header,
    heading,
    iconButton,
    label,
    listCard,
    listRow,
    mainButton,
    quiet,
    screen,
    segments,
    statTile,
)
from gym.screens.today import ExerciseRow, _kilograms, _steps
from gym.screens.weight import dayText

beforeThePlan = "before your plan"  # what History says of a day before the first plan. Such days are left out


def monthText(month: dt.date) -> str:
    return f"{month:%B %Y}"


@ft.component
def HistoryScreen(app, model):
    """The phone's History, opened from ⋮ (HI1.1)."""
    back = app.closeDay if model.historyDay is not None else app.closeHistory
    top = [] if model.historyView is not None else [
        header("History", leading=iconButton(ft.Icons.ARROW_BACK, "Back", lambda e: back()))]
    return screen([*top, Notice(app, model), *HistoryBody(app, model)])


@ft.component
def HistoryTab(app, model):
    """The PC view's History tab (SC6.1)."""
    top = [] if model.historyView is not None else [header("History", trailing=[Menu(app, app.menuItems)]),
                                                    Banners(app, model)]
    return screen([*top, Notice(app, model), *HistoryBody(app, model)])


def HistoryBody(app, model) -> list[ft.Control]:
    if model.historyView is not None:
        return [DayEditor(app, model, model.historyView, key=f"day{model.historyView.date}")]
    modes = segments([("days", "Days"), ("months", "Months"), ("all", "All time")], model.historyMode,
                     app.showHistoryMode)
    body = {"months": Diary, "all": AllTime}.get(model.historyMode, Days)(app, model)
    return [modes, body]


def monthPicker(app, model, month: dt.date, first: dt.date | None) -> ft.Row:
    """‹ October 2026 ›, never past this month nor before the first."""
    thisMonth = app.localToday().replace(day=1)
    return ft.Row([
        iconButton(ft.Icons.CHEVRON_LEFT, "Earlier month", lambda e: app.showHistoryMonth(-1),
                   disabled=first is not None and month <= first),
        ft.Text(monthText(month), size=16, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER, expand=True),
        iconButton(ft.Icons.CHEVRON_RIGHT, "Later month", lambda e: app.showHistoryMonth(1),
                   disabled=month >= thisMonth),
    ])


def dateBadge(date: dt.date) -> ft.Column:
    """"Mo" over "13"."""
    return ft.Column([faint(weekdayNames[date.weekday()][:2].capitalize(), size=11),
                      ft.Text(str(date.day), size=17, weight=ft.FontWeight.W_600)],
                     spacing=0, width=34, horizontal_alignment=ft.CrossAxisAlignment.CENTER)


@ft.component
def Days(app, model):
    month = model.historyMonth or app.localToday().replace(day=1)
    parts: list[ft.Control] = [monthPicker(app, model, month, app.firstHistoryMonth())]
    days = [day for day in model.historyDays if day.text != beforeThePlan]
    rows = []
    for day in days:
        action = "Edit" if app.canEditDay(day.date) else "View"
        rows.append(listRow(ft.Row([
            dateBadge(day.date),
            ft.Text(day.text or "Nothing logged", expand=True,
                    color=None if day.text else ft.Colors.OUTLINE),
            ft.Icon(ft.Icons.EDIT_OUTLINED if action == "Edit" else ft.Icons.CHEVRON_RIGHT, size=18,
                    color=ft.Colors.OUTLINE),
        ], spacing=14), on_click=lambda e, date=day.date: app.editDay(date), tooltip=f"{action} {dayText(day.date)}",
            padding=ft.Padding.symmetric(horizontal=16, vertical=10)))
    parts.append(listCard(rows) if rows else card(quiet("No days here yet.")))
    if len(days) < len(model.historyDays) and days:
        parts.append(faint(f"Your plan began on {dayText(days[-1].date)}."))
    return ft.Column(parts, spacing=12)


def dayHeading(app, view) -> ft.Row:
    words = f"{view.title}" + (f", for {view.makesUp}" if view.makesUp else "")
    return header(dayText(view.date), words,
                  leading=iconButton(ft.Icons.ARROW_BACK, "Back to the days", lambda e: app.closeDay()))


@ft.component
def DayEditor(app, model, view):
    """A past day laid out like Today (HI1.1): its exercises, its steps and weigh-in, and Delete this workout.
    Read-only when it's too far back to edit here (HI1.2)."""
    date = view.date
    if not app.canEditDay(date):
        return DayView(app, view)
    steps = app.state.steps.get(date)
    weighIn = app.state.weights.get(date)
    typedSteps, setTypedSteps = ft.use_state("" if steps is None else str(steps))
    typedKg, setTypedKg = ft.use_state("" if weighIn is None else kgText(weighIn))
    problem, setProblem = ft.use_state("")

    async def saveSteps(e):
        try:
            value = _steps(typedSteps) if typedSteps.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        setProblem("")
        await app.setStepsOn(date, value)

    async def saveWeight(e):
        try:
            value = _kilograms(typedKg) if typedKg.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        setProblem("")
        await app.setBodyWeight(date, value)

    async def delete(e):
        await app.deleteWorkout(date)

    parts: list[ft.Control] = [dayHeading(app, view)]
    if not view.hasPlan:
        parts.append(card(quiet("No plan yet on this day.")))
    elif view.isRestDay:
        parts.append(card(ft.Text("Rest day")))
    else:
        parts += [ExerciseRow(app, line, view, key=f"{date}{line.exercise.exerciseId}") for line in view.exercises]
    parts += [
        label("Steps and weigh-in"),
        card(ft.Column([
            ft.Row([field("Steps", typedSteps, lambda e: setTypedSteps(e.control.value), expand=True),
                    mainButton("Save", saveSteps, tooltip="Save the steps")]),
            ft.Row([field("Weight, kg", typedKg, lambda e: setTypedKg(e.control.value), expand=True),
                    mainButton("Save", saveWeight, tooltip="Save the weigh-in")]),
            quiet(problem) if problem else ft.Container(visible=False),
        ], spacing=10), padding=12),
    ]
    if view.workoutExists:
        parts.append(ft.Row([ft.OutlinedButton("Delete this workout", icon=ft.Icons.DELETE_OUTLINE, on_click=delete)],
                            alignment=ft.MainAxisAlignment.CENTER))
    return ft.Column(parts, spacing=12)


@ft.component
def DayView(app, view):
    """A day too far back to edit on the phone (HI1.2): what was done, read-only. The PC view edits it."""
    date = view.date
    parts: list[ft.Control] = [dayHeading(app, view)]
    if not view.hasPlan:
        parts.append(card(quiet("No plan yet on this day.")))
    elif view.isRestDay:
        parts.append(card(ft.Text("Rest day")))
    rows = []
    for line in view.exercises if view.hasPlan and not view.isRestDay else ():
        logged = line.logged
        shown = (setsText(line.exercise, logged.sets, logged.minutes) if logged is not None and logged.done
                 else "skipped" if line.status in ("skipped", "autoSkipped") else "—")
        rows.append(listRow(ft.Row([ft.Text(line.exercise.name, expand=True, weight=ft.FontWeight.W_500),
                                    quiet(shown, text_align=ft.TextAlign.RIGHT, expand=True)])))
    if rows:
        parts.append(listCard(rows))
    steps, weighIn = app.state.steps.get(date), app.state.weights.get(date)
    parts += [ft.Row([statTile("Steps", f"{steps:,}" if steps is not None else "—", size=18),
                      statTile("Weight", f"{kgText(weighIn)} kg" if weighIn is not None else "—", size=18)],
                     spacing=8),
              faint("Older than 7 days: edit it in the PC view.")]
    return ft.Column(parts, spacing=12)


@ft.component
def Diary(app, model):
    """The months (DI1.1): each exercise's month, then the body weight's. A tap unfolds its chart."""
    diary = model.diary
    if diary is None:
        return quiet("Loading…")
    parts: list[ft.Control] = [monthPicker(app, model, diary.month, app.firstHistoryMonth())]
    parts.append(listCard([DiaryEntry(app, line, key=f"{diary.month}{line.exerciseId}") for line in diary.lines])
                 if diary.lines else card(quiet("Nothing logged or weighed this month.")))
    return ft.Column(parts, spacing=12)


@ft.component
def DiaryEntry(app, line):
    showing, setShowing = ft.use_state(False)
    change, _, difference = line.change.partition("  ")
    top = listRow(ft.Row([
        ft.Column([ft.Text(line.name, weight=ft.FontWeight.W_600), quiet(line.detail, size=12)], spacing=2,
                  expand=True),
        ft.Column([ft.Text(change, weight=ft.FontWeight.W_500),
                   faint(difference) if difference else ft.Container(visible=False)], spacing=0,
                  horizontal_alignment=ft.CrossAxisAlignment.END),
        ft.Icon(ft.Icons.EXPAND_LESS if showing else ft.Icons.EXPAND_MORE, size=18, color=ft.Colors.OUTLINE),
    ], spacing=10), tooltip=f"{line.name}: {'hide' if showing else 'show'} its months",
        on_click=lambda e: setShowing(not showing))
    parts = [top]
    if showing:
        unit = "kg" if not line.exerciseId else line.change.split("  ")[0].rsplit(" ", 1)[-1]
        parts.append(ft.Container(LineChart(app.state.monthlyPoints(line.exerciseId), byDay=False, unit=unit),
                                  padding=ft.Padding.only(left=8, right=16, bottom=12)))
    return ft.Column(parts, spacing=0)


@ft.component
def AllTime(app, model):
    """Every exercise's full chart since the start with its PRs (the plan's first, then past ones), then the
    body weight's (DI1.2). The Charts tab is for one exercise up close."""
    today = app.localToday()
    parts: list[ft.Control] = []
    for line in (*model.progress, *model.pastProgress):
        exerciseId = line.exercise.exerciseId
        view = app.state.chart(exerciseId, today, "All")
        if view is None or not view.sessions:
            continue
        detail = app.state.exerciseDetail(exerciseId, today, "All")
        parts.append(card(ft.Column([
            heading(line.exercise.name),
            quiet(detail.recordsText, size=12) if detail and detail.recordsText else ft.Container(visible=False),
            ExerciseChart(view, key=f"all{exerciseId}"),
        ], spacing=8)))
    weighIns = sorted(app.state.weights.items())
    if weighIns:
        parts.append(card(ft.Column([
            heading("Body weight"),
            quiet(f"{len(weighIns)} weigh-in{'' if len(weighIns) == 1 else 's'} · lowest "
                  f"{kgText(min(kg for _, kg in weighIns))} kg · highest "
                  f"{kgText(max(kg for _, kg in weighIns))} kg", size=12),
            LineChart(weighIns, byDay=True),
        ], spacing=8)))
    return ft.Column(parts or [card(quiet("Nothing logged yet."))], spacing=12)
