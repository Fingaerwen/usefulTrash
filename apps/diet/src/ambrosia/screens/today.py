"""Today (apps/diet/docs/plan.md 4a, AM5.8), as sketched in the design round:

    Today                                        ⋮
    Monday 26 Oct · training day
    ┌ LEFT TODAY                       1,600 eaten ┐
    │ 1,600 kcal                          of 3,200 │
    │ ████████████░░░░░░░░░░░░                     │
    │ PROTEIN 101/160 g  FAT 45/90 g  CARBS 199/440 │
    └───────────────────────────────────────────────┘
    ┌ Breakfast  600 kcal                       +  ┐
    │ Oats, whole grain, rolled        80 g  303 kcal│
    └───────────────────────────────────────────────┘
    … Lunch, Dinner, Snacks …
    ┌ Water  1,250 ml of 3,000 ml        [+250 ml] ┐

A meal's + adds food to it. Tapping an entry unfolds it to change the amount or the meal, or delete it. The
same parts make History's day editor (AM5.5). A day the phone can't edit any more shows without + and taps.
"""

import flet as ft

from ambrosia.rules.foods import LoggedFood, mealNames, meals, total
from ambrosia.rules.today import DayView
from ambrosia.screens.common import Banners, Menu, Notice, dayText, kcalText
from ambrosia.screens.look import (
    big,
    card,
    faint,
    field,
    heading,
    iconButton,
    label,
    listCard,
    listRow,
    mainButton,
    pill,
    quiet,
    screen,
    softButton,
    track,
)


@ft.component
def TodayTab(app, model):
    day = model.today
    if day is None:
        return screen([])
    return screen([
        ft.Row([ft.Column([ft.Text("Today", size=26, weight=ft.FontWeight.BOLD),
                           quiet(f"{dayText(day.date)} · {day.kind} day", size=14)], spacing=2, expand=True),
                Menu(app)], vertical_alignment=ft.CrossAxisAlignment.START),
        Banners(app, model), Notice(app, model), *dayParts(app, day),
    ])


def dayParts(app, day: DayView) -> list[ft.Control]:
    """A day's summary, its four meals and water: Today, and History's day editor."""
    return [Summary(day), *[MealCard(app, day, meal) for meal in meals], WaterCard(app, day)]


def bar(fraction: float, height: int = 6) -> ft.ProgressBar:
    return ft.ProgressBar(value=max(0.0, min(fraction, 1.0)), bar_height=height, border_radius=height / 2,
                          color=ft.Colors.PRIMARY, bgcolor=track)


@ft.component
def Summary(day: DayView):
    """What's left of the day's target: kcal first, then protein, fat and carbs."""
    eaten = day.eaten
    if day.targets is None:
        return card(ft.Column([label("Eaten"), big(kcalText(eaten.kcal), 30),
                               quiet(f"P {eaten.proteinG:.0f} g · F {eaten.fatG:.0f} g · C {eaten.carbsG:.0f} g"),
                               faint("No targets on this day: your first targets file came later."
                                     if day.targetsLater else
                                     "No targets yet: import your targets file on the Targets tab.")], spacing=6))
    targets = day.targets

    def macro(name: str, have: float, want: int) -> ft.Column:
        return ft.Column([label(name), ft.Text(f"{have:.0f} / {want} g", size=16, weight=ft.FontWeight.W_600),
                          bar(have / want if want else 0, 4)], spacing=4, expand=True)

    left = day.leftKcal
    over = left < 0
    return card(ft.Column([
        ft.Row([ft.Column([label("Over today" if over else "Left today"), big(kcalText(abs(left)), 30)],
                          spacing=2, expand=True),
                ft.Column([quiet(f"{eaten.kcal:,.0f} eaten"), quiet(f"of {targets.kcal:,}")], spacing=0,
                          horizontal_alignment=ft.CrossAxisAlignment.END)]),
        bar(eaten.kcal / targets.kcal if targets.kcal else 0, 8),
        ft.Container(height=4),
        ft.Row([macro("Protein", eaten.proteinG, targets.proteinG), macro("Fat", eaten.fatG, targets.fatG),
                macro("Carbs", eaten.carbsG, targets.carbsG)], spacing=16),
    ], spacing=10))


@ft.component
def MealCard(app, day: DayView, meal: str):
    entries = day.meals.get(meal, ())
    kcal = total(entry.values for entry in entries).kcal
    name = mealNames[meal]
    plus = (iconButton(ft.Icons.ADD, f"Add to {name}", lambda e: app.openAdd(meal, day.date)) if day.editable
            else ft.Container(visible=False))
    top = listRow(ft.Row([heading(name), quiet(kcalText(kcal)) if entries else faint("nothing yet"),
                          ft.Container(expand=True), plus], spacing=10),
                  padding=ft.Padding.only(left=16, right=4, top=4, bottom=4))
    return listCard([top, *[LogRow(app, entry, day.editable) for entry in entries]])


@ft.component
def LogRow(app, entry: LoggedFood, editable: bool):
    """One thing eaten. A tap unfolds it: the amount, the meal, Save and Delete."""
    editing, setEditing = ft.use_state(False)
    amount, setAmount = ft.use_state("")
    meal, setMeal = ft.use_state(entry.meal)
    count = entry.portionCount if entry.portion != "grams" and entry.portionCount else entry.grams
    unitWord = {"grams": entry.unit, "servings": "servings", "pack": "packs"}[entry.portion]

    def toggle(e):
        setEditing(not editing)
        setAmount(f"{count:g}")
        setMeal(entry.meal)

    async def save(e):
        try:
            value = float(amount.replace(",", "."))
        except ValueError:
            app.model.notice = "The amount must be a number."
            return
        await app.changeLog(entry.logId, meal, entry.portion, value)
        setEditing(False)

    async def delete(e):
        await app.deleteLog(entry.logId)

    line = ft.Row([ft.Column([ft.Text(entry.title, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                              faint(entry.amount)], spacing=2, expand=True),
                   quiet(kcalText(entry.values.kcal), size=14)])
    row = listRow(line, on_click=toggle if editable else None,
                  tooltip=f"{entry.title}: change or delete" if editable else None,
                  padding=ft.Padding.symmetric(horizontal=16, vertical=10))
    if not editing:
        return row
    return ft.Column([row, ft.Container(ft.Column([
        ft.Row([field(f"How much ({unitWord})", amount, lambda e: setAmount(e.control.value), expand=True)]),
        ft.Row([pill(mealNames[option], option == meal, on_click=lambda e, option=option: setMeal(option))
                for option in meals], spacing=6, wrap=True),
        ft.Row([mainButton("Save", save), softButton("Delete", delete, icon=ft.Icons.DELETE_OUTLINE)], spacing=8),
    ], spacing=10), padding=ft.Padding.only(left=16, right=16, bottom=14))], spacing=0)


@ft.component
def WaterCard(app, day: DayView):
    """The day's water (AM2.6): +250 ml a tap. The pencil sets the total, to fix a mistake."""
    setting, setSetting = ft.use_state(False)
    typed, setTyped = ft.use_state("")
    of = f" of {day.waterTargetMl:,} ml" if day.waterTargetMl else ""

    async def add(e):
        await app.addWater(day.date)

    async def save(e):
        try:
            ml = int(typed.strip())
        except ValueError:
            app.model.notice = "Water must be a whole number of ml."
            return
        await app.setWater(day.date, ml)
        setSetting(False)

    def edit(e):
        setSetting(not setting)
        setTyped(str(day.waterMl))

    actions = [iconButton(ft.Icons.EDIT_OUTLINED, "Set the day's water", edit), softButton("+250 ml", add)] \
        if day.editable else []
    parts: list[ft.Control] = [ft.Row([
        ft.Icon(ft.Icons.WATER_DROP_OUTLINED, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Column([heading("Water"), quiet(f"{day.waterMl:,} ml{of}")], spacing=0, expand=True), *actions])]
    if setting:
        parts.append(ft.Row([field("Water today (ml)", typed, lambda e: setTyped(e.control.value), expand=True),
                             mainButton("Save", save)], spacing=8))
    return card(ft.Column(parts, spacing=10), padding=ft.Padding.only(left=16, right=12, top=10, bottom=10))
