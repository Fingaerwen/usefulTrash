"""The Progress tab (SC3.1), as approved:

    Progress                                     ⋮
    Bench Press   now 82.5 kg × 9    PR 85 kg   ▸
    Squat         now 120 kg × 6     PR 120 kg  ▸
    Dips          now 12 reps        PR 14 reps ▸
    Past exercises (2)                          ▸

Tapping an exercise opens its page: the chart (3M · 1Y · All), its PRs (heaviest, estimated 1RM, most
reps at the current weight), its target on each of its days with ✎ to set the weight and the weight step
(WD2.1), and its history with each session's volume (WD3.6).
"""

import flet as ft

from gym.rules.stats import chartRanges
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, tapSize, title
from gym.screens.today import WeightEditor


@ft.component
def ProgressTab(app, model):
    if model.detail is not None:
        return ExercisePage(app, model, model.detail, key=model.detail.exercise.exerciseId)
    showingPast, setShowingPast = ft.use_state(False)
    rows = [ProgressRow(app, line, key=line.exercise.exerciseId) for line in model.progress]
    if not rows:
        rows.append(quiet("Nothing here yet: import your plan, and its exercises show up."))
    if model.pastProgress:
        rows.append(ft.Container(ft.Row([ft.Text(f"Past exercises ({len(model.pastProgress)})", expand=True),
                                         ft.Text("▾" if showingPast else "▸")]),
                                 height=tapSize, ink=True, on_click=lambda e: setShowingPast(not showingPast)))
        if showingPast:
            rows += [ProgressRow(app, line, key=f"past{line.exercise.exerciseId}") for line in model.pastProgress]
    return ft.Column([
        ft.Row([ft.Container(title("Progress"), expand=True), Menu(app, app.menuItems)]),
        Banners(model), Notice(app, model), ft.Divider(), *rows,
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def ProgressRow(app, line):
    """One exercise: name, what comes next, its PR, ▸ to open it."""
    return ft.Container(
        ft.Row([ft.Text(line.exercise.name, expand=True, weight=ft.FontWeight.W_500, max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS), quiet(line.now),
                ft.Text(line.record), ft.Text("▸")], spacing=gap),
        height=tapSize, ink=True, tooltip=f"{line.exercise.name}: open",
        on_click=lambda e: app.openExercise(line.exercise.exerciseId))


@ft.component
def ExercisePage(app, model, detail):
    """One exercise (SC3.1): chart, PRs, its days with ✎, history."""
    editing, setEditing = ft.use_state(None)  # the day whose weight is being set
    exercise = detail.exercise
    ranges = ft.Row([ft.TextButton(name, on_click=lambda e, name=name: app.showRange(name),
                                   style=ft.ButtonStyle(text_style=ft.TextStyle(
                                       weight=ft.FontWeight.BOLD if name == detail.chartRange else None)))
                     for name in chartRanges], spacing=0)
    parts = [
        ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=lambda e: app.closeExercise()),
                ft.Container(title(exercise.name), expand=True), ranges]),
        Notice(app, model),
        ft.Text(f"{detail.chartLabel}  {detail.chart}") if detail.chart else quiet("Nothing logged in this span yet."),
    ]
    if detail.recordsText:
        parts.append(ft.Text(detail.recordsText))
    for day in detail.days:
        parts.append(ft.Row([ft.Text(f"Now {day.text}", expand=True),
                             ft.TextButton("✎", tooltip=f"{exercise.name}: set the weight",
                                           on_click=lambda e, weekday=day.weekday: setEditing(
                                               None if editing == weekday else weekday))
                             if detail.stepKg is not None else ft.Container(visible=False)]))
        if editing == day.weekday:
            parts.append(WeightEditor(app, exercise, day.weekday, day.target.weightKg, detail.stepKg,
                                      lambda: setEditing(None), key=f"edit{day.weekday}"))
    if detail.stepKg is not None:
        parts.append(quiet(f"Weight step: {detail.stepKg:g} {detail.chartLabel}"))
    parts.append(ft.Divider())
    parts += [quiet(line) for line in detail.lines] or [quiet("No sessions yet.")]
    return ft.Column(parts, spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)
