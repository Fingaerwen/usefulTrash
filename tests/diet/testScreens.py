"""Ambrosia's screens drawn as Flet draws them (tests/screenTestKit.py): every screen in both modes without a
layout Flutter refuses (its grey box) or a character the PC view's font can't write (TS1.1), and the main
paths pressed through."""

import asyncio
import datetime as dt
import json

import pytest
from ambrosiaStandIn import StandInApp
from screenTestKit import draw, find, layoutProblems, press, type_, undrawable, useLoop, visibleTexts

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
    loop.run_until_complete(app.search("nutella"))
    drawn(app)
    loop.run_until_complete(app.useBarcode("3017620422003"))
    drawn(app)  # How much
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
