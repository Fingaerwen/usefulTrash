"""The Week tab (apps/diet/docs/plan.md 4a), as sketched: the week's averages against their targets, each day's
kcal as a bar with its target as a line (T training day, R rest day), and your weight from Talon."""

import datetime as dt

import flet as ft

from ambrosia.screens.common import Menu, months
from ambrosia.screens.look import big, card, faint, gap, header, iconButton, label, quiet, screen, statTile

barHeight = 140
barWidth = 26


def _range(week) -> str:
    first, last = week.monday, week.monday + dt.timedelta(days=6)
    return (f"{first.day} {months[first.month - 1]} - {last.day} {months[last.month - 1]}" if first.month != last.month
            else f"{first.day} - {last.day} {months[last.month - 1]}")


@ft.component
def WeekTab(app, model):
    week = model.week
    if week is None:
        return screen([])
    offset = model.weekOffset
    title = "This week" if offset == 0 else "Last week" if offset == 1 else "Week"
    tallest = max([day.kcal for day in week.days] + [day.target.kcal for day in week.days if day.target] + [1]) * 1.1

    def dayBar(day) -> ft.Column:
        filled = barHeight * min(day.kcal, tallest) / tallest
        layers: list[ft.Control] = [
            ft.Container(width=barWidth, height=barHeight, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH),
            ft.Container(width=barWidth, height=filled, border_radius=8, bottom=0,
                         bgcolor=ft.Colors.PRIMARY if not day.upcoming else ft.Colors.OUTLINE)]
        if day.target is not None:
            layers.append(ft.Container(width=barWidth + 8, height=2, bgcolor=ft.Colors.TERTIARY, left=-4,
                                       bottom=barHeight * min(day.target.kcal, tallest) / tallest))
        return ft.Column([ft.Stack(layers, width=barWidth, height=barHeight, clip_behavior=ft.ClipBehavior.NONE),
                          quiet(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")[day.date.weekday()], size=12),
                          faint("T" if day.kind == "training" else "R", size=11)],
                         spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                         tooltip=f"{day.kcal:,.0f} kcal" + (f" of {day.target.kcal:,}" if day.target else ""))

    def average(value, target, unit) -> str | None:
        if target is None:
            return None
        return f"target {target:,.0f}{unit} a day"

    tiles = ft.Row([
        statTile("Average", f"{week.averageKcal:,.0f} kcal" if week.averageKcal is not None else "nothing yet",
                 average(week.averageKcal, week.averageTargetKcal, "")),
        statTile("Protein", f"{week.averageProteinG:.0f} g" if week.averageProteinG is not None else "nothing yet",
                 average(week.averageProteinG, week.averageTargetProteinG, " g")),
    ], spacing=gap)
    if week.weightKg is None:
        weight = card(quiet("No weigh-ins in Talon this week.", size=14))
    else:
        change = "" if week.weightChangeKg is None else f"{week.weightChangeKg:+.1f} kg".replace("-", "−")
        weight = card(ft.Row([
            ft.Column([big(f"{week.weightKg:.1f} kg"),
                       quiet(f"this week's average, {week.weighIns} weigh-in{'s' if week.weighIns != 1 else ''}")],
                      spacing=2, expand=True),
            ft.Column([quiet(change), faint("vs last week")], spacing=0,
                      horizontal_alignment=ft.CrossAxisAlignment.END) if change else ft.Container(visible=False)]))
    return screen([
        header(title, _range(week), trailing=[
            iconButton(ft.Icons.CHEVRON_LEFT, "The week before", lambda e: app.showWeek(offset + 1)),
            iconButton(ft.Icons.CHEVRON_RIGHT, "The week after", lambda e: app.showWeek(offset - 1),
                       disabled=offset == 0),
            Menu(app)]),
        tiles,
        label("Days"),
        card(ft.Column([ft.Row([dayBar(day) for day in week.days], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                        faint("The gold line is the day's target. T training day, R rest day.")], spacing=10)),
        label("Body weight (from Talon)"),
        weight,
    ])
