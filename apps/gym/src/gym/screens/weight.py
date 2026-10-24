"""The Weight tab (SC5.1), as approved (no hint text on this screen):

    Weight                                       ⋮
    ─────────────────────────────────────────────
    Fri 16 Oct    [ 81.2 ] kg              [Save]
    ─────────────────────────────────────────────
     kg  ▆▅▅▄▄▃▃▂                3M · 1Y · All
    Last 4:  82.0 · 81.8 · 81.6 · 81.2   (↓ 0.8 kg)

Friday is preselected and ◂ ▸ choose any other day up to today; saving again the same day replaces it
(DT2.1), and saving it empty clears it. On Fridays a banner asks for the weigh-in until it's in (18.4a).
"""

import datetime as dt

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.rules.stats import chartRanges, kgText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, title
from gym.screens.today import _kilograms

oneDay = dt.timedelta(days=1)


def dayText(date: dt.date) -> str:
    """Fri 16 Oct."""
    return f"{weekdayNames[date.weekday()][:3].capitalize()} {date.day} {date:%b}"


@ft.component
def WeightTab(app, model):
    view = model.weight
    if view is None:
        return ft.Column([quiet("Loading…")])
    return WeightPage(app, model, view, key=f"weight{view.preselected}")


@ft.component
def WeightPage(app, model, view):
    def saved(date: dt.date) -> str:
        weightKg = app.state.weights.get(date)
        return "" if weightKg is None else kgText(weightKg)

    day, setDay = ft.use_state(view.preselected)
    typed, setTyped = ft.use_state(saved(view.preselected))
    problem, setProblem = ft.use_state("")
    today = app.localToday()

    def move(days: int):
        chosen = day + days * oneDay
        if chosen <= today:
            setDay(chosen)
            setTyped(saved(chosen))
            setProblem("")

    async def save(e):
        try:
            weightKg = _kilograms(typed) if typed.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        setProblem("")
        await app.setBodyWeight(day, weightKg)

    ranges = ft.Row([ft.TextButton(name, on_click=lambda e, name=name: app.showWeightRange(name),
                                   style=ft.ButtonStyle(text_style=ft.TextStyle(
                                       weight=ft.FontWeight.BOLD if name == view.chartRange else None)))
                     for name in chartRanges], spacing=0)
    entry = ft.Row([
        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Earlier day", on_click=lambda e: move(-1)),
        ft.Text(dayText(day), width=88),
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Later day", disabled=day >= today, on_click=lambda e: move(1)),
        ft.TextField(label="kg", value=typed, keyboard_type=ft.KeyboardType.NUMBER, width=96,
                     on_change=lambda e: setTyped(e.control.value)),
        ft.Button("Save", on_click=save),
    ], spacing=4, wrap=True)
    return ft.Column([
        ft.Row([ft.Container(title("Weight"), expand=True), Menu(app, app.menuItems)]),
        Banners(app, model), Notice(app, model), ft.Divider(),
        entry, quiet(problem) if problem else ft.Container(visible=False), ft.Divider(),
        ft.Row([ft.Text(f"kg  {view.chart}", expand=True) if view.chart
                else ft.Container(quiet("No weigh-ins in this span yet."), expand=True), ranges], wrap=True),
        ft.Text(view.lastText) if view.lastText else ft.Container(visible=False),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)
