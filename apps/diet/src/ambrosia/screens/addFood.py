"""Adding food (apps/diet/docs/plan.md 4a, 4b, AM2.2–AM2.4, AM5.2), as sketched in the design round:

    ←  Add to Lunch                 Add: Scan · Search · Recent (the PC view: search and a typed barcode)
    [ Search foods: chicken breast ]
    YOUR FOODS        Chicken, breast, boneless…   112 kcal · … · eaten 12 times   +
    GENERIC (USDA, OFFLINE)                        Chicken, breast, meat and skin, raw …
    PACKAGED (OPEN FOOD FACTS)                     Chicken Breast Fillets · Tesco …  (phone only)

    ←  Chicken, breast, boneless, skinless, raw    How much: Grams · Servings · Part of the pack
    [ 200 ]  100 g  150 g  200 g  250 g            THIS ADDS 224 kcal · P 45 g · F 4 g · C 0 g
    Breakfast  Lunch  Dinner  Snacks               [ + Add to Lunch ]

    ←  Type it from the label                     name, brand, per 100 g (or ml), serving and pack size
"""

import flet as ft

from ambrosia.model import Found
from ambrosia.rules.foods import FoodProblem, gramsFor, mealNames, meals, packText
from ambrosia.screens.common import Notice, backButton, dayText
from ambrosia.sources.genericFoods import credit as genericCredit
from ambrosia.sources.openFoodFacts import credit as packagedCredit
from ambrosia.screens.look import (
    card,
    faint,
    field,
    header,
    label,
    listCard,
    listRow,
    mainButton,
    pill,
    quiet,
    screen,
    segments,
    softButton,
    statTile,
)


def _forWhen(app, model) -> str | None:
    date = model.addDate
    return None if date is None or date == app.localToday() else dayText(date)


@ft.component
def AddScreen(app, model):
    meal = mealNames.get(model.addMeal, "")
    parts: list[ft.Control] = [header(f"Add to {meal}", _forWhen(app, model), leading=backButton(app)),
                               Notice(app, model)]
    if app.mode == "phone":
        parts.append(segments([("scan", "Scan"), ("search", "Search"), ("recent", "Recent")], model.addMode,
                              app.setAddMode))
    mode = model.addMode if app.mode == "phone" else "search"
    if mode == "scan":
        parts += [ScanPart(app, model)]
    elif mode == "recent":
        parts += [label("Recent"), RecentCard(app, model.recent) if model.recent
                  else faint("Nothing eaten yet: search or scan a food first.")]
    else:
        parts += [SearchPart(app, model)]
        if app.mode == "pc":
            parts.append(BarcodePart(app))
    parts.append(ft.Row([faint("Not there?"), ft.TextButton("Type it from the label", on_click=lambda e: app.typeLabel(
        "Type it from the pack's label, per 100 g (or 100 ml). It's saved as one of your foods."))], spacing=0))
    parts.append(faint(f"{genericCredit} {packagedCredit}", size=11))  # what their licences ask for
    return screen(parts)


def resultsCard(app, found: tuple[Found, ...]) -> ft.Container:
    return listCard([
        listRow(ft.Row([ft.Column([ft.Text(item.title, size=14, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                   faint(item.detail)], spacing=2, expand=True),
                        ft.Icon(ft.Icons.ADD, size=20, color=ft.Colors.OUTLINE)]),
                on_click=lambda e, item=item: app.pickFound(item), tooltip=f"Add {item.title}")
        for item in found])


@ft.component
def RecentCard(app, recent: tuple[Found, ...]):
    """Recent foods: "again" has the same amount as last time in one tap. The row opens How much."""
    def again(item: Found):
        async def tap(e):
            await app.again(item)
        return tap

    return listCard([
        listRow(ft.Row([ft.Column([ft.Text(item.title, size=14, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                   faint(item.detail)], spacing=2, expand=True),
                        softButton(f"{item.last.shortAmount} again", again(item), tooltip=f"{item.title}: the same again")
                        if item.last else ft.Container(visible=False)], spacing=8),
                on_click=lambda e, item=item: app.pickFound(item), tooltip=f"Add {item.title}")
        for item in recent])


@ft.component
def SearchPart(app, model):
    async def search(e):
        await app.search(model.searchWords)

    results = model.results
    searchField = field("Search foods", model.searchWords, lambda e: app.typeSearch(e.control.value), expand=True,
                        number=False)
    searchField.on_submit = search
    parts: list[ft.Control] = [ft.Row([searchField, softButton("Search", search, icon=ft.Icons.SEARCH)], spacing=8)]
    if results is None:
        return ft.Column(parts, spacing=12)
    sections = [("Your foods", results.yours), ("Generic (USDA, offline)", results.generic)]
    if app.mode == "phone":
        sections.append(("Packaged (Open Food Facts)", results.packaged))
    for title, found in sections:
        if found:
            parts += [label(title), resultsCard(app, found)]
    if results.packagedNote and app.mode == "phone":
        parts += [label("Packaged (Open Food Facts)") if not results.packaged else ft.Container(visible=False),
                  faint(results.packagedNote)]
    if not (results.yours or results.generic or results.packaged or results.packagedNote):
        parts.append(faint("Nothing found."))
    return ft.Column(parts, spacing=12)


@ft.component
def ScanPart(app, model):
    async def scan(e):
        await app.scan()

    return ft.Column([
        card(ft.Column([ft.Icon(ft.Icons.QR_CODE_SCANNER, size=44, color=ft.Colors.TERTIARY),
                        quiet("Point the camera at the barcode. Your own foods are found without the internet.",
                              size=14, text_align=ft.TextAlign.CENTER),
                        mainButton("Scan a barcode", scan, icon=ft.Icons.CAMERA_ALT, disabled=bool(model.busy))],
                       spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20),
        quiet(model.busy) if model.busy else ft.Container(visible=False),
        BarcodePart(app),
    ], spacing=12)


@ft.component
def BarcodePart(app):
    """A barcode typed from the pack: the PC view's way in, and the phone's when the camera can't read it."""
    typed, setTyped = ft.use_state("")

    async def lookUp(e):
        await app.useBarcode(typed)

    return ft.Row([field("Or type the barcode", typed, lambda e: setTyped(e.control.value), expand=True),
                   softButton("Look up", lookUp)], spacing=8)


@ft.component
def AmountScreen(app, model):
    """How much (AM2.4): grams, servings or part of the pack, what it adds, and the meal."""
    picked = model.picked
    portion, setPortion = ft.use_state(picked.portion if picked else "grams")  # hooks first, always (Flet's rule)
    typed, setTyped = ft.use_state(f"{picked.count:g}" if picked else "100")
    meal, setMeal = ft.use_state(picked.meal if picked else "lunch")
    if picked is None:
        return screen([])
    food = picked.food
    unit = food.unit
    choices = [("grams", "Grams" if unit == "g" else "Millilitres")]
    if food.servingG:
        choices.append(("servings", "Servings"))
    if food.packG:
        choices.append(("pack", "Part of the pack"))

    def choose(kind: str) -> None:
        setPortion(kind)
        setTyped({"grams": "100", "servings": "1", "pack": "1"}[kind])

    try:
        count = float(typed.replace(",", "."))
        grams = gramsFor(food, portion, count)
        adds = food.per100.scaled(grams)
        addsText = statTile("This adds", f"{adds.kcal:,.0f} kcal",
                            f"P {adds.proteinG:.0f} g · F {adds.fatG:.0f} g · C {adds.carbsG:.0f} g"
                            + ("" if portion == "grams" else f" · {grams:g} {unit}"), expand=False, size=26)
    except (ValueError, FoodProblem) as problem:
        count, addsText = None, faint(str(problem) if isinstance(problem, FoodProblem) else "Type a number.")
    quick = {"grams": [(f"{value} {unit}", str(value)) for value in (50, 100, 150, 200, 250)],
             "servings": [(f"{value}", str(value)) for value in (1, 2, 3)],
             "pack": [(packText(value).replace(" of the pack", "").replace(" the pack", ""), f"{value:g}")
                      for value in (0.25, 0.5, 1)]}[portion]

    async def save(e):
        if count is not None:
            await app.saveAmount(portion, count, meal)

    v = food.per100
    return screen([
        header(food.title, f"{v.kcal:.0f} kcal · P {v.proteinG:g} · F {v.fatG:g} · C {v.carbsG:g} per 100 {unit}",
               leading=backButton(app)),
        Notice(app, model),
        segments(choices, portion, choose) if len(choices) > 1 else ft.Container(visible=False),
        field({"grams": "Grams" if unit == "g" else "Millilitres", "servings": "Servings",
               "pack": "Packs (0.5 = half)"}[portion], typed,
              lambda e: setTyped(e.control.value)),
        ft.Row([pill(text, typed == value, on_click=lambda e, value=value: setTyped(value)) for text, value in quick],
               spacing=6, wrap=True),
        addsText,
        label("Meal"),
        ft.Row([pill(mealNames[option], option == meal, on_click=lambda e, option=option: setMeal(option))
                for option in meals], spacing=6, wrap=True),
        ft.Container(height=4),
        mainButton(f"Add to {mealNames[meal]}", save, icon=ft.Icons.ADD, disabled=count is None),
    ])


@ft.component
def LabelScreen(app, model):
    """Typing a food from its label (AM2.3), once: the next scan of its barcode finds it."""
    draft = model.label
    keys = ("name", "brand", "kcal", "proteinG", "fatG", "carbsG", "servingG", "packG", "unit")
    values, setValues = ft.use_state({key: getattr(draft, key) if draft else "" for key in keys})
    if draft is None:
        return screen([])

    def setter(key: str):
        return lambda e: setValues({**values, key: e.control.value})

    async def save(e):
        await app.saveLabel(values)

    unit = values["unit"]
    return screen([
        header("Type it from the label", leading=backButton(app)),
        quiet(draft.why, size=14),
        Notice(app, model),
        field("Name", values["name"], setter("name"), number=False),
        field("Brand (optional)", values["brand"], setter("brand"), number=False),
        ft.Row([label(f"Per 100 {unit}"), ft.Container(expand=True),
                pill("g", unit == "g", on_click=lambda e: setValues({**values, "unit": "g"})),
                pill("ml", unit == "ml", on_click=lambda e: setValues({**values, "unit": "ml"}))], spacing=6),
        ft.Row([field("kcal", values["kcal"], setter("kcal"), expand=True),
                field("Protein g", values["proteinG"], setter("proteinG"), expand=True)], spacing=12),
        ft.Row([field("Fat g", values["fatG"], setter("fatG"), expand=True),
                field("Carbs g", values["carbsG"], setter("carbsG"), expand=True)], spacing=12),
        label("Sizes (optional)"),
        ft.Row([field(f"Serving {unit}", values["servingG"], setter("servingG"), expand=True),
                field(f"Pack {unit}", values["packG"], setter("packG"), expand=True)], spacing=12),
        faint(f"Barcode {draft.barcode}") if draft.barcode else ft.Container(visible=False),
        ft.Container(height=4),
        mainButton("Save and choose the amount", save),
    ])
