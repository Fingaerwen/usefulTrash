"""The Progress tab (SC3.1), restyled (LK1.2):

    Progress                                     ⋮
    ┌ Bench Press                          PR      ┐
    │ now 82.5 kg × 9                   85 kg   >  │
    ├ Squat                                PR      ┤
    └ now 120 kg × 6                   120 kg   >  ┘
    Past exercises (2)                           >

Tapping an exercise opens its page: the chart (3M · 1Y · All, drawn like the Charts tab), its PRs as tiles
(heaviest, estimated 1RM, most reps at the current weight), what's next on each of its days with ✎ to set the
weight and the weight step (WD2.1), and its history with each session's volume (WD3.6).
"""

import flet as ft

from gym.rules.stats import chartRanges
from gym.screens.charts import ExerciseChart
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import (
    card,
    chevron,
    faint,
    header,
    iconButton,
    label,
    listCard,
    listRow,
    quiet,
    screen,
    segments,
    statTile,
)
from gym.screens.today import WeightEditor


@ft.component
def ProgressTab(app, model):
    if model.detail is not None:
        return ExercisePage(app, model, model.detail, key=model.detail.exercise.exerciseId)
    showingPast, setShowingPast = ft.use_state(False)
    parts = [header("Progress", trailing=[Menu(app, app.menuItems)]), Banners(app, model), Notice(app, model)]
    if model.progress:
        parts.append(listCard([ProgressRow(app, line, key=line.exercise.exerciseId) for line in model.progress]))
    else:
        parts.append(card(quiet("Nothing here yet: import your plan, and its exercises show up.")))
    if model.pastProgress:
        parts.append(listCard([listRow(ft.Row([ft.Text(f"Past exercises ({len(model.pastProgress)})", expand=True,
                                                       weight=ft.FontWeight.W_500),
                                               ft.Icon(ft.Icons.EXPAND_LESS if showingPast else ft.Icons.EXPAND_MORE,
                                                       color=ft.Colors.OUTLINE)]),
                                       on_click=lambda e: setShowingPast(not showingPast))]))
        if showingPast:
            parts.append(listCard([ProgressRow(app, line, key=f"past{line.exercise.exerciseId}")
                                   for line in model.pastProgress]))
    return screen(parts)


@ft.component
def ProgressRow(app, line):
    """One exercise: its name and what comes next, its PR on the right, > to open it."""
    record = line.record.removeprefix("PR ")
    return listRow(ft.Row([
        ft.Column([ft.Text(line.exercise.name, weight=ft.FontWeight.W_600, max_lines=2,
                           overflow=ft.TextOverflow.ELLIPSIS), quiet(line.now)], spacing=2, expand=True),
        ft.Column([faint("PR", size=11), ft.Text(record, weight=ft.FontWeight.W_600)], spacing=0,
                  horizontal_alignment=ft.CrossAxisAlignment.END) if record else ft.Container(visible=False),
        chevron(),
    ], spacing=10), on_click=lambda e: app.openExercise(line.exercise.exerciseId),
        tooltip=f"{line.exercise.name}: open")


@ft.component
def ExercisePage(app, model, detail):
    """One exercise (SC3.1): chart, PRs, its days with ✎, history."""
    editing, setEditing = ft.use_state(None)  # the day whose weight is being set
    exercise = detail.exercise
    parts: list[ft.Control] = [
        header(exercise.name, leading=iconButton(ft.Icons.ARROW_BACK, "Back", lambda e: app.closeExercise())),
        Notice(app, model),
        segments([(name, name) for name in chartRanges], detail.chartRange, app.showRange),
        card(ExerciseChart(detail.chart, key=f"{exercise.exerciseId}{detail.chartRange}") if detail.chart.sessions
             else quiet("Nothing logged in this span yet.")),
    ]
    if detail.recordTiles:
        parts.append(ft.Row([statTile(name, value, size=17) for name, value in detail.recordTiles], spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START))
    if detail.days:
        rows: list[ft.Control] = []
        for day in detail.days:
            weekday, _, target = day.text.partition(" ")
            rows.append(listRow(ft.Row([
                ft.Text(weekday, width=44, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.W_600),
                ft.Text(target, expand=True, weight=ft.FontWeight.W_500),
                iconButton(ft.Icons.EDIT_OUTLINED, f"{exercise.name}: set the weight",
                           lambda e, weekday=day.weekday: setEditing(None if editing == weekday else weekday),
                           size=20) if detail.stepKg is not None else ft.Container(visible=False),
            ]), padding=ft.Padding.only(left=16, right=4, top=4, bottom=4)))
            if editing == day.weekday:
                rows.append(ft.Container(WeightEditor(app, exercise, day.weekday, day.target.weightKg, detail.stepKg,
                                                      lambda: setEditing(None), key=f"edit{day.weekday}"),
                                         padding=16))
        if detail.stepKg is not None:
            rows.append(listRow(quiet(f"Weight step: {detail.stepKg:g} {detail.chartLabel}")))
        parts += [label("Next time"), listCard(rows)]
    parts.append(label("History"))
    parts.append(listCard([listRow(HistoryLine(text)) for text in detail.lines]) if detail.lines
                 else card(quiet("No sessions yet.")))
    return screen(parts)


def HistoryLine(text: str) -> ft.Row:
    """"14 Oct  4×9 @ 82.5 kg · 3,024 kg": the date, what was done, and the volume quieter."""
    date, _, rest = text.partition("  ")
    done, _, volume = rest.rpartition(" · ") if rest.endswith(" kg") and " · " in rest else (rest, "", "")
    return ft.Row([ft.Text(date, width=56, color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                   ft.Text(done, expand=True), faint(volume, size=12) if volume else ft.Container(visible=False)],
                  spacing=8)
