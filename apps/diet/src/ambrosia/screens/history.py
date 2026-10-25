"""History (AM5.5): every day back to the first, a month at a time; a day opens laid out like Today. The phone
edits the last 7 days (⋮ → History), the PC view any day (its History tab)."""

import flet as ft

from ambrosia.screens.common import Notice, backButton, dayText, months
from ambrosia.screens.look import faint, header, iconButton, listCard, listRow, quiet, screen
from ambrosia.screens.today import dayParts


def _monthsBack(app, model) -> int:
    today, month = app.localToday(), model.historyMonth or app.localToday().replace(day=1)
    return (today.year - month.year) * 12 + today.month - month.month


@ft.component
def HistoryBody(app, model, leading=None):
    if model.historyDay is not None:
        day = model.historyDay
        note = "" if day.editable else "Read only: the phone edits the last 7 days; the PC view edits any day."
        return screen([header(dayText(day.date), f"{day.kind} day",
                              leading=iconButton(ft.Icons.ARROW_BACK, "Back to the month", lambda e: app.closeDay())),
                       Notice(app, model), faint(note) if note else ft.Container(visible=False), *dayParts(app, day)])
    back = _monthsBack(app, model)
    month = model.historyMonth or app.localToday().replace(day=1)
    rows = [listRow(ft.Row([ft.Text(dayText(day.date), size=14, expand=True),
                            quiet((f"{day.kcal:,.0f} of {day.targetKcal:,} kcal" if day.targetKcal else
                                   f"{day.kcal:,.0f} kcal") if day.entries else "nothing logged", size=14),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=20, color=ft.Colors.OUTLINE)]),
                    on_click=lambda e, date=day.date: app.editDay(date), tooltip=f"Open {dayText(day.date)}")
            for day in model.historyDays]
    return screen([
        header("History", f"{months[month.month - 1]} {month.year}", leading=leading, trailing=[
            iconButton(ft.Icons.CHEVRON_LEFT, "The month before", lambda e: app.showMonth(back + 1)),
            iconButton(ft.Icons.CHEVRON_RIGHT, "The month after", lambda e: app.showMonth(back - 1),
                       disabled=back == 0)]),
        listCard(rows) if rows else faint("No days in this month yet."),
    ])


@ft.component
def HistoryScreen(app, model):
    """The phone's History, from the ⋮ menu."""
    return HistoryBody(app, model, backButton(app))


@ft.component
def HistoryTab(app, model):
    """The PC view's History tab."""
    return HistoryBody(app, model)
