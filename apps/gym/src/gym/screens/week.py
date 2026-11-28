"""The Week tab (SC4.1), restyled (LK1.2):

    This week                                ‹ ›  ⋮
    12–18 Oct
    ┌ WORKOUTS     ┐ ┌ STREAK       ┐
    └ 3 of 4       ┘ └ 5 weeks      ┘
    ┌ COMPLETION   ┐ ┌ CARDIO       ┐
    └ 92%          ┘ └ 185 min      ┘   45 gym + 140 from steps
    ┌ VOLUME       ┐ ┌ WEIGHT       ┐
    └ 18,400 kg    ┘ └ 81.2 kg      ┘   +6% vs last week · −0.4 kg
    PRS: Bench 85 kg · Squat 120 kg
    ┌ (✓) ( ) ( ) (×) (✓) ( ) ( )   ┐   trained, rest, missed. Today ringed
    └  Mo  Tu  We  Th  Fr  Sa  Su   ┘

A part that's zero is left out. Tapping a day in the calendar enters or fixes that day's steps: on the
phone for the last 7 days, on the PC for any day. A day Health Connect filled (HC1.1) shows its steps instead of
the field (HC1.3). Under the calendar, Steps and calories lists each day's steps with its active and total kcal.
"""

import datetime as dt

import flet as ft

from gym.rules.stats import weekTiles, weekTitle
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import (
    card,
    dot,
    faint,
    field,
    header,
    iconButton,
    label,
    listCard,
    listRow,
    mainButton,
    quiet,
    screen,
    statTile,
)
from gym.screens.today import _steps

dayLetters = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
statusWords = {"trained": "trained", "rest": "rest day", "missed": "missed", "open": "to do", "later": "coming up",
               "none": "no plan"}
trendIcons = {"up": ft.Icons.NORTH_EAST, "down": ft.Icons.SOUTH_EAST}


@ft.component
def WeekTab(app, model):
    week = model.week
    if week is None:
        return ft.Column([quiet("Loading…")])
    choosing, setChoosing = ft.use_state(None)  # the day whose steps are being entered
    name = {0: "This week", 1: "Last week"}.get(model.weekOffset, "Week")
    dates = weekTitle(week).removeprefix("Week ")
    top = header(name, dates, trailing=[
        iconButton(ft.Icons.CHEVRON_LEFT, "Earlier week", lambda e: app.showWeek(model.weekOffset + 1)),
        iconButton(ft.Icons.CHEVRON_RIGHT, "Later week", lambda e: app.showWeek(model.weekOffset - 1),
                   disabled=model.weekOffset == 0),
        Menu(app, app.menuItems)])
    tiles = [statTile(tile.name, tile.value, tile.detail or None, trendIcons.get(tile.trend))
             for tile in weekTiles(week)]
    rows = [ft.Row(tiles[index:index + 2] if index + 1 < len(tiles) else [tiles[index], ft.Container(expand=True)],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.START) for index in range(0, len(tiles), 2)]
    parts = [top, Banners(app, model), Notice(app, model), *rows]
    if week.records:
        parts += [label("Records this week"),
                  listCard([listRow(ft.Row([ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=18,
                                                    color=ft.Colors.ON_SURFACE_VARIANT), ft.Text(record, expand=True)],
                                           spacing=12)) for record in week.records])]
    days = []
    today = app.localToday()
    for index, (date, status) in enumerate(week.calendar):
        enabled = app.canEnterStepsOn(date)
        days.append(ft.Container(ft.Column([DayMark(status, date == today), faint(dayLetters[index], size=12)],
                                           spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                 expand=True, padding=ft.Padding.symmetric(vertical=6), border_radius=12,
                                 ink=enabled,
                                 tooltip=f"{dayLetters[index]} {date.day} {date:%b}: {statusWords.get(status, status)}"
                                 + (" · tap for steps" if enabled else ""),
                                 on_click=(lambda e, index=index: setChoosing(index)) if enabled else None))
    parts += [label("Days"), card(ft.Row(days, spacing=0), padding=ft.Padding.symmetric(horizontal=8, vertical=10))]
    if choosing is not None:
        date = week.calendar[choosing][0]
        steps = week.steps[choosing] if choosing < len(week.steps) else None
        known = app.state.stepDays.get(date)
        if known is not None and known.fromHealth:  # Health Connect's, not typed over (HC1.3)
            parts.append(card(ft.Row([quiet(f"{date.day} {date:%b}: {known.steps:,} steps from Health Connect",
                                            size=14, expand=True),
                                      ft.TextButton("Close", on_click=lambda e: setChoosing(None))]), padding=12))
        else:
            parts.append(card(DaySteps(app, date, steps, lambda: setChoosing(None), key=f"steps{date}"), padding=12))
    activity = [(date, app.state.stepDays.get(date)) for date, _ in week.calendar]
    activity = [(date, known) for date, known in activity if known is not None]
    if activity:  # each day's steps with its calories from Health Connect (HC1.1)
        parts += [label("Steps and calories"), listCard([
            listRow(ft.Row([ft.Text(f"{dayLetters[date.weekday()]} {date.day}", size=14, width=56),
                            ft.Text(f"{known.steps:,} steps", size=14, expand=True),
                            quiet(_kcalShort(known.activeKcal, known.totalKcal), size=14)], spacing=8),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10))
            for date, known in activity])]
    return screen(parts)


def _kcalShort(activeKcal: int | None, totalKcal: int | None) -> str:
    """ "412 active · 2,310 kcal" for a row of Steps and calories, the parts that are known."""
    parts = []
    if activeKcal is not None:
        parts.append(f"{activeKcal:,} active")
    if totalKcal is not None:
        parts.append(f"{totalKcal:,} kcal")
    return " · ".join(parts)


def DayMark(status: str, isToday: bool) -> ft.Container:
    """A day in the calendar: a filled circle with a tick when trained, a cross when missed, a dot on a rest
    day, a ring when it's still to come. Today has a stronger ring."""
    ring = ft.Border.all(2, ft.Colors.PRIMARY if isToday else ft.Colors.OUTLINE_VARIANT)
    size = 34
    if status == "trained":
        return ft.Container(ft.Icon(ft.Icons.CHECK, size=18, color=ft.Colors.ON_PRIMARY), width=size, height=size,
                            border_radius=size / 2, bgcolor=ft.Colors.PRIMARY, alignment=ft.Alignment.CENTER)
    if status == "missed":
        return ft.Container(ft.Icon(ft.Icons.CLOSE, size=16, color=ft.Colors.ON_SURFACE_VARIANT), width=size,
                            height=size, border_radius=size / 2, border=ring, alignment=ft.Alignment.CENTER)
    if status == "rest":
        return ft.Container(dot(6), width=size, height=size, border_radius=size / 2, alignment=ft.Alignment.CENTER,
                            border=ft.Border.all(2, ft.Colors.PRIMARY) if isToday else None)
    if status == "none":
        return ft.Container(width=size, height=size)
    return ft.Container(width=size, height=size, border_radius=size / 2, border=ring)


@ft.component
def DaySteps(app, date: dt.date, steps, close):
    """Enter or fix one day's step total (CA1.1). Empty clears it."""
    typed, setTyped = ft.use_state("" if steps is None else str(steps))
    problem, setProblem = ft.use_state("")

    async def save(e):
        try:
            value = _steps(typed) if typed.strip() else None
        except ValueError as refused:
            setProblem(str(refused))
            return
        await app.setStepsOn(date, value)
        close()

    return ft.Column([
        ft.Row([field(f"Steps on {date.day} {date:%b}", typed, lambda e: setTyped(e.control.value), expand=True),
                mainButton("Save", save), ft.TextButton("Cancel", on_click=lambda e: close())]),
        quiet(problem) if problem else ft.Container(visible=False),
    ], spacing=8)
