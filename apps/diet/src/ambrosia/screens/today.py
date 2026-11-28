"""Today (apps/diet/docs/plan.md 4a, AM5.8), as sketched in the design round:

    Today                                        ⋮
    Monday 26 Oct · training day
    [Mon ·] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun]      this week's days (AM12.1), today with a dot
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

A meal's + adds food to it. Tapping an entry opens it (AM12.2) to change the amount or the meal, or delete it. The
same parts make History's day editor (AM5.5). A day the phone can't edit any more shows without + and opens its
entries to look at only.

The strip under the header (AM12.1, like Talon's DY1.1) shows another day of this week, and so does a flick
sideways (to the left for the next day). That day is laid out and edited the same, a day ahead too, its food saved
under its own date. Like Talon's steps, water can't be added to a day ahead, since it isn't drunk yet.
"""

import flet as ft

from ambrosia.rules.foods import LoggedFood, mealNames, meals, total
from ambrosia.rules.today import DayView, DayWater
from ambrosia.screens.bulkCheck import blockLine, ruleText, suggestionTitle
from ambrosia.screens.common import Banners, Menu, Notice, dayText, dayWords, kcalText, months, weekdays
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

swipeSpeed = 300  # a sideways flick at least this fast (pixels a second) changes the day (AM12.1, as in Talon)


@ft.component
def TodayTab(app, model):
    today = model.today
    if today is None:
        return screen([])
    other = model.dayView  # another day of the week picked in the strip (AM12.1), None for today
    day = other or today
    if other is None:
        heading, under = "Today", f"{dayText(day.date)} · {day.kind} day"
    else:
        heading = weekdays[day.date.weekday()]
        under = f"{day.date.day} {months[day.date.month - 1]} · {dayWords(day.date, today.date)} · {day.kind} day"
    parts = [
        ft.Row([ft.Column([ft.Text(heading, size=26, weight=ft.FontWeight.BOLD),
                           quiet(under + (f" · {model.waiting} waiting" if model.waiting else ""), size=14)],
                          spacing=2, expand=True),
                Menu(app)], vertical_alignment=ft.CrossAxisAlignment.START),
        DayStrip(app, model), Banners(app, model), BulkCheckBanner(app, model), Notice(app, model),
        *dayParts(app, day, isToday=other is None),
    ]

    def swipe(e):
        """A flick sideways: to the left for the next day, to the right for the one before, like pages."""
        speed = e.primary_velocity or 0
        if abs(speed) >= swipeSpeed:
            app.shiftDay(1 if speed < 0 else -1)

    return ft.GestureDetector(content=screen(parts), on_horizontal_drag_end=swipe, expand=True)


@ft.component
def DayStrip(app, model):
    """This week's days (AM12.1), Mon Tue Wed …, the one shown filled. Today has a dot. A tap shows that day, and
    so does a swipe on the screen."""
    today = model.today.date
    shown = model.dayShown or today
    chips = []
    for date in model.weekDays:
        name = weekdays[date.weekday()]
        chips.append(pill(name[:3] + (" ·" if date == today else ""), date == shown,
                          on_click=lambda e, date=date: app.showDay(date),
                          tooltip=f"Show {name}" + (" (today)" if date == today else ""), expand=True))
    return ft.Row(chips, spacing=5)


@ft.component
def BulkCheckBanner(app, model):
    """The bulk check's suggestion (4g, AM3.3): the rule that fired with both blocks' averages and weigh-ins, Apply
    and Not now. Nothing changes until you tap Apply, and Apply waits until Ambrosia has synced today."""
    view = model.bulkCheck
    if view is None or view.suggestion is None:
        return ft.Container(visible=False)
    chosen = view.suggestion

    async def apply(e):
        await app.applySuggestion()

    return card(ft.Column([
        ft.Row([ft.Icon(ft.Icons.MONITOR_WEIGHT_OUTLINED, size=20),
                ft.Text(f"Bulk check: {suggestionTitle(chosen)}", size=16, weight=ft.FontWeight.W_600, expand=True)],
               spacing=12),
        ft.Text(ruleText(view, chosen), size=14),
        quiet(blockLine(view.check.block), size=13),
        quiet(blockLine(chosen.compared), size=13),
        ft.Row([mainButton("Apply", apply), softButton("Not now", lambda e: app.dismissSuggestion())], spacing=8),
        faint("Apply waits until Ambrosia has synced today, so a late weigh-in isn't missed.")
        if not model.applyReady else ft.Container(visible=False),
    ], spacing=8), padding=16, raised=True)


def dayParts(app, day: DayView, isToday: bool = False) -> list[ft.Control]:
    """A day's summary, its four meals and water: Today (and the strip's other days), and History's day editor."""
    return [Summary(day, isToday), *[MealCard(app, day, meal) for meal in meals], WaterCard(app, day)]


def bar(fraction: float, height: int = 6) -> ft.ProgressBar:
    return ft.ProgressBar(value=max(0.0, min(fraction, 1.0)), bar_height=height, border_radius=height / 2,
                          color=ft.Colors.PRIMARY, bgcolor=track)


@ft.component
def Summary(day: DayView, isToday: bool = False):
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
        ft.Row([ft.Column([label(("Over" if over else "Left") + (" today" if isToday else "")),
                           big(kcalText(abs(left)), 30)],
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
    """One thing eaten. A tap opens it (AM12.2): what it adds, the amount, the meal, Save and Delete, or only to
    look at on a day the phone can't edit any more."""
    line = ft.Row([ft.Column([ft.Text(entry.title, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                              faint(entry.amount)], spacing=2, expand=True),
                   quiet(kcalText(entry.values.kcal), size=14), ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18,
                                                                        color=ft.Colors.OUTLINE)], spacing=6)
    return listRow(line, on_click=lambda e: app.openLog(entry, editable),
                   tooltip=f"{entry.title}: {'change or delete' if editable else 'look at it'}",
                   padding=ft.Padding.only(left=16, right=10, top=10, bottom=10))


def waterSources(water: DayWater) -> str:
    """What adds itself to a day's water (AM12.4): "1,300 ml from your Talon workout · 600 ml from a shake"."""
    parts = []
    if water.workout:
        parts.append(f"{water.workoutMl:,} ml from your Talon workout")
    if water.shakes:
        parts.append(f"{water.shakesMl:,} ml from " + ("a shake" if water.shakes == 1 else f"{water.shakes} shakes"))
    return " · ".join(parts)


@ft.component
def WaterCard(app, day: DayView):
    """The day's water (AM2.6): +250 ml a tap, and the pencil sets what you added, to fix a mistake. The pencil's
    field opens in the card's own row, where you tapped, and takes the focus, so the phone keeps it in view above
    the keyboard (it used to open in a row below, under the tab bar). Shakes and Talon's finished workout add their
    water by themselves (AM12.4), shown under the total."""
    setting, setSetting = ft.use_state(False)
    typed, setTyped = ft.use_state("")
    water = day.water or DayWater(day.waterMl)
    of = f" of {day.waterTargetMl:,} ml" if day.waterTargetMl else ""
    sources = waterSources(water)

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
        setTyped(str(water.byHandMl))
        setSetting(True)

    icon = ft.Icon(ft.Icons.WATER_DROP_OUTLINED, color=ft.Colors.ON_SURFACE_VARIANT)
    if setting:
        box = field("Water you added (ml)", typed, lambda e: setTyped(e.control.value), expand=True)
        box.autofocus, box.on_submit = True, save
        parts: list[ft.Control] = [
            ft.Row([icon, box, mainButton("Save", save),
                    iconButton(ft.Icons.CLOSE, "Cancel", lambda e: setSetting(False))], spacing=8),
            faint(f"Plus {sources}, added for you.") if sources else ft.Container(visible=False)]
    else:
        actions = [iconButton(ft.Icons.EDIT_OUTLINED, "Set the water you added", edit),
                   softButton("+250 ml", add)] if day.editable and not day.ahead else []
        parts = [ft.Row([icon, ft.Column([heading("Water"), quiet(f"{water.totalMl:,} ml{of}")], spacing=0,
                                         expand=True), *actions]),
                 faint(sources) if sources else ft.Container(visible=False)]
    return card(ft.Column(parts, spacing=6), padding=ft.Padding.only(left=16, right=12, top=10, bottom=10))
