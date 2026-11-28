"""The premade protein shake's rules (ambrosia/rules/shake.py, apps/diet/docs/plan.md AM12.3)."""

import pytest

from ambrosia.rules.foods import FoodProblem, LoggedFood, Values
from ambrosia.rules.shake import (
    ShakeValues,
    checkShake,
    isShake,
    loggedProtein,
    placeholder,
    shakeFood,
    shakeFoodId,
    shakeValues,
    withProtein,
)
from usefulTestKit import userA, userB


def testTheShakeHasOneIdPerAccount():
    assert shakeFoodId(userA) == shakeFoodId(userA) != shakeFoodId(userB)
    assert isShake(shakeFoodId(userA), userA) and not isShake(shakeFoodId(userA), userB)
    assert not isShake(shakeFoodId(userA), "")


def testItsValuesAServingGoInAndOutPer100G():
    values = ShakeValues(powderG=33, kcal=127, proteinG=25, fatG=1.8, carbsG=3.4)
    food = shakeFood("id", values)
    assert food.servingG == 33 and food.unit == "g" and food.source == "label" and food.name == "Protein shake"
    assert food.per100.proteinG == pytest.approx(75.7575, abs=1e-3)
    assert shakeValues(food) == values
    assert shakeValues(None) == placeholder


def testValuesNoPowderCouldHoldAreRefused():
    checkShake(placeholder)
    for wrong, words in ((ShakeValues(0, 0, 0, 0, 0), "powder must be above 0"),
                         (ShakeValues(30, 120, 24, 1.5, -1), "Carbs can't be below 0"),
                         (ShakeValues(30, 120, 28, 2, 3), "can't weigh more than the 30 g of powder"),
                         (ShakeValues(30, 300, 24, 1.5, 3), "can't hold 300 kcal")):
        with pytest.raises(FoodProblem, match=words):
            checkShake(wrong)


def testEachShakeHasItsOwnProteinAndTheRestAsSet():
    food = withProtein(shakeFood("id", placeholder), 21)
    one = food.per100.scaled(food.servingG)
    assert one.proteinG == pytest.approx(21) and one.kcal == pytest.approx(120) and one.carbsG == pytest.approx(3)
    with pytest.raises(FoodProblem, match="between 0 and the 30 g of powder"):
        withProtein(shakeFood("id", placeholder), 31)


def testALoggedShakesProtein():
    import datetime as dt

    log = LoggedFood("log", dt.date(2026, 11, 26), "breakfast", dt.datetime(2026, 11, 26, 8, tzinfo=dt.UTC), "id",
                     "Protein shake", Values(400, 83.33, 5, 10), 30, portion="servings", portionCount=1)
    assert loggedProtein(log) == 25.0
