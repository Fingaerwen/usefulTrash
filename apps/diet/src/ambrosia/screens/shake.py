"""The protein shake (apps/diet/docs/plan.md AM12.3), opened from the top of the add screen:

    ←  Protein shake                              30 g of your powder
    [ Protein in this shake (g): 24 ]             typed for each shake, flavours differ
    THIS ADDS 120 kcal · P 24 g · F 1.5 g · C 3 g · 600 ml water   (the water adds itself, AM12.4)
    Breakfast  Lunch  Dinner  Snacks              [ + Add to Lunch ]
    ┌ YOUR POWDER, ONE SHAKE                   ✎ ┐   its values a serving, placeholders until you set them
    └ 30 g · 120 kcal · P 24 g · F 1.5 g · C 3 g ┘

A shake you logged opens here too (AM12.2), with its protein and meal to change, Save and Delete, or only to look at
on a day the phone can't edit any more. Its other values stay as they were logged.
"""

import flet as ft

from ambrosia.rules.foods import mealNames, meals
from ambrosia.rules.today import shakeWaterMl
from ambrosia.screens.common import Notice, backButton, dayText
from ambrosia.screens.look import (
    card,
    faint,
    field,
    header,
    iconButton,
    label,
    mainButton,
    pill,
    quiet,
    screen,
    softButton,
    statTile,
)

powderFields = (("powderG", "Powder g"), ("kcal", "kcal"), ("proteinG", "Protein g"), ("fatG", "Fat g"),
                ("carbsG", "Carbs g"))


def _number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


@ft.component
def ShakeScreen(app, model):
    draft = model.shake
    typed, setTyped = ft.use_state(_number(draft.proteinG) if draft else "")  # hooks first, always (Flet's rule)
    meal, setMeal = ft.use_state(draft.meal if draft else "lunch")
    if draft is None:
        return screen([])
    opened = draft.logId is not None
    if opened and draft.logged is not None:  # as logged: the shake's values then
        whole = draft.logged.values
        powderG, kcal, fatG, carbsG = draft.logged.grams, whole.kcal, whole.fatG, whole.carbsG
    else:
        values = model.shakeValues
        powderG, kcal, fatG, carbsG = values.powderG, values.kcal, values.fatG, values.carbsG
    try:
        proteinG = float(typed.replace(",", "."))
        if not 0 <= proteinG <= powderG:
            raise ValueError
        tile = statTile("This entry" if opened else "This adds", f"{kcal:,.0f} kcal",
                        f"P {_number(proteinG)} g · F {_number(fatG)} g · C {_number(carbsG)} g · "
                        f"{shakeWaterMl} ml water", expand=False, size=26)
    except ValueError:
        proteinG = None
        tile = faint(f"Type the protein in grams, at most the {_number(powderG)} g of powder.")

    async def save(e):
        if proteinG is not None:
            await app.saveShakeEntry(proteinG, meal)

    async def delete(e):
        await app.deleteOpened()

    top = header("Protein shake", f"{_number(powderG)} g of your powder", leading=backButton(app))
    when = quiet(dayText(draft.date), size=14) if opened or draft.date != app.localToday() else None
    if draft.readOnly:
        return screen([top, quiet(f"{mealNames[draft.meal]} · {dayText(draft.date)}", size=14), tile,
                       faint("Read only: the phone edits the last 7 days, the PC view edits any day.")])
    buttons = (ft.Row([mainButton("Save", save, icon=ft.Icons.CHECK, disabled=proteinG is None, expand=True),
                       softButton("Delete", delete, icon=ft.Icons.DELETE_OUTLINE)], spacing=8) if opened else
               mainButton(f"Add to {mealNames[meal]}", save, icon=ft.Icons.ADD, disabled=proteinG is None))
    parts = [
        top,
        when or ft.Container(visible=False),
        Notice(app, model),
        field("Protein in this shake (g)", typed, lambda e: setTyped(e.control.value)),
        tile,
        label("Meal"),
        ft.Row([pill(mealNames[option], option == meal, on_click=lambda e, option=option: setMeal(option))
                for option in meals], spacing=6, wrap=True),
        ft.Container(height=4),
        buttons,
    ]
    if not opened:
        parts.append(PowderCard(app, model, lambda protein: setTyped(_number(protein))))
    return screen(parts)


@ft.component
def PowderCard(app, model, newProtein):
    """Your powder's values for one shake, with ✎ to set them. Placeholders until you do (AM12.3)."""
    values = model.shakeValues
    editing, setEditing = ft.use_state(False)
    typed, setTyped = ft.use_state({})

    def edit(e):
        setTyped({key: _number(getattr(values, key)) for key, _ in powderFields})
        setEditing(not editing)

    def setter(key: str):
        return lambda e: setTyped({**typed, key: e.control.value})

    async def save(e):
        if await app.saveShakeValues(typed):
            setEditing(False)
            newProtein(app.model.shakeValues.proteinG)

    parts: list[ft.Control] = [
        ft.Row([label("Your powder, one shake"), ft.Container(expand=True),
                iconButton(ft.Icons.EDIT_OUTLINED, "Set your powder's values", edit)]),
        quiet(f"{_number(values.powderG)} g · {_number(values.kcal)} kcal · P {_number(values.proteinG)} g · "
              f"F {_number(values.fatG)} g · C {_number(values.carbsG)} g", size=14),
    ]
    if model.shakeIsPlaceholder:
        parts.append(faint("These are placeholders: set your powder's values with the pencil. Shakes logged before "
                           "that keep them."))
    if editing:
        parts += [
            ft.Row([field(name, typed.get(key, ""), setter(key), expand=True) for key, name in powderFields[:2]],
                   spacing=12),
            ft.Row([field(name, typed.get(key, ""), setter(key), expand=True) for key, name in powderFields[2:]],
                   spacing=12),
            mainButton("Save the powder", save),
        ]
    return card(ft.Column(parts, spacing=8), padding=ft.Padding.only(left=16, right=8, top=8, bottom=14))
