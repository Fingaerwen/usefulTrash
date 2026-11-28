"""Ambrosia's screens drawn as Flet draws them (tests/screenTestKit.py): every screen in both modes without a
layout Flutter refuses (its grey box) or a character the PC view's font can't write (TS1.1), and the main
paths pressed through."""

import asyncio
import datetime as dt
import json

import pytest
from ambrosiaStandIn import StandInApp
from flet import BaseControl
from screenTestKit import (
    draw,
    find,
    label,
    layoutProblems,
    press,
    redraw,
    type_,
    undrawable,
    useLoop,
    visibleTexts,
    walk,
)

from ambrosia.screens.addFood import AmountScreen
from ambrosia.screens.shake import PowderCard, ShakeScreen
from ambrosia.screens.root import AmbrosiaApp
from usefulTestKit import FakeClock, userA

nutella = {"code": "3017620422003", "product_name": "Nutella", "brands": "Ferrero", "product_quantity": 400,
           "product_quantity_unit": "g", "serving_quantity": 15,
           "nutriments": {"energy-kcal_100g": 539, "proteins_100g": 6.3, "fat_100g": 30.9, "carbohydrates_100g": 57.5}}
targetsFile = {
    "format": "ambrosiaTargets", "version": 1, "name": "Bulk from 26 Oct",
    "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "restDay": {"kcal": 2900, "proteinG": 160, "fatG": 90, "carbsG": 365}, "waterMl": 3000,
    "bulkCheck": {"firstBlockStart": "2026-10-26", "rateKgPerWeek": {"min": 0.15, "max": 0.35}, "stepKcal": 150,
                  "bigStepKcal": 250, "bigGainKg": 2.0, "minWeighIns": 2, "changeMacro": "carbs",
                  "regularWeeks": 8, "bigMissWeeks": 4},
}


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    useLoop(loop)
    yield loop
    loop.close()


def makeApp(mode="phone"):
    clock = FakeClock(dt.datetime(2026, 10, 26, 11, 0, tzinfo=dt.UTC))
    return StandInApp(userA, clock, lambda: clock().date(), mode, products={"3017620422003": nutella})


def drawn(app):
    root = draw(AmbrosiaApp, app, app.model)
    problems = layoutProblems(root)
    assert not problems, problems
    assert undrawable(root) == set(), undrawable(root)
    return root


def everyScreen(app, loop):
    """Visits each screen and tab, drawing each one."""
    for tab in ("today", "week", "targets") + (("history", "backup") if app.mode == "pc" else ()):
        app.selectTab(tab)
        drawn(app)
    app.selectTab("today")
    app.openAdd("lunch")
    for mode in ("search", "scan", "recent"):
        app.setAddMode(mode)
        drawn(app)
    app.openShake()
    drawn(app)  # the protein shake (AM12.3)
    app.openAdd("lunch")
    loop.run_until_complete(app.search("nutella"))
    drawn(app)
    loop.run_until_complete(app.useBarcode("3017620422003"))
    drawn(app)  # How much
    app.pick(app.model.picked.food, 523)
    drawn(app)  # How much with Whole pack
    app.typeLabel("Type it from the label.", barcode="2000000000008")
    drawn(app)
    app.checkTargets(json.dumps(targetsFile).encode())
    drawn(app)
    app.openHistory()
    drawn(app)
    app.editDay(app.localToday())
    drawn(app)
    app.openProblems()
    drawn(app)


@pytest.mark.parametrize("mode", ["phone", "pc"])
def testEveryScreenDraws(mode, loop):
    everyScreen(makeApp(mode), loop)


def testAddingAFoodThroughTheScreens(loop):
    app = makeApp()
    root = drawn(app)
    press(find(root, "Add to Breakfast", "IconButton"))
    assert app.model.screen == "add" and app.model.addMeal == "breakfast"
    root = drawn(app)
    type_(find(root, "Search foods", "TextField"), "nutella")
    root = drawn(app)
    press(find(root, "Search", "Button"))
    root = drawn(app)
    assert "Nutella · Ferrero" in visibleTexts(root)
    press(find(root, "Add Nutella · Ferrero"))
    root = drawn(app)
    assert app.model.screen == "amount" and "This adds".upper() in visibleTexts(root)
    press(find(root, "Add to Breakfast", "Button"))
    root = drawn(app)
    assert app.model.screen == "main" and "Nutella · Ferrero" in visibleTexts(root)
    assert "EATEN" in visibleTexts(root) and "81 kcal" in visibleTexts(root)  # 15 g of Nutella, no targets yet


def testWholePackFillsInAWeighedPacksWeight(loop):
    """AM11.1: the amount starts as usual, and Whole pack fills in the weight from the pack's barcode."""
    app = makeApp()
    app.openAdd("dinner")
    loop.run_until_complete(app.useBarcode("2301234505230"))
    loop.run_until_complete(app.saveLabel({"name": "Minced beef", "kcal": "180", "proteinG": "20", "fatG": "11",
                                           "carbsG": "0"}))
    amount = draw(AmountScreen, app, app.model)
    assert "180 kcal" in visibleTexts(amount)  # 100 g to start with
    [wholePack] = [control for control in walk(amount) if type(control).__name__ == "Container"
                   and isinstance(control.content, BaseControl) and label(control.content) == "Whole pack · 523 g"]
    press(wholePack)  # the pill around the words
    redraw(amount)  # the amount is the screen's own state, kept by a redraw
    assert "941 kcal" in visibleTexts(amount)
    press(find(amount, "Add to Dinner", "Button"))
    [log] = [row for row in app.rows["foodLogs"].values() if not row["deleted"]]
    assert log["grams"] == 523


def testWaterAndTheSummaryWithoutTargets(loop):
    app = makeApp()
    root = drawn(app)
    assert "No targets yet: import your targets file on the Targets tab." in visibleTexts(root)
    press(find(root, "+250 ml", "Button"))
    root = drawn(app)
    assert "250 ml" in visibleTexts(root)


def testImportingTargetsThroughTheScreens(loop):
    app = makeApp()
    app.checkTargets(json.dumps(targetsFile).encode())
    root = drawn(app)
    press(find(root, "Import", "Button"))
    root = drawn(app)
    assert app.model.tab == "targets" and "3,200" in visibleTexts(root)
    app.selectTab("today")
    root = drawn(app)
    assert any(text.startswith("of 3,200") for text in visibleTexts(root))


def buttons(root) -> list[str]:
    return [label(control) for control in walk(root) if type(control).__name__ == "Button"]


def tooltips(root) -> list[str]:
    return [control.tooltip for control in walk(root) if isinstance(getattr(control, "tooltip", None), str)]


def testTheDayStripShowsAndEditsTheWeeksOtherDays(loop):
    """AM12.1, like Talon's DY1.1: this week's seven days under the header. A day ahead is looked at and logged
    under its own date, without water. A swipe moves along the strip, stopping at its ends, and today's chip goes
    back."""
    from types import SimpleNamespace

    app = makeApp()  # Monday 26 Oct
    monday = app.localToday()
    root = drawn(app)
    days = [tip for tip in tooltips(root) if tip.startswith("Show ") and tip.split()[1].endswith("day")]
    assert days == ["Show Monday (today)", "Show Tuesday", "Show Wednesday", "Show Thursday", "Show Friday",
                    "Show Saturday", "Show Sunday"]
    press(find(root, "Show Wednesday"))
    root = drawn(app)
    texts = visibleTexts(root)
    assert "Wednesday" in texts and "28 Oct · in 2 days · training day" in texts
    assert "+250 ml" not in buttons(root) and "Set the day's water" not in tooltips(root)  # not drunk yet
    press(find(root, "Add to Dinner", "IconButton"))
    assert app.model.screen == "add" and app.model.addDate == monday + dt.timedelta(days=2)
    loop.run_until_complete(app.useBarcode("3017620422003"))
    press(find(drawn(app), "Add to Dinner", "Button"))
    [log] = [row for row in app.rows["foodLogs"].values() if not row["deleted"]]
    assert log["date"] == monday + dt.timedelta(days=2) and app.model.screen == "main"
    root = drawn(app)
    assert "Nutella · Ferrero" in visibleTexts(root) and app.model.dayShown == monday + dt.timedelta(days=2)
    assert app.model.today.eaten.kcal == 0  # today's untouched

    gesture = next(control for control in walk(root) if type(control).__name__ == "GestureDetector")
    gesture.on_horizontal_drag_end(SimpleNamespace(primary_velocity=-800))  # a flick to the left: the next day
    assert app.model.dayShown == monday + dt.timedelta(days=3)
    gesture.on_horizontal_drag_end(SimpleNamespace(primary_velocity=-100))  # too slow: nothing
    assert app.model.dayShown == monday + dt.timedelta(days=3)
    for _ in range(5):
        app.shiftDay(1)
    assert app.model.dayShown == monday + dt.timedelta(days=6)  # the end of the strip
    press(find(drawn(app), "Show Monday (today)"))
    assert app.model.dayView is None and "Monday 26 Oct · training day" in visibleTexts(drawn(app))
    app.shiftDay(-1)  # Monday is the strip's start
    assert app.model.dayView is None


def testTheDayStripEditsADayEarlierInTheWeek(loop):
    """AM12.1: on Thursday, Monday is in the strip, with its own water."""
    app = makeApp()
    app.clock.now += dt.timedelta(days=3)
    app.refresh()
    monday = app.localToday() - dt.timedelta(days=3)
    press(find(drawn(app), "Show Monday"))
    root = drawn(app)
    assert "26 Oct · 3 days ago · training day" in visibleTexts(root) and "+250 ml" in buttons(root)
    press(find(root, "+250 ml", "Button"))
    assert app.state.water == {monday: 250}


def testANewWeekGoesBackToToday(loop):
    """A day shown last week has left the strip, so Today shows today again."""
    app = makeApp()
    app.showDay(app.localToday() + dt.timedelta(days=6))
    app.clock.now += dt.timedelta(days=7)
    app.refresh()
    assert app.model.dayShown is None and app.model.weekDays[0] == app.localToday()


def pillNamed(root, text: str):
    """The tappable part of a pill (the container around its words)."""
    [found] = [control for control in walk(root) if type(control).__name__ == "Container"
               and isinstance(control.content, BaseControl) and label(control.content) == text
               and control.on_click is not None]
    return found


def logNutella(app, loop, date=None, meal="breakfast"):
    """One serving (15 g) of Nutella, from its barcode."""
    app.openAdd(meal, date)
    loop.run_until_complete(app.useBarcode("3017620422003"))
    loop.run_until_complete(app.saveAmount("servings", 1, meal))


def testOpeningAnEntryChangesItsAmountAndMeal(loop):
    """AM12.2: a tap on something logged opens it with what it adds, the amount and the meal. Save keeps the
    serving's size, and the day shows again."""
    app = makeApp()
    logNutella(app, loop)
    press(find(drawn(app), "Nutella · Ferrero: change or delete"))
    assert app.model.screen == "amount" and app.model.picked.logId is not None
    drawn(app)
    root = draw(AmountScreen, app, app.model)  # the amount is the screen's own state, kept by redrawing it
    texts = visibleTexts(root)
    assert "THIS ENTRY" in texts and "81 kcal" in texts and "Add to Breakfast" not in buttons(root)
    [amount] = [control for control in walk(root) if type(control).__name__ == "TextField"]
    assert amount.label == "Servings" and amount.value == "1"
    type_(amount, "2")
    redraw(root)
    press(pillNamed(root, "Lunch"))
    redraw(root)
    assert "162 kcal" in visibleTexts(root)
    press(find(root, "Save", "Button"))
    [log] = [row for row in app.rows["foodLogs"].values() if not row["deleted"]]
    assert (log["meal"], log["portion"], log["portionCount"], log["grams"]) == ("lunch", "servings", 2, 30)
    assert app.model.screen == "main" and app.model.picked is None


def testDeletingAnOpenedEntry(loop):
    app = makeApp()
    logNutella(app, loop)
    press(find(drawn(app), "Nutella · Ferrero: change or delete"))
    press(find(drawn(app), "Delete", "Button"))
    assert [row["deleted"] for row in app.rows["foodLogs"].values()] == [True] and app.model.screen == "main"


def testBackFromAnOpenedEntryGoesToItsDay(loop):
    """From an opened entry the back arrow leads to the day it's on, Today or History's day, not to adding food."""
    app = makeApp()
    logNutella(app, loop)
    press(find(drawn(app), "Nutella · Ferrero: change or delete"))
    press(find(drawn(app), "Back", "IconButton"))
    assert app.model.screen == "main" and app.model.picked is None
    app.openHistory()
    app.editDay(app.localToday())
    press(find(drawn(app), "Nutella · Ferrero: change or delete"))
    press(find(drawn(app), "Back", "IconButton"))
    assert app.model.screen == "history" and app.model.historyDay is not None


def testADayThePhoneCantEditOpensItsEntriesToLookAtOnly(loop):
    """AM5.5: the phone edits the last 7 days. An older entry opens without Save or Delete, and Save does nothing."""
    app = makeApp()
    old = app.localToday() - dt.timedelta(days=8)
    logNutella(app, loop, old)
    app.openHistory()
    app.showMonth(0)
    app.editDay(old)
    press(find(drawn(app), "Nutella · Ferrero: look at it"))
    root = drawn(app)
    assert "Read only: the phone edits the last 7 days, the PC view edits any day." in visibleTexts(root)
    assert buttons(root) == [] and "81 kcal" in visibleTexts(root)
    loop.run_until_complete(app.saveAmount("servings", 3, "lunch"))
    [log] = list(app.rows["foodLogs"].values())
    assert log["grams"] == 15 and not log["deleted"]


def testAddingAShakeAndSettingThePowderThroughTheScreens(loop):
    """AM12.3: the shake at the top of the add screen, its protein typed for this shake, and the powder's values set
    with the pencil. The protein field starts again from the new value."""
    app = makeApp()
    press(find(drawn(app), "Add to Breakfast", "IconButton"))
    press(find(drawn(app), "Add a protein shake"))
    assert app.model.screen == "shake"
    shake = draw(ShakeScreen, app, app.model)
    assert "These are placeholders: set your powder's values with the pencil. Shakes logged before that keep them." \
        in visibleTexts(shake)

    told = []
    powder = draw(PowderCard, app, app.model, told.append)  # its own state, kept by redrawing it alone
    press(find(powder, "Set your powder's values", "IconButton"))
    redraw(powder)
    for name, value in (("Powder g", "32"), ("kcal", "125"), ("Protein g", "25.5"), ("Fat g", "1.6"),
                        ("Carbs g", "2.9")):
        fields = {control.label: control for control in walk(powder) if type(control).__name__ == "TextField"}
        type_(fields[name], value)
        redraw(powder)
    press(find(powder, "Save the powder", "Button"))
    assert told == [25.5] and not app.model.shakeIsPlaceholder

    shake = draw(ShakeScreen, app, app.model)
    assert "32 g · 125 kcal · P 25.5 g · F 1.6 g · C 2.9 g" in visibleTexts(shake)
    [protein] = [control for control in walk(shake) if type(control).__name__ == "TextField"]
    assert protein.label == "Protein in this shake (g)" and protein.value == "25.5"
    type_(protein, "23")
    redraw(shake)
    assert "P 23 g · F 1.6 g · C 2.9 g" in visibleTexts(shake)
    press(find(shake, "Add to Breakfast", "Button"))
    assert app.model.screen == "main" and app.model.today.eaten.proteinG == pytest.approx(23, abs=0.01)
    root = drawn(app)
    assert "Protein shake" in visibleTexts(root) and "1 serving (32 g)" in visibleTexts(root)
