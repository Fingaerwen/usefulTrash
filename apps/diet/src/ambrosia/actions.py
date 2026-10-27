"""Everything Ambrosia changes, as rows (plan 3b: one write path). Each action builds the rows with the columns of
apps/diet/docs/plan.md 4e and hands them to the store in one go, so they're saved (and later sent) together.
The store stamps edit times. IDs follow 4e: a food from its barcode or USDA number, a day's water from the date.

Saving these rows for real (the phone's database, the cloud upgrade and sync) is built at max effort (gate 2).
Until then the store is a stand-in.
"""

import datetime as dt
import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from ambrosia.rules.foods import Food, FoodProblem, checkValues, foodRowId, gramsFor, meals, portions
from ambrosia.rules.targets import targetsFromJson
from ambrosia.state import AmbrosiaState
from usefulShared.tables import idNamespace, newRowId

maxWaterMl = 20_000  # a day's total


class ActionRefused(Exception):
    """An entry that can't be saved, in plain words for the screen."""


class RowStore(Protocol):
    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]: ...


def waterRowId(userId: str, date: dt.date) -> str:
    """A day's water row ID, made like every one-per-day row (usefulShared.tables.dayRowId): the phone and the PC
    view adding water the same day write one row."""
    return str(uuid.uuid5(idNamespace, f"water/{uuid.UUID(userId)}/{date.isoformat()}"))


def foodRow(food: Food, foodId: str, userId: str) -> dict[str, Any]:
    """A foods row (4e). Values are kept to the precision the cloud keeps: kcal to 0.1, grams to 0.01."""
    values = food.per100
    return {"id": foodId, "userId": userId, "deleted": False, "source": food.source, "barcode": food.barcode or None,
            "usdaId": food.usdaId, "name": food.name, "brand": food.brand or None, "unit": food.unit,
            "kcal": round(values.kcal, 1), "proteinG": round(values.proteinG, 2), "fatG": round(values.fatG, 2),
            "carbsG": round(values.carbsG, 2), "servingG": _grams(food.servingG), "packG": _grams(food.packG)}


def _grams(value: float | None) -> float | None:
    return round(value, 1) if value else None


class AmbrosiaActions:
    def __init__(self, store: RowStore, state: AmbrosiaState, userId: str, clock: Callable[[], dt.datetime]):
        self.store = store
        self.state = state
        self.userId = userId
        self.clock = clock

    def _foodId(self, food: Food) -> str:
        return food.foodId or foodRowId(self.userId, food.barcode, food.usdaId) or newRowId()

    # --- Food --------------------------------------------------------------------------------

    async def logFood(self, date: dt.date, meal: str, food: Food, portion: str, count: float) -> str:
        """Logs what you ate. A food you haven't used before becomes one of your foods in the same save.
        Returns the log's ID."""
        if meal not in meals:
            raise ActionRefused("That isn't one of the day's meals.")
        try:
            grams = gramsFor(food, portion, count)
        except FoodProblem as problem:
            raise ActionRefused(str(problem)) from None
        foodId = self._foodId(food)
        edits: list[tuple[str, dict[str, Any]]] = []
        existing = self.state.row("foods", foodId)
        if existing is None or existing["deleted"]:
            edits.append(("foods", foodRow(food, foodId, self.userId)))
        logId = newRowId()
        values = food.per100
        edits.append(("foodLogs", {
            "id": logId, "userId": self.userId, "deleted": False, "date": date, "meal": meal,
            "loggedAt": self.clock(), "foodId": foodId, "portion": portion,
            "portionCount": None if portion == "grams" else round(float(count), 2), "grams": grams,
            "name": food.name, "brand": food.brand or None, "unit": food.unit, "kcal": round(values.kcal, 1),
            "proteinG": round(values.proteinG, 2), "fatG": round(values.fatG, 2), "carbsG": round(values.carbsG, 2)}))
        await self.store.saveRows(edits)
        return logId

    async def saveLabel(self, food: Food) -> Food:
        """A food typed from its label (AM2.3), saved as one of your foods so the next scan finds it. A barcode's
        food keeps its ID, so typing over a wrong Open Food Facts entry corrects it."""
        if not food.name.strip():
            raise ActionRefused("Give the food a name.")
        try:
            checkValues(food.per100)
        except FoodProblem as problem:
            raise ActionRefused(str(problem)) from None
        for size, what in ((food.servingG, "serving"), (food.packG, "pack")):
            if size is not None and not 0 < size <= 10_000:
                raise ActionRefused(f"The {what} size must be above 0 and at most 10 kg.")
        foodId = self._foodId(food)
        saved = Food(foodId, "label", food.name.strip(), food.per100, food.brand.strip(), food.barcode, None,
                     food.unit, food.servingG, food.packG)
        await self.store.saveRows([("foods", foodRow(saved, foodId, self.userId))])
        return saved

    async def changeLog(self, logId: str, meal: str, portion: str, count: float) -> None:
        """Changes how much of a food you ate, or the meal. Servings and packs keep the size they had when logged."""
        row = self.state.row("foodLogs", logId)
        if row is None or row["deleted"]:
            raise ActionRefused("That entry is gone.")
        if meal not in meals or portion not in portions:
            raise ActionRefused("That isn't one of the day's meals.")
        unitGrams = row["grams"] / row["portionCount"] if row["portion"] != "grams" and row["portionCount"] else None
        if portion == "grams":
            grams = count
        elif portion == row["portion"] and unitGrams:
            grams = count * unitGrams
        else:
            food = self.state.foods.get(row["foodId"])
            if food is None:
                raise ActionRefused("This food isn't among your foods any more: give the amount in grams.")
            try:
                grams = gramsFor(food, portion, count)
            except FoodProblem as problem:
                raise ActionRefused(str(problem)) from None
        if not 0 < grams <= 10_000:
            raise ActionRefused("The amount must be above 0 and at most 10 kg.")
        await self.store.saveRows([("foodLogs", dict(row, meal=meal, portion=portion, grams=round(grams, 1),
                                                     portionCount=None if portion == "grams" else round(count, 2)))])

    async def deleteLog(self, logId: str) -> None:
        row = self.state.row("foodLogs", logId)
        if row is not None and not row["deleted"]:
            await self.store.saveRows([("foodLogs", dict(row, deleted=True))])

    # --- Water (AM2.6) -----------------------------------------------------------------------

    async def setWater(self, date: dt.date, ml: int) -> None:
        if isinstance(ml, bool) or not isinstance(ml, int) or not 0 <= ml <= maxWaterMl:
            raise ActionRefused(f"Water must be a whole number of ml from 0 to {maxWaterMl:,}.")
        rowId = waterRowId(self.userId, date)
        existing = self.state.row("water", rowId) or {}
        await self.store.saveRows([("water", {**existing, "id": rowId, "userId": self.userId, "deleted": False,
                                              "date": date, "ml": ml})])

    async def addWater(self, date: dt.date, ml: int) -> None:
        await self.setWater(date, min(maxWaterMl, self.state.water.get(date, 0) + ml))

    # --- Targets (AM3.1, 4f) -----------------------------------------------------------------

    async def importTargets(self, data: Any, today: dt.date) -> str:
        """Imports a checked targets file. It applies from today."""
        if targetsFromJson(data).targets is None:
            raise ActionRefused("This targets file has problems: fix them first.")
        importId = newRowId()
        await self.store.saveRows([("dietTargets", {"id": importId, "userId": self.userId, "deleted": False,
                                                    "importedAt": self.clock(), "effectiveDate": today,
                                                    "targetsJson": data})])
        return importId
