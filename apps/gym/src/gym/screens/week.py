"""The Week tab (SC4.1), as approved:

    Week 14–20 Oct                      ◂ ▸   ⋮
    ─────────────────────────────────────────────
    Workouts    3 of 4          Streak   5 weeks
    Completion  92%             Cardio   185 min
                                (45 gym + 140 from steps)
    Volume      18,400 kg   ↑ 6% vs last week
    PRs         Bench 85 kg · Squat 120 kg
    Weight      81.2 kg   ↓ 0.4 kg
    ─────────────────────────────────────────────
    Mo ✓   Tu ·   We ·   Th ✗   Fr ✓   Sa     Su
    ✓ trained   · rest   ✗ missed

One line per number here, so it fits a phone's width. Tapping a day in the calendar row enters or fixes
that day's steps: on the phone for the last 7 days, on the PC for any day.
"""

import flet as ft

from gym.rules.stats import calendarMarks, weekLines, weekTitle
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, tapSize, title
from gym.screens.today import _steps

dayLetters = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


@ft.component
def WeekTab(app, model):
    week = model.week
    if week is None:
        return ft.Column([quiet("Loading…")])
    choosing, setChoosing = ft.use_state(None)  # the day whose steps are being entered
    header = ft.Row([
        ft.Container(title(weekTitle(week)), expand=True),
        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Earlier week", on_click=lambda e: app.showWeek(model.weekOffset + 1)),
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Later week", disabled=model.weekOffset == 0,
                      on_click=lambda e: app.showWeek(model.weekOffset - 1)),
        Menu(app, app.menuItems),
    ])
    lines = [ft.Row([ft.Text(label, width=100, color=ft.Colors.GREY_500), ft.Text(text, expand=True)])
             for label, text in weekLines(week)]
    days = []
    for index, (date, status) in enumerate(week.calendar):
        mark = calendarMarks.get(status, "")
        enabled = app.canEnterStepsOn(date)
        days.append(ft.Container(ft.Text(f"{dayLetters[index]} {mark}".strip()), width=48, height=tapSize,
                                 alignment=ft.Alignment.CENTER, ink=enabled,
                                 tooltip=f"Steps on {date.day} {date:%b}" if enabled else None,
                                 on_click=(lambda e, index=index: setChoosing(index)) if enabled else None))
    parts = [header, Banners(app, model), Notice(app, model), ft.Divider(), *lines, ft.Divider(),
             ft.Row(days, spacing=0, wrap=True), quiet("✓ trained   · rest   ✗ missed")]
    if choosing is not None:
        date = week.calendar[choosing][0]
        steps = week.steps[choosing] if choosing < len(week.steps) else None
        parts.append(DaySteps(app, date, steps, lambda: setChoosing(None), key=f"steps{date}"))
    return ft.Column(parts, spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def DaySteps(app, date, steps, close):
    """Enter or fix one day's step total (CA1.1); empty clears it."""
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
        ft.Row([ft.TextField(label=f"Steps on {date.day} {date:%b}", value=typed, keyboard_type=ft.KeyboardType.NUMBER,
                             width=180, on_change=lambda e: setTyped(e.control.value)),
                ft.Button("Save", on_click=save), ft.TextButton("Cancel", on_click=lambda e: close())]),
        quiet(problem) if problem else ft.Container(visible=False),
    ])
