"""The Weight tab (SC5.1), as approved, restyled (LK1.2; no hint text on this screen):

    Weight                                       ⋮
    ┌   ‹     Fri 16 Oct     ›                    ┐
    └ [ kg  81.2              ]          [ Save ] ┘
    [3M] [1Y] [All]
    ┌ KG   the weigh-ins as a line                ┐
    └ 2 Oct                               16 Oct  ┘
    LAST 4
    82.0   81.8   81.6   81.2              −0.8 kg

Friday is preselected and ‹ › choose any other day up to today; saving again the same day replaces it
(DT2.1), and saving it empty clears it. On Fridays a banner asks for the weigh-in until it's in (18.4a).
"""

import datetime as dt

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.rules.stats import chartRanges, kgText
from gym.screens.charts import LineChart
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import card, field, header, iconButton, label, mainButton, quiet, screen, segments
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

    entry = card(ft.Column([
        ft.Row([iconButton(ft.Icons.CHEVRON_LEFT, "Earlier day", lambda e: move(-1)),
                ft.Text(dayText(day), size=16, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER,
                        expand=True),
                iconButton(ft.Icons.CHEVRON_RIGHT, "Later day", lambda e: move(1), disabled=day >= today)]),
        ft.Row([field("kg", typed, lambda e: setTyped(e.control.value), expand=True, size=22),
                mainButton("Save", save)], spacing=12),
        quiet(problem) if problem else ft.Container(visible=False),
    ], spacing=10), padding=ft.Padding.only(left=8, right=16, top=8, bottom=16))
    parts = [header("Weight", trailing=[Menu(app, app.menuItems)]), Banners(app, model), Notice(app, model), entry,
             segments([(name, name) for name in chartRanges], view.chartRange, app.showWeightRange),
             card(LineChart(view.points, byDay=True, key=f"weighIns{view.chartRange}") if view.points
                  else quiet("No weigh-ins in this span yet."))]
    if view.last:
        parts += [label(f"Last {len(view.last)}"), card(ft.Row([
            *[ft.Text(kg, size=17, weight=ft.FontWeight.W_600 if index == len(view.last) - 1 else ft.FontWeight.W_400,
                      color=None if index == len(view.last) - 1 else ft.Colors.ON_SURFACE_VARIANT)
              for index, kg in enumerate(view.last)],
            ft.Container(expand=True),
            quiet(view.changeText, size=15) if view.changeText else ft.Container(visible=False),
        ], spacing=16), padding=16, tooltip=view.lastText)]
    return screen(parts)
