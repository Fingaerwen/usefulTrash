"""What Ambrosia's phone app and PC view share (plan 3b): the model, the facts, adding food, water, targets,
History and the Problems page. Each mode adds where rows come from and go to: sign-in, the phone's database
and sync, built at max effort (gate 2). Until then a stand-in store keeps the rows (tests and screenshots).
"""

import datetime as dt
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from ambrosia.actions import ActionRefused, AmbrosiaActions
from ambrosia.model import AppModel, Found, LabelDraft, Picked, SearchResults, appName, appVersion
from ambrosia.rules.barcodes import cleanBarcode, isShopCode
from ambrosia.rules.foods import Food, UsedFood, Values, searchYourFoods
from ambrosia.rules.targets import FileCheck, readTargetsFile, targetsFromJson
from ambrosia.rules.week import mondayOf
from ambrosia.sources.genericFoods import GenericFoods
from ambrosia.sources.openFoodFacts import FoodSourceError, OpenFoodFacts, Product
from ambrosia.state import AmbrosiaState
from usefulShared.platform.appLog import AppLog

waterStepMl = 250  # the water card's +250 ml (4a)
phoneEditableDays = 7  # History: the phone edits the last 7 days (AM5.5)


class AmbrosiaBase:
    """The shared part of both controllers."""

    mode = "phone"  # or "pc": the PC view has no scanner and no packaged-food search by name (AM5.2)

    def __init__(self, services: Any, log: AppLog, clock: Callable[[], dt.datetime],
                 localToday: Callable[[], dt.date], userId: str, foodSource: OpenFoodFacts | None = None,
                 genericFoods: GenericFoods | None = None):
        self.services = services
        self.log = log
        self.clock = clock
        self.localToday = localToday
        self.userId = userId
        self.model = AppModel()
        self.state = AmbrosiaState()
        self.actions = AmbrosiaActions(self, self.state, userId, clock)
        self.foodSource = foodSource or OpenFoodFacts(appVersion)
        self.genericFoods = genericFoods or GenericFoods()

    # --- What each mode provides -------------------------------------------------------------

    def rowsByTable(self) -> dict[str, list[dict[str, Any]]]:
        raise NotImplementedError

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """The RowStore the actions save through: save, then redraw."""
        raise NotImplementedError

    # --- The facts ---------------------------------------------------------------------------

    def refresh(self) -> None:
        """Works out the facts again and redraws what changed."""
        self.state.load(self.rowsByTable())
        today = self.localToday()
        self.model.today = self.state.dayView(today)
        monday = mondayOf(today) - dt.timedelta(weeks=self.model.weekOffset)
        self.model.week = self.state.weekView(monday, today)
        self.model.targets = self.state.targetsView(today)
        lastLogs = {}
        for log in sorted(self.state.logs, key=lambda log: log.loggedAt):
            lastLogs[log.foodId] = log
        self.model.recent = tuple(replace(self._found(item), last=lastLogs.get(item.food.foodId))
                                  for item in self.state.yourFoods() if item.lastUsed)[:20]
        if self.model.historyMonth is not None:
            self.model.historyDays = tuple(self.state.historyDays(self.model.historyMonth, today))
        if self.model.historyDay is not None:
            self.model.historyDay = self._dayForHistory(self.model.historyDay.date)

    async def _act(self, work) -> bool:
        """Runs an action. A refusal shows as a notice. True if it went through."""
        try:
            await work
        except ActionRefused as refused:
            self.model.notice = str(refused)
            return False
        return True

    def selectTab(self, tab: str) -> None:
        self.model.tab = tab

    def showWeek(self, offset: int) -> None:
        self.model.weekOffset = max(0, offset)
        self.refresh()

    def back(self) -> None:
        """The back arrow: from How much or a label to adding food, from there (or anything else) to the tabs."""
        if self.model.screen in ("amount", "label"):
            self.model.screen = "add"
        elif self.model.screen == "add" and self.model.historyDay is not None:
            self.model.screen = "history"
        else:
            self.model.screen = "main"
        self.model.notice = ""

    # --- Adding food (4a, 4d) ----------------------------------------------------------------

    def openAdd(self, meal: str, date: dt.date | None = None) -> None:
        self.model.addMeal, self.model.addDate = meal, date or self.localToday()
        self.model.addMode = "search" if self.mode == "pc" else self.model.addMode
        self.model.results, self.model.searchWords, self.model.notice = None, "", ""
        self.model.screen = "add"

    def setAddMode(self, mode: str) -> None:
        self.model.addMode = mode

    def typeSearch(self, words: str) -> None:
        self.model.searchWords = words

    def _found(self, item: UsedFood) -> Found:
        times = f"eaten {item.uses} times" if item.uses > 1 else "eaten once" if item.uses else "not eaten yet"
        return Found(item.food, item.food.title, f"{_valuesText(item.food)} · {times}")

    async def search(self, words: str) -> None:
        """Your foods and the generic foods at once (offline). Then, on the phone, packaged foods (AM5.2)."""
        words = words.strip()
        if not words:
            self.model.results = None
            return
        yours = tuple(self._found(item) for item in searchYourFoods(self.state.yourFoods(), words))
        known = {found.food.usdaId for found in yours if found.food and found.food.usdaId}
        generic = tuple(Found(food, food.name, f"{_valuesText(food)} · USDA")
                        for food in self.genericFoods.search(words) if food.usdaId not in known)
        phone = self.mode == "phone"
        self.model.results = SearchResults(words, yours, generic, (), "Searching…" if phone else "")
        if not phone:
            return
        try:
            products = await self.foodSource.search(words)
        except FoodSourceError as problem:
            self.model.results = SearchResults(words, yours, generic, (), str(problem))
            return
        packaged = tuple(self._product(product) for product in products if product.name)
        if self.model.results is not None and self.model.results.words == words:  # not replaced by a newer search
            self.model.results = SearchResults(words, yours, generic, packaged, "" if packaged else "Nothing found.")

    def _product(self, product: Product) -> Found:
        title = f"{product.name} · {product.brand}" if product.brand else product.name
        if product.complete:
            return Found(product.asFood(), title, _valuesText(product.asFood()))
        return Found(None, title, "values missing: type them from the label", product)

    async def scan(self) -> None:
        """The phone's camera (AM5.1: ZXing)."""
        answer = await self.services.scanner.scanOpen()
        if answer.get("status") == "cancelled":
            return
        if answer.get("status") != "ok":
            self.model.notice = "The scanner couldn't start. Type the barcode instead."
            self.log.problem("scan", "The scanner couldn't start.", f"{answer.get('errorType')}: {answer.get('message')}")
            return
        await self.useBarcode(str(answer.get("barcode", "")))

    async def useBarcode(self, text: str) -> None:
        """A scanned or typed barcode: your food if you have it. A shop's own code goes straight to typing the
        label (AM5.4). Otherwise Open Food Facts, and typing the label if it doesn't have it all (AM2.3)."""
        try:
            barcode = cleanBarcode(text)
        except ValueError as problem:
            self.model.notice = str(problem)
            return
        yours = self.state.foodWithBarcode(barcode)
        if yours is not None:
            self.pick(yours)
            return
        if isShopCode(barcode):
            self.typeLabel(f"Barcode {barcode} is a shop's own code: type it from the label once, and the next scan "
                           "finds it.", barcode=barcode)
            return
        self.model.busy = "Looking it up…"
        try:
            product = await self.foodSource.lookUp(barcode)
        except FoodSourceError as problem:
            self.model.notice = str(problem)
            return
        finally:
            self.model.busy = ""
        if product is None:
            self.typeLabel(f"Barcode {barcode} isn't in Open Food Facts. Type it from the label once; the next scan "
                           "finds it.", barcode=barcode)
        elif not product.complete:
            self.typeLabel("Open Food Facts doesn't have all four values for this one: type the rest from the label.",
                           product=product)
        else:
            self.pick(product.asFood())

    def pick(self, food: Food) -> None:
        """How much (4a): a serving if the food has one, else 100 g (or ml)."""
        portion, count = ("servings", 1.0) if food.servingG else ("grams", 100.0)
        self.model.picked = Picked(food, self.model.addMeal, self.model.addDate or self.localToday(), portion, count)
        self.model.notice = ""
        self.model.screen = "amount"

    def pickFound(self, found: Found) -> None:
        if found.food is not None:
            self.pick(found.food)
        elif found.product is not None:
            self.typeLabel("Open Food Facts doesn't have all four values for this one: type the rest from the "
                           "label.", product=found.product)

    async def again(self, found: Found) -> None:
        """Recent's one tap (4a): the same food and amount as last time, into the meal being added to."""
        last = found.last
        if found.food is None or last is None:
            return
        count = last.portionCount if last.portion != "grams" and last.portionCount else last.grams
        date = self.model.addDate or self.localToday()
        if await self._act(self.actions.logFood(date, self.model.addMeal, found.food, last.portion, count)):
            self.model.screen = "history" if self.model.historyDay is not None else "main"

    async def saveAmount(self, portion: str, count: float, meal: str) -> None:
        picked = self.model.picked
        if picked is None:
            return
        if await self._act(self.actions.logFood(picked.date, meal, picked.food, portion, count)):
            self.model.picked = None
            self.model.screen = "history" if self.model.historyDay is not None else "main"

    def typeLabel(self, why: str, barcode: str = "", product: Product | None = None) -> None:
        def text(value: float | None) -> str:
            return "" if value is None else f"{value:g}"

        draft = LabelDraft(why, barcode, meal=self.model.addMeal, date=self.model.addDate)
        if product is not None:
            draft = LabelDraft(why, product.barcode, product.name, product.brand, product.unit, text(product.kcal),
                               text(product.proteinG), text(product.fatG), text(product.carbsG),
                               text(product.servingG), text(product.packG), self.model.addMeal, self.model.addDate)
        self.model.label, self.model.notice = draft, ""
        self.model.screen = "label"

    async def saveLabel(self, fields: dict[str, str]) -> None:
        """The label's values as typed: per 100 g (or ml), then How much."""
        draft = self.model.label
        if draft is None:
            return
        try:
            numbers = {key: _number(fields.get(key, ""), required) for key, required in
                       (("kcal", True), ("proteinG", True), ("fatG", True), ("carbsG", True),
                        ("servingG", False), ("packG", False))}
        except ValueError as problem:
            self.model.notice = str(problem)
            return
        food = Food("", "label", fields.get("name", "").strip(), Values(numbers["kcal"], numbers["proteinG"],
                                                                      numbers["fatG"], numbers["carbsG"]),
                    fields.get("brand", "").strip(), draft.barcode, unit=fields.get("unit") or draft.unit,
                    servingG=numbers["servingG"], packG=numbers["packG"])
        try:
            saved = await self.actions.saveLabel(food)
        except ActionRefused as refused:
            self.model.notice = str(refused)
            return
        self.model.label = None
        self.pick(saved)

    # --- Water, and changing what's logged ---------------------------------------------------

    async def addWater(self, date: dt.date | None = None) -> None:
        await self._act(self.actions.addWater(date or self.localToday(), waterStepMl))

    async def setWater(self, date: dt.date, ml: int) -> None:
        await self._act(self.actions.setWater(date, ml))

    async def deleteLog(self, logId: str) -> None:
        await self._act(self.actions.deleteLog(logId))

    async def changeLog(self, logId: str, meal: str, portion: str, count: float) -> None:
        await self._act(self.actions.changeLog(logId, meal, portion, count))

    # --- Targets (AM3.1, 4f) -----------------------------------------------------------------

    async def pickTargetsFile(self) -> None:
        files = await self.services.filePicker.pick_files(dialog_title="Pick your targets file", with_data=True,
                                                          file_type=ft.FilePickerFileType.CUSTOM,
                                                          allowed_extensions=["json"])
        if files:
            self.checkTargets(files[0].bytes or b"")

    def checkTargets(self, content: bytes | str) -> None:
        """Reads a targets file and shows it with the current targets next to it, before anything changes."""
        checked: FileCheck = readTargetsFile(content)
        self.model.targetsCheck = checked
        self.model.targetsData = json.loads(content) if checked.targets is not None else None
        self.model.screen = "importTargets"

    async def confirmTargets(self) -> None:
        data = self.model.targetsData
        if data is None or targetsFromJson(data).targets is None:
            return
        if await self._act(self.actions.importTargets(data, self.localToday())):
            self.model.targetsCheck, self.model.targetsData = None, None
            self.model.screen, self.model.tab = "main", "targets"

    # --- History (AM5.5) ---------------------------------------------------------------------

    def openHistory(self) -> None:
        self.model.historyMonth = self.localToday().replace(day=1)
        self.model.historyDay = None
        self.model.screen = "history" if self.mode == "phone" else "main"
        if self.mode == "pc":
            self.model.tab = "history"
        self.refresh()

    def showMonth(self, monthsBack: int) -> None:
        month = self.localToday().replace(day=1)
        for _ in range(max(0, monthsBack)):
            month = (month - dt.timedelta(days=1)).replace(day=1)
        self.model.historyMonth = month
        self.refresh()

    def _dayForHistory(self, date: dt.date):
        editable = self.mode == "pc" or (self.localToday() - date).days < phoneEditableDays
        return self.state.dayView(date, editable)

    def editDay(self, date: dt.date) -> None:
        self.model.historyDay = self._dayForHistory(date)

    def closeDay(self) -> None:
        self.model.historyDay = None

    # --- Problems (DG1.1) --------------------------------------------------------------------

    def openProblems(self) -> None:
        check = self.log.check()
        lines = [f"{appName} {appVersion} ({self.mode}) · not syncing yet: the cloud part comes with gate 2",
                 f"Log check: {check.lines} lines, {check.tokenShapedStrings} token-shaped strings"]
        recent = self.log.entries()
        lines += ["Recent problems:", *[f"  {entry.at} {entry.area}: {entry.plainWords}" for entry in recent]] \
            if recent else ["Recent problems: none"]
        self.model.problems = tuple(lines)
        self.model.screen = "problems"


def _valuesText(food: Food) -> str:
    values = food.per100
    return (f"{values.kcal:.0f} kcal · P {values.proteinG:g} · F {values.fatG:g} · C {values.carbsG:g} "
            f"per 100 {food.unit}")


def _number(text: str, required: bool) -> float | None:
    text = text.strip().replace(",", ".")
    if not text:
        if required:
            raise ValueError("Fill in kcal, protein, fat and carbs per 100 g, as on the label.")
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{text!r} isn't a number.") from None
