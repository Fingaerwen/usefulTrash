"""History (HI1.1, SC6.1): the days, to look back on and edit, and the months, a progression diary (DI1.1).

    History                    Days · Months
    Mo 13  Push · 5 exercises · finished      [Edit]
    Su 12  Rest · 9,500 steps                 [Edit]

    Diary              ◂ October 2026 ▸
    Lat pulldown        25 → 30 kg/side  ↑5
      best 3×12 @ 27.5 · 8 sessions
    Body weight         82.0 → 81.2 kg  ↓0.8

The phone opens it from ⋮, the PC view has it as a tab; both list every day, a month at a time (HI1.2).
Edit lays the day out like Today: its exercises, steps and weigh-in, and "Delete this workout"; the phone
edits only its last 7 days (19.1f-1), so older ones open with View, read-only. In Months, tapping an
exercise (or the body weight) unfolds its chart, one point per month. All time has every exercise's full
chart with its PRs, and the body weight's (DI1.2).
"""

import datetime as dt

import flet as ft
import flet.canvas as cv

from gym.rules.schedule import weekdayNames
from gym.rules.stats import chartPoints, kgText, setsText
from gym.screens.charts import ExerciseChart, chartHeight, labelWidth, lineShapes
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, title
from gym.screens.today import ExerciseRow, _kilograms, _steps
from gym.screens.weight import dayText


def monthText(month: dt.date) -> str:
    return f"{month:%B %Y}"


def dateLabel(date: dt.date, byDay: bool) -> str:
    """4 Oct 2026, or Oct 2026 for a month."""
    return f"{date.day} {date:%b %Y}" if byDay else f"{date:%b %Y}"


@ft.component
def HistoryScreen(app, model):
    """The phone's History, opened from ⋮ (HI1.1)."""
    back = app.closeDay if model.historyDay is not None else app.closeHistory
    return ft.Column([
        ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=lambda e: back()), title("History")]),
        Notice(app, model), *HistoryBody(app, model),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def HistoryTab(app, model):
    """The PC view's History tab (SC6.1)."""
    return ft.Column([
        ft.Row([ft.Container(title("History"), expand=True), Menu(app, app.menuItems)]),
        Banners(app, model), Notice(app, model), *HistoryBody(app, model),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


def HistoryBody(app, model) -> list[ft.Control]:
    if model.historyView is not None:
        return [DayEditor(app, model, model.historyView, key=f"day{model.historyView.date}")]
    modes = ft.Row([ft.TextButton(label, on_click=lambda e, mode=mode: app.showHistoryMode(mode),
                                  style=ft.ButtonStyle(text_style=ft.TextStyle(
                                      weight=ft.FontWeight.BOLD if model.historyMode == mode else None)))
                    for mode, label in (("days", "Days"), ("months", "Months"), ("all", "All time"))], spacing=0)
    body = {"months": Diary, "all": AllTime}.get(model.historyMode, Days)(app, model)
    return [modes, ft.Divider(), body]


def monthPicker(app, model, month: dt.date, first: dt.date | None) -> ft.Row:
    """◂ October 2026 ▸, never past this month nor before the first."""
    thisMonth = app.localToday().replace(day=1)
    return ft.Row([
        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Earlier month", disabled=first is not None and month <= first,
                      on_click=lambda e: app.showHistoryMonth(-1)),
        ft.Text(monthText(month), weight=ft.FontWeight.W_500),
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Later month", disabled=month >= thisMonth,
                      on_click=lambda e: app.showHistoryMonth(1)),
    ])


@ft.component
def Days(app, model):
    month = model.historyMonth or app.localToday().replace(day=1)
    parts = [monthPicker(app, model, month, app.firstHistoryMonth())]
    for day in model.historyDays:
        action = "Edit" if app.canEditDay(day.date) else "View"
        parts.append(ft.Row([
            ft.Text(f"{weekdayNames[day.date.weekday()][:2].capitalize()} {day.date.day}", width=56),
            ft.Text(day.text or "—", expand=True),
            ft.TextButton(action, tooltip=f"{action} {dayText(day.date)}",
                          on_click=lambda e, date=day.date: app.editDay(date)),
        ]))
    if not model.historyDays:
        parts.append(quiet("No days here yet."))
    return ft.Column(parts, spacing=0)


@ft.component
def DayEditor(app, model, view):
    """A past day laid out like Today (HI1.1): its exercises, its steps and weigh-in, and Delete this workout;
    read-only when it's too far back to edit here (HI1.2)."""
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

    heading = f"{view.title} · {dayText(date)}" + (f", for {view.makesUp}" if view.makesUp else "")
    parts = [ft.Row([ft.TextButton("◂ Days", on_click=lambda e: app.closeDay()),
                     ft.Text(heading, size=16, weight=ft.FontWeight.BOLD, expand=True)])]
    if not view.hasPlan:
        parts.append(quiet("No plan yet on this day."))
    elif view.isRestDay:
        parts.append(ft.Text("Rest day"))
    else:
        parts += [ExerciseRow(app, line, view, key=f"{date}{line.exercise.exerciseId}") for line in view.exercises]
    parts += [
        ft.Divider(),
        ft.Row([ft.TextField(label="Steps", value=typedSteps, keyboard_type=ft.KeyboardType.NUMBER, width=140,
                             on_change=lambda e: setTypedSteps(e.control.value)),
                ft.Button("Save", on_click=saveSteps, tooltip="Save the steps")], wrap=True),
        ft.Row([ft.TextField(label="Weight, kg", value=typedKg, keyboard_type=ft.KeyboardType.NUMBER, width=140,
                             on_change=lambda e: setTypedKg(e.control.value)),
                ft.Button("Save", on_click=saveWeight, tooltip="Save the weigh-in")], wrap=True),
        quiet(problem) if problem else ft.Container(visible=False),
    ]
    if view.workoutExists:
        parts.append(ft.OutlinedButton("Delete this workout", icon=ft.Icons.DELETE_OUTLINE, on_click=delete))
    return ft.Column(parts, spacing=gap)


@ft.component
def DayView(app, view):
    """A day too far back to edit on the phone (HI1.2): what was done, read-only; the PC view edits it."""
    date = view.date
    heading = f"{view.title} · {dayText(date)}" + (f", for {view.makesUp}" if view.makesUp else "")
    parts = [ft.Row([ft.TextButton("◂ Days", on_click=lambda e: app.closeDay()),
                     ft.Text(heading, size=16, weight=ft.FontWeight.BOLD, expand=True)])]
    if not view.hasPlan:
        parts.append(quiet("No plan yet on this day."))
    elif view.isRestDay:
        parts.append(ft.Text("Rest day"))
    for line in view.exercises if view.hasPlan and not view.isRestDay else ():
        logged = line.logged
        shown = (setsText(line.exercise, logged.sets, logged.minutes) if logged is not None and logged.done
                 else "skipped" if line.status in ("skipped", "autoSkipped") else "—")
        parts.append(ft.Row([ft.Text(line.exercise.name, expand=True), ft.Text(shown, expand=True,
                                                                               text_align=ft.TextAlign.RIGHT)]))
    steps, weighIn = app.state.steps.get(date), app.state.weights.get(date)
    parts += [ft.Divider(), ft.Text(f"Steps: {steps:,}" if steps is not None else "Steps: —"),
              ft.Text(f"Weight: {kgText(weighIn)} kg" if weighIn is not None else "Weight: —"),
              quiet("Older than 7 days: edit it in the PC view.")]
    return ft.Column(parts, spacing=gap)


@ft.component
def Diary(app, model):
    """The months (DI1.1): each exercise's month, then the body weight's; a tap unfolds its chart."""
    diary = model.diary
    if diary is None:
        return quiet("Loading…")
    parts: list[ft.Control] = [monthPicker(app, model, diary.month, app.firstHistoryMonth())]
    parts += [DiaryEntry(app, line, key=f"{diary.month}{line.exerciseId}") for line in diary.lines]
    if not diary.lines:
        parts.append(quiet("Nothing logged or weighed this month."))
    return ft.Column(parts, spacing=4)


@ft.component
def DiaryEntry(app, line):
    showing, setShowing = ft.use_state(False)
    top = ft.Container(ft.Column([
        ft.Row([ft.Text(line.name, weight=ft.FontWeight.W_500, expand=True), ft.Text(line.change)]),
        quiet(line.detail),
    ], spacing=0), ink=True, tooltip=f"{line.name}: {'hide' if showing else 'show'} its months",
        on_click=lambda e: setShowing(not showing), padding=ft.Padding.symmetric(vertical=4))
    parts = [top]
    if showing:
        parts.append(LineChart(app.state.monthlyPoints(line.exerciseId), byDay=False))
    return ft.Column(parts, spacing=0)


@ft.component
def AllTime(app, model):
    """Every exercise's full chart since the start with its PRs (the plan's first, then past ones), then the
    body weight's (DI1.2); the Charts tab is for one exercise up close."""
    today = app.localToday()
    parts: list[ft.Control] = []
    for line in (*model.progress, *model.pastProgress):
        exerciseId = line.exercise.exerciseId
        view = app.state.chart(exerciseId, today, "All")
        if view is None or not view.sessions:
            continue
        detail = app.state.exerciseDetail(exerciseId, today, "All")
        parts += [ft.Text(line.exercise.name, size=16, weight=ft.FontWeight.W_500),
                  quiet(detail.recordsText) if detail and detail.recordsText else ft.Container(visible=False),
                  ExerciseChart(view, key=f"all{exerciseId}"), ft.Divider()]
    weighIns = sorted(app.state.weights.items())
    if weighIns:
        parts += [ft.Text("Body weight", size=16, weight=ft.FontWeight.W_500),
                  quiet(f"{len(weighIns)} weigh-in{'' if len(weighIns) == 1 else 's'} · lowest "
                        f"{kgText(min(kg for _, kg in weighIns))} kg · highest "
                        f"{kgText(max(kg for _, kg in weighIns))} kg"),
                  LineChart(weighIns, byDay=True)]
    return ft.Column(parts or [quiet("Nothing logged yet.")], spacing=gap)


@ft.component
def LineChart(points, byDay: bool):
    """A line through dated values (the diary's months, DI1.1; all weigh-ins, DI1.2), at most 30 points,
    evenly picked and ending with the latest."""
    width, setWidth = ft.use_state(300.0)
    if not points:
        return quiet("Nothing to draw yet.")
    if len(points) > chartPoints:
        step = (len(points) - 1) / (chartPoints - 1)
        points = [points[round(index * step)] for index in range(chartPoints)]
    values = [value for _, value in points]

    def resize(e):
        if abs(e.width - width) > 0.5:
            setWidth(e.width)

    axis = ft.Column([quiet(kgText(max(values))), quiet(kgText(min(values)))], width=labelWidth, height=chartHeight,
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
    canvas = cv.Canvas(shapes=lineShapes(values, [False] * len(values), width, None), height=chartHeight, expand=True,
                       on_resize=resize)
    first, last = points[0][0], points[-1][0]
    return ft.Column([
        ft.Row([axis, canvas], spacing=0),
        ft.Row([ft.Container(width=labelWidth),
                ft.Row([quiet(dateLabel(first, byDay)), quiet(dateLabel(last, byDay))],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True)], spacing=0),
    ], spacing=2)
