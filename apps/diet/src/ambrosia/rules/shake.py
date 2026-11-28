"""The premade protein shake (apps/diet/docs/plan.md AM12.3): one serving of your powder, always the same amount
because you measure it with the same cup. Its values a serving start as placeholders and you set them in the app.
The protein is typed for each shake, since flavours differ, and the rest stays as set.

It's kept as one of your foods (a label food, so the cloud needs nothing new) with an ID worked out from your
account, so the phone and the PC view share one shake. Its values are stored per 100 g like every food, and shown a
serving at a time. Nothing here reads a database or the clock.
"""

import uuid
from dataclasses import dataclass

from ambrosia.rules.foods import Food, FoodProblem, LoggedFood, Values
from usefulShared.tables import idNamespace

shakeName = "Protein shake"
maxPowderG = 500.0  # one shake. More is a typing mistake


@dataclass(frozen=True, slots=True)
class ShakeValues:
    """One shake: the powder's weight and what it holds."""

    powderG: float
    kcal: float
    proteinG: float
    fatG: float
    carbsG: float


placeholder = ShakeValues(powderG=30, kcal=120, proteinG=24, fatG=1.5, carbsG=3)  # until you set yours (AM12.3)


def shakeFoodId(userId: str) -> str:
    """The shake's food ID, the same on every device of your account."""
    return str(uuid.uuid5(idNamespace, f"foods/{uuid.UUID(userId)}/proteinShake"))


def isShake(foodId: str, userId: str) -> bool:
    return bool(userId) and foodId == shakeFoodId(userId)


def checkShake(values: ShakeValues) -> None:
    """Values a shake can have, in plain words when it can't: some powder, nothing below 0, the macros together no
    heavier than the powder (a little more is label rounding), and no more kcal than pure fat would hold."""
    if not 0 < values.powderG <= maxPowderG:
        raise FoodProblem(f"The powder must be above 0 and at most {maxPowderG:.0f} g.")
    for name, amount in (("kcal", values.kcal), ("Protein", values.proteinG), ("Fat", values.fatG),
                         ("Carbs", values.carbsG)):
        if amount < 0:
            raise FoodProblem(f"{name} can't be below 0.")
    if values.proteinG + values.fatG + values.carbsG > values.powderG * 1.05:
        raise FoodProblem(f"Protein, fat and carbs together can't weigh more than the {values.powderG:g} g of powder.")
    if values.kcal > values.powderG * 9.5:
        raise FoodProblem(f"{values.powderG:g} g of powder can't hold {values.kcal:g} kcal.")


def shakeFood(foodId: str, values: ShakeValues) -> Food:
    """The shake as a food: its values per 100 g of powder, a serving being one shake."""
    factor = 100 / values.powderG
    per100 = Values(values.kcal * factor, values.proteinG * factor, values.fatG * factor, values.carbsG * factor)
    return Food(foodId, "label", shakeName, per100, servingG=values.powderG)


def shakeValues(food: Food | None) -> ShakeValues:
    """The shake's values a serving, from its food. The placeholders while it isn't saved yet."""
    if food is None or not food.servingG:
        return placeholder
    one = food.per100.scaled(food.servingG)
    return ShakeValues(food.servingG, round(one.kcal, 1), round(one.proteinG, 1), round(one.fatG, 1),
                       round(one.carbsG, 1))


def withProtein(food: Food, proteinG: float) -> Food:
    """The shake with this shake's protein, the rest as set. Refused when the powder couldn't hold it."""
    powderG = food.servingG or placeholder.powderG
    if not 0 <= proteinG <= powderG:
        raise FoodProblem(f"A shake's protein must be between 0 and the {powderG:g} g of powder.")
    per100 = food.per100
    return Food(food.foodId, food.source, food.name,
                Values(per100.kcal, proteinG * 100 / powderG, per100.fatG, per100.carbsG), food.brand, food.barcode,
                food.usdaId, food.unit, food.servingG, food.packG)


def loggedProtein(log: LoggedFood) -> float:
    """The protein a logged shake held, to 0.1 g."""
    return round(log.per100.proteinG * log.grams / 100, 1)
