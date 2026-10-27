"""Foods, amounts and what you ate (Ambrosia plan 4a, 4e, AM2.4, AM2.5)."""

import datetime as dt

import pytest

from ambrosia.rules.barcodes import checkDigitFits, cleanBarcode, isShopCode
from ambrosia.rules.foods import (
    Food,
    FoodProblem,
    LoggedFood,
    Values,
    amountText,
    byMeal,
    checkValues,
    dayTotal,
    foodRowId,
    gramsFor,
    searchYourFoods,
    yourFoods,
)
from usefulTestKit import userA, userB

chicken = Food("f1", "usda", "Chicken, breast, boneless, skinless, raw", Values(112, 22.5, 1.9, 0), usdaId=2646170)
skyr = Food("f2", "openFoodFacts", "Skyr Natural", Values(62, 11, 0.2, 4), "Milbona", "4056489012345",
            servingG=150, packG=450)
monday = dt.date(2026, 10, 26)


def at(hour: int, minute: int = 0, day: dt.date = monday) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=dt.UTC)


def logged(food: Food, grams: float, meal: str = "lunch", when: dt.datetime | None = None, logId: str = "l1",
           day: dt.date = monday, portion: str = "grams", count: float | None = None) -> LoggedFood:
    return LoggedFood(logId, day, meal, when or at(12), food.foodId, food.name, food.per100, grams, food.brand,
                      food.unit, portion, count)


def testValuesScaleWithTheAmount():
    eaten = chicken.per100.scaled(200)
    assert (eaten.kcal, eaten.proteinG, eaten.fatG, eaten.carbsG) == pytest.approx((224, 45, 3.8, 0))


def testAmountsInGramsServingsOrPartOfThePack():
    assert gramsFor(skyr, "grams", 170) == 170
    assert gramsFor(skyr, "servings", 1) == 150
    assert gramsFor(skyr, "pack", 0.5) == 225
    assert gramsFor(skyr, "servings", 1 / 3) == 50  # rounded to 0.1 g


@pytest.mark.parametrize("portion, count, why", [
    ("servings", 1, "no serving size"), ("pack", 1, "no pack size"), ("grams", 0, "above 0"),
    ("grams", -5, "above 0"), ("grams", float("nan"), "above 0"), ("grams", 20_000, "over 10 kg"),
    ("spoons", 1, "isn't a way"),
])
def testAmountsThatCantBeWorkedOut(portion, count, why):
    with pytest.raises(FoodProblem, match=why):
        gramsFor(chicken, portion, count)


def testAmountsReadAsYouSaidThem():
    assert amountText(200) == "200 g"
    assert amountText(300, "ml") == "300 ml"
    assert amountText(150, portion="servings", count=1) == "1 serving (150 g)"
    assert amountText(300, portion="servings", count=2) == "2 servings (300 g)"
    assert amountText(225, portion="pack", count=0.5) == "half the pack (225 g)"
    assert amountText(1250.5) == "1,250.5 g"


@pytest.mark.parametrize("values, why", [
    (Values(950, 0, 100, 0), "kcal"), (Values(100, 120, 0, 0), "Protein"), (Values(100, 50, 40, 30), "together"),
])
def testImpossibleLabelValuesAreRefused(values, why):
    with pytest.raises(FoodProblem, match=why):
        checkValues(values)
    checkValues(Values(884, 0, 100, 0))  # olive oil is possible


def testFoodIdsComeFromWhatTheFoodIs():
    """The phone and the PC view saving the same food make one row (4e)."""
    assert foodRowId(userA, barcode="4056489012345") == foodRowId(userA, barcode="4056489012345")
    assert foodRowId(userA, barcode="4056489012345") != foodRowId(userB, barcode="4056489012345")
    assert foodRowId(userA, usdaId=2646170) != foodRowId(userA, barcode="2646170")
    assert foodRowId(userA) is None  # a label typed without a barcode: a random ID


def testADayInItsMealsInTheOrderLogged():
    logs = [logged(skyr, 150, "snacks", at(15), "a"), logged(chicken, 200, "lunch", at(13), "b"),
            logged(chicken, 100, "lunch", at(12), "c"), logged(chicken, 50, "lunch", at(12), "d", monday + dt.timedelta(1))]
    meals = byMeal(logs, monday)
    assert [log.logId for log in meals["lunch"]] == ["c", "b"]
    assert [log.logId for log in meals["snacks"]] == ["a"] and meals["breakfast"] == meals["dinner"] == ()
    assert dayTotal(logs, monday).kcal == pytest.approx(112 * 3 + 93)


def testRecentIsTheMostRecentlyEatenFirstAndSearchTheMostEaten():
    other = Food("f3", "label", "Protein quark, vanilla", Values(72, 10, 0.2, 7.5))
    logs = [logged(chicken, 200, when=at(12), logId="a"), logged(chicken, 200, when=at(18), logId="b"),
            logged(skyr, 150, when=at(20), logId="c")]
    used = yourFoods([chicken, skyr, other], logs)
    assert [item.food.foodId for item in used] == ["f2", "f1", "f3"]  # skyr last eaten, quark never
    assert [item.uses for item in used] == [1, 2, 0]
    assert [item.food.foodId for item in searchYourFoods(used, "chick bre")] == ["f1"]
    assert [item.food.foodId for item in searchYourFoods(used, "milbona")] == ["f2"]  # the brand counts
    assert searchYourFoods(used, "  ") == []


def testBarcodesAreCheckedByTheirLastDigit():
    assert cleanBarcode(" 3017620422003 ") == "3017620422003"  # Nutella
    assert checkDigitFits("5449000000996") and checkDigitFits("96385074")  # Coca-Cola, an EAN-8
    for text, why in (("301762042200A", "only digits"), ("12345", "8, 12, 13 or 14"),
                      ("3017620422004", "last digit")):
        with pytest.raises(ValueError, match=why):
            cleanBarcode(text)


def testShopsOwnCodesAreRecognised():
    """AM5.4: GS1's ranges for codes a shop gives its own items."""
    assert isShopCode("2000000000008")  # Open Food Facts had it as someone's pecorino
    assert isShopCode("0212345678903") and isShopCode("0412345678909")
    assert isShopCode("212345678901") and isShopCode("412345678901")  # UPC-A
    assert isShopCode("20123451") and isShopCode("01234565")  # EAN-8
    assert not isShopCode("3017620422003") and not isShopCode("5449000000996") and not isShopCode("96385074")
