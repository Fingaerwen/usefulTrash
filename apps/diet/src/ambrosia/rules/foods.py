"""Foods and what you ate (apps/diet/docs/plan.md 4a, 4d, 4e; AM2.1–AM2.5): values per 100 g (or 100 ml for a
drink), amounts in grams, servings or part of the pack, and the totals of a meal and a day.

A food row is your copy of a food you've used; a food log row is one thing you ate, with a copy of the food's
name and values at the time, so editing the food later never rewrites a past day (4e). Rows are plain dicts
with the columns of 4e; nothing here reads a database or the clock.
"""

import datetime as dt
import math
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from usefulShared.tables import idNamespace

meals = ("breakfast", "lunch", "dinner", "snacks")  # AM2.5, in the day's order
mealNames = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snacks": "Snacks"}
portions = ("grams", "servings", "pack")  # AM2.4: grams, servings, or part of the pack
sources = ("openFoodFacts", "usda", "label")
maxGrams = 10_000.0  # one entry; more is a typing mistake


class FoodProblem(ValueError):
    """A food or amount that can't be used, in plain words for the screen."""


@dataclass(frozen=True, slots=True)
class Values:
    """kcal and the three macros, per 100 g (a food) or for an amount (a log, a meal, a day)."""

    kcal: float = 0.0
    proteinG: float = 0.0
    fatG: float = 0.0
    carbsG: float = 0.0

    def scaled(self, grams: float) -> "Values":
        """What `grams` of a food with these values per 100 g holds."""
        factor = grams / 100
        return Values(self.kcal * factor, self.proteinG * factor, self.fatG * factor, self.carbsG * factor)

    def __add__(self, other: "Values") -> "Values":
        return Values(self.kcal + other.kcal, self.proteinG + other.proteinG, self.fatG + other.fatG,
                      self.carbsG + other.carbsG)


def total(values: Iterable[Values]) -> Values:
    result = Values()
    for value in values:
        result = result + value
    return result


@dataclass(frozen=True, slots=True)
class Food:
    """A food with its values per 100 g (100 ml when unit is "ml"; 1 ml counts as 1 g, 4e)."""

    foodId: str
    source: str  # openFoodFacts, usda or label
    name: str
    per100: Values
    brand: str = ""
    barcode: str = ""
    usdaId: int | None = None
    unit: str = "g"
    servingG: float | None = None
    packG: float | None = None

    @property
    def title(self) -> str:
        """The name, with the brand after a dot when there is one."""
        return f"{self.name} · {self.brand}" if self.brand else self.name


def foodFromRow(row: Mapping[str, Any]) -> Food:
    return Food(row["id"], row["source"], row["name"], Values(row["kcal"], row["proteinG"], row["fatG"], row["carbsG"]),
                row.get("brand") or "", row.get("barcode") or "", row.get("usdaId"), row.get("unit") or "g",
                row.get("servingG"), row.get("packG"))


def foodRowId(userId: str, barcode: str = "", usdaId: int | None = None) -> str | None:
    """A food's row ID, worked out from what it is, so the phone and the PC view saving the same food make one
    row, never two (4e): from its barcode, or from its USDA number. None for a label typed without a barcode,
    which gets a random ID."""
    if barcode:
        key = f"foods/{uuid.UUID(userId)}/barcode/{barcode}"
    elif usdaId is not None:
        key = f"foods/{uuid.UUID(userId)}/usda/{usdaId}"
    else:
        return None
    return str(uuid.uuid5(idNamespace, key))


def checkValues(values: Values) -> None:
    """Values per 100 g must be possible: kcal 0 to 900 (pure fat), each macro 0 to 100 g, and the macros
    together at most 100 g (a little more is label rounding)."""
    if not 0 <= values.kcal <= 900:
        raise FoodProblem("kcal per 100 g must be between 0 and 900.")
    for name, grams in (("Protein", values.proteinG), ("Fat", values.fatG), ("Carbs", values.carbsG)):
        if not 0 <= grams <= 100:
            raise FoodProblem(f"{name} per 100 g must be between 0 and 100 g.")
    if values.proteinG + values.fatG + values.carbsG > 105:
        raise FoodProblem("Protein, fat and carbs together can't be more than 100 g per 100 g.")


# --- Amounts -------------------------------------------------------------------------------------

def gramsFor(food: Food, portion: str, count: float) -> float:
    """The grams (ml for a drink) an amount stands for: grams as typed, servings times the serving size, or a
    part of the pack (0.5 = half). Rounded to 0.1 g. Raises FoodProblem when it can't be worked out."""
    if portion not in portions:
        raise FoodProblem("That isn't a way to say how much.")
    if not isinstance(count, (int, float)) or isinstance(count, bool) or not math.isfinite(count) or count <= 0:
        raise FoodProblem("The amount must be a number above 0.")
    if portion == "grams":
        grams = float(count)
    elif portion == "servings":
        if not food.servingG:
            raise FoodProblem("This food has no serving size: give the amount in grams.")
        grams = count * food.servingG
    else:
        if not food.packG:
            raise FoodProblem("This food has no pack size: give the amount in grams.")
        grams = count * food.packG
    grams = round(grams, 1)
    if grams <= 0:
        raise FoodProblem("The amount must be a number above 0.")
    if grams > maxGrams:
        raise FoodProblem(f"That's over {maxGrams / 1000:.0f} kg in one go: check the amount.")
    return grams


def amountText(grams: float, unit: str = "g", portion: str = "grams", count: float | None = None) -> str:
    """How an amount reads: "200 g", "300 ml", "1 serving (120 g)", "half the pack (200 g)"."""
    weight = f"{_number(grams)} {unit}"
    if portion == "servings" and count:
        return f"{_number(count)} serving{'' if count == 1 else 's'} ({weight})"
    if portion == "pack" and count:
        return f"{packText(count)} ({weight})"
    return weight


def packText(count: float) -> str:
    """Part of the pack in words (the PC view's font has no ¼ or ½)."""
    words = {0.25: "a quarter of the pack", 0.5: "half the pack", 0.75: "three quarters of the pack",
             1: "the whole pack"}
    if count in words:
        return words[count]
    return f"{_number(count)} packs" if count > 1 else f"{_number(count)} of the pack"


def _number(value: float) -> str:
    """A number without a needless ".0": 200, 37.5, 1,250."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# --- What you ate ---------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LoggedFood:
    """One thing you ate (a foodLogs row that isn't deleted), with the food's values as they were then."""

    logId: str
    date: dt.date
    meal: str
    loggedAt: dt.datetime
    foodId: str
    name: str
    per100: Values
    grams: float
    brand: str = ""
    unit: str = "g"
    portion: str = "grams"
    portionCount: float | None = None

    @property
    def values(self) -> Values:
        return self.per100.scaled(self.grams)

    @property
    def title(self) -> str:
        return f"{self.name} · {self.brand}" if self.brand else self.name

    @property
    def amount(self) -> str:
        return amountText(self.grams, self.unit, self.portion, self.portionCount)

    @property
    def shortAmount(self) -> str:
        """The amount without the grams behind a serving or a pack: "200 g", "1 serving", "half the pack"."""
        return amountText(self.grams, self.unit, self.portion, self.portionCount).split(" (")[0]


def loggedFromRow(row: Mapping[str, Any]) -> LoggedFood:
    return LoggedFood(row["id"], row["date"], row["meal"], row["loggedAt"], row["foodId"], row["name"],
                      Values(row["kcal"], row["proteinG"], row["fatG"], row["carbsG"]), row["grams"],
                      row.get("brand") or "", row.get("unit") or "g", row.get("portion") or "grams",
                      row.get("portionCount"))


def byMeal(logs: Iterable[LoggedFood], date: dt.date) -> dict[str, tuple[LoggedFood, ...]]:
    """A day's food in its four meals, each in the order you logged it."""
    day = sorted((log for log in logs if log.date == date), key=lambda log: (log.loggedAt, log.logId))
    return {meal: tuple(log for log in day if log.meal == meal) for meal in meals}


def dayTotal(logs: Iterable[LoggedFood], date: dt.date) -> Values:
    return total(log.values for log in logs if log.date == date)


# --- Your foods: Recent and search ----------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class UsedFood:
    """One of your foods with how often and when you last ate it."""

    food: Food
    uses: int
    lastUsed: dt.datetime | None


def yourFoods(foods: Iterable[Food], logs: Iterable[LoggedFood]) -> list[UsedFood]:
    """Your foods, the most recently eaten first (Recent), then the ones never logged, by name."""
    uses: dict[str, int] = {}
    last: dict[str, dt.datetime] = {}
    for log in logs:
        uses[log.foodId] = uses.get(log.foodId, 0) + 1
        if log.foodId not in last or log.loggedAt > last[log.foodId]:
            last[log.foodId] = log.loggedAt
    used = [UsedFood(food, uses.get(food.foodId, 0), last.get(food.foodId)) for food in foods]
    eaten = sorted((item for item in used if item.lastUsed), key=lambda item: item.lastUsed, reverse=True)
    never = sorted((item for item in used if not item.lastUsed), key=lambda item: item.food.title.lower())
    return eaten + never


def searchYourFoods(used: Iterable[UsedFood], words: str, limit: int = 10) -> list[UsedFood]:
    """Your foods with a word starting with each word searched (name or brand), the most eaten first."""
    wanted = _words(words)
    if not wanted:
        return []
    found = [item for item in used
             if all(any(word.startswith(part) for word in _words(item.food.title)) for part in wanted)]
    return sorted(found, key=lambda item: (-item.uses, item.food.title.lower()))[:limit]


def _words(text: str) -> list[str]:
    return re.findall(r"[0-9a-zà-ÿ]+", text.lower())
