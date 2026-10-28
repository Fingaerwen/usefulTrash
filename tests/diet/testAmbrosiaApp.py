"""Ambrosia's flows on the stand-in store (plan 4a, 4d, 4e, 4f, AM2.2–AM2.6, AM5.2, AM5.4, AM5.5)."""

import asyncio
import copy
import datetime as dt
import json

import pytest
from ambrosiaStandIn import FakeFile, StandInApp

from ambrosia.actions import waterRowId
from ambrosia.rules.foods import foodRowId
from usefulTestKit import FakeClock, userA

monday = dt.date(2026, 10, 26)
nutella = {"code": "3017620422003", "product_name": "Nutella", "brands": "Ferrero", "product_quantity": 400,
           "product_quantity_unit": "g", "serving_quantity": 15,
           "nutriments": {"energy-kcal_100g": 539, "proteins_100g": 6.3, "fat_100g": 30.9, "carbohydrates_100g": 57.5}}
rye = {"code": "6411401015090", "product_name": "Rye bread", "brands": "Fazer",
       "nutriments": {"energy-kcal_100g": 250, "proteins_100g": 8}}
targetsFile = {
    "format": "ambrosiaTargets", "version": 1, "name": "Bulk from 26 Oct",
    "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
    "restDay": {"kcal": 2900, "proteinG": 160, "fatG": 90, "carbsG": 365}, "waterMl": 3000,
    "bulkCheck": {"firstBlockStart": "2026-10-26", "rateKgPerWeek": {"min": 0.15, "max": 0.35}, "stepKcal": 150,
                  "bigStepKcal": 250, "bigGainKg": 2.0, "minWeighIns": 2, "changeMacro": "carbs",
                  "regularWeeks": 8, "bigMissWeeks": 4},
}


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def clock():
    return FakeClock(dt.datetime(2026, 10, 26, 11, 0, tzinfo=dt.UTC))


def makeApp(clock, mode="phone", **options):
    return StandInApp(userA, clock, lambda: clock().date(), mode, products={"3017620422003": nutella,
                                                                            "6411401015090": rye}, **options)


def live(app, table):
    return [row for row in app.rows.get(table, {}).values() if not row["deleted"]]


def testSearchingFindsYourFoodsGenericFoodsAndOnThePhonePackagedOnes(clock):
    app = makeApp(clock)
    run(app.search("nutella"))
    results = app.model.results
    assert [found.title for found in results.packaged] == ["Nutella · Ferrero"] and results.packagedNote == ""
    run(app.search("chicken breast"))
    assert app.model.results.generic[0].title.startswith("Chicken, breast")
    assert app.model.results.packagedNote == "Nothing found."


def testThePcViewDoesntSearchPackagedFoodsByName(clock):
    """AM5.2: the PC view searches your foods and the generic foods only."""
    app = makeApp(clock, mode="pc")
    run(app.search("nutella"))
    assert app.model.results.packaged == () and app.model.results.packagedNote == ""
    assert not any("search.openfoodfacts.org" in url for url in app.net.asked)


def testLoggingAFoodMakesItOneOfYoursAndCountsTheDay(clock):
    app = makeApp(clock)
    app.openAdd("lunch")
    run(app.useBarcode("3017620422003"))
    assert app.model.screen == "amount" and app.model.picked.portion == "servings"  # it has a serving size
    run(app.saveAmount("servings", 2, "breakfast"))
    assert app.model.screen == "main"
    [food], [log] = live(app, "foods"), live(app, "foodLogs")
    assert food["id"] == foodRowId(userA, barcode="3017620422003") and food["source"] == "openFoodFacts"
    assert (log["meal"], log["grams"], log["portion"], log["portionCount"]) == ("breakfast", 30.0, "servings", 2.0)
    assert log["kcal"] == 539 and log["name"] == "Nutella" and log["loggedAt"] == clock()
    assert app.model.today.eaten.kcal == pytest.approx(539 * 0.3)
    # The next scan finds it among your foods, without asking Open Food Facts again.
    asked = len(app.net.asked)
    run(app.useBarcode("3017620422003"))
    assert len(app.net.asked) == asked and app.model.screen == "amount"


def testAnUnknownBarcodeOrAShopsCodeIsTypedFromTheLabel(clock):
    app = makeApp(clock)
    app.openAdd("dinner")
    run(app.useBarcode("4002239010306"))  # not in Open Food Facts
    assert app.model.screen == "label" and "isn't in Open Food Facts" in app.model.label.why
    run(app.useBarcode("2000000000008"))  # a shop's own code (AM5.4): Open Food Facts isn't asked
    assert app.model.screen == "label" and "shop's own code" in app.model.label.why
    assert not any("2000000000008" in url for url in app.net.asked)
    run(app.saveLabel({"name": "Deli ham", "kcal": "110", "proteinG": "18,5", "fatG": "4", "carbsG": "1",
                       "packG": "150"}))
    assert app.model.screen == "amount"
    [food] = live(app, "foods")
    assert (food["source"], food["barcode"], food["proteinG"], food["packG"]) == ("label", "2000000000008", 18.5, 150)
    run(app.saveAmount("pack", 0.5, "dinner"))
    assert live(app, "foodLogs")[0]["grams"] == 75
    run(app.useBarcode("2000000000008"))  # now it's yours
    assert app.model.screen == "amount" and app.model.picked.food.name == "Deli ham"


def testMissingValuesStartTheLabelWithWhatsKnown(clock):
    app = makeApp(clock)
    app.openAdd("lunch")
    run(app.useBarcode("6411401015090"))
    label = app.model.label
    assert app.model.screen == "label" and (label.name, label.brand, label.kcal, label.proteinG, label.fatG) == (
        "Rye bread", "Fazer", "250", "8", "")
    run(app.saveLabel({"name": "Rye bread", "kcal": "250", "proteinG": "8", "fatG": "", "carbsG": "45"}))
    assert app.model.notice == "Fill in kcal, protein, fat and carbs per 100 g, as on the label."
    run(app.saveLabel({"name": "Rye bread", "kcal": "250", "proteinG": "8", "fatG": "200", "carbsG": "45"}))
    assert "Fat per 100 g must be between 0 and 100 g" in app.model.notice


def testATypedBarcodeIsChecked(clock):
    app = makeApp(clock, mode="pc")
    run(app.useBarcode("3017620422004"))
    assert app.model.notice == "That barcode's last digit doesn't fit the others: check it against the pack."
    assert app.net.asked == []


def testChangingAndDeletingWhatYouAte(clock):
    app = makeApp(clock)
    app.openAdd("lunch")
    run(app.useBarcode("3017620422003"))
    run(app.saveAmount("servings", 1, "lunch"))
    [log] = live(app, "foodLogs")
    run(app.changeLog(log["id"], "snacks", "servings", 3))  # the serving size it was logged with
    [log] = live(app, "foodLogs")
    assert (log["meal"], log["grams"], log["portionCount"]) == ("snacks", 45.0, 3.0)
    run(app.changeLog(log["id"], "snacks", "grams", 20))
    assert live(app, "foodLogs")[0]["grams"] == 20 and live(app, "foodLogs")[0]["portionCount"] is None
    run(app.deleteLog(log["id"]))
    assert live(app, "foodLogs") == [] and app.model.today.eaten.kcal == 0


def testWaterAddsUpOnOneRowADay(clock):
    app = makeApp(clock)
    for _ in range(3):
        run(app.addWater())
    [row] = live(app, "water")
    assert row["ml"] == 750 and row["id"] == waterRowId(userA, monday) and app.model.today.waterMl == 750
    run(app.setWater(monday, 25_000))
    assert "from 0 to 20,000" in app.model.notice


def testImportingTargetsShowsThemFirstThenApplies(clock):
    app = makeApp(clock)
    bad = copy.deepcopy(targetsFile)
    bad["restDay"]["kcal"] = "lots"
    app.checkTargets(json.dumps(bad).encode())
    assert app.model.screen == "importTargets" and app.model.targetsCheck.targets is None
    run(app.confirmTargets())
    assert live(app, "dietTargets") == []
    app.services.filePicker.next = [FakeFile(json.dumps(targetsFile).encode())]
    run(app.pickTargetsFile())
    assert app.model.targetsCheck.problems == ()
    run(app.confirmTargets())
    [row] = live(app, "dietTargets")
    assert row["effectiveDate"] == monday and row["targetsJson"] == targetsFile
    assert app.model.screen == "main" and app.model.tab == "targets"
    assert app.model.today.targets.kcal == 3200 and app.model.today.waterTargetMl == 3000  # a Monday, no plan: training
    assert app.model.targets.name == "Bulk from 26 Oct" and app.model.targets.firstBlockStart == monday


def plansRow(week):
    return {"id": "11111111-1111-1111-1111-111111111111", "deleted": False, "effectiveDate": dt.date(2026, 10, 1),
            "importedAt": dt.datetime(2026, 10, 1, tzinfo=dt.UTC), "planJson": {"week": week}}


def testTheWeekCountsEachDayAgainstItsOwnTarget(clock):
    workout, rest, flex = {"exercises": []}, {"restDay": True}, {"makeUp": ["monday"]}
    rows = {"plans": [plansRow([workout] * 5 + [flex, rest])],
            "dietTargets": [{"id": "22222222-2222-2222-2222-222222222222", "deleted": False,
                             "importedAt": dt.datetime(2026, 10, 25, tzinfo=dt.UTC),
                             "effectiveDate": dt.date(2026, 10, 25), "targetsJson": targetsFile}],
            "bodyWeight": [{"id": f"w{day}", "deleted": False, "date": monday + dt.timedelta(day), "weightKg": kg}
                           for day, kg in ((-6, 79.0), (-4, 79.2), (0, 79.4), (2, 79.6))]}
    clock.now = dt.datetime(2026, 10, 28, 20, 0, tzinfo=dt.UTC)  # Wednesday
    app = makeApp(clock, rows=rows)
    app.openAdd("lunch", monday)
    run(app.useBarcode("3017620422003"))
    run(app.saveAmount("grams", 100, "lunch"))
    week = app.model.week
    assert [day.kind for day in week.days] == ["training"] * 5 + ["rest", "rest"]  # Saturday's flex: not trained
    assert week.days[0].kcal == 539 and week.days[0].logged and not week.days[1].logged
    assert week.averageKcal == 539 and week.averageTargetKcal == 3200  # only days with food logged count
    assert (week.weightKg, week.weighIns, week.weightChangeKg) == (79.5, 2, 0.4)
    assert week.days[5].target.kcal == 2900 and week.days[2].upcoming is False and week.days[3].upcoming


def testHistoryEditsTheLast7DaysOnThePhoneAndAnyDayOnThePc(clock):
    app = makeApp(clock)
    app.openHistory()
    assert app.model.screen == "history" and app.model.historyDays[0].date == monday
    app.editDay(monday - dt.timedelta(days=6))
    assert app.model.historyDay.editable
    app.editDay(monday - dt.timedelta(days=7))
    assert not app.model.historyDay.editable
    pc = makeApp(clock, mode="pc")
    pc.openHistory()
    assert pc.model.screen == "main" and pc.model.tab == "history"
    pc.editDay(dt.date(2026, 1, 3))
    assert pc.model.historyDay.editable
    pc.openAdd("lunch", dt.date(2026, 1, 3))
    run(pc.useBarcode("3017620422003"))
    run(pc.saveAmount("grams", 50, "lunch"))
    assert live(pc, "foodLogs")[0]["date"] == dt.date(2026, 1, 3) and pc.model.screen == "history"


def testScanningOnThePhone(clock):
    app = makeApp(clock)
    app.openAdd("snacks")
    app.services.scanner.next = {"status": "ok", "barcode": "3017620422003", "format": "EAN_13"}
    run(app.scan())
    assert app.model.screen == "amount" and app.model.picked.meal == "snacks"
    app.services.scanner.next = {"status": "error", "errorType": "camera", "message": "no camera"}
    run(app.scan())
    assert app.model.notice == "The scanner couldn't start. Type the barcode instead."


def testRecentHasTheSameAgainInOneTap(clock):
    """4a: Recent foods re-log in one tap, with the amount you had last time."""
    app = makeApp(clock)
    app.openAdd("breakfast")
    run(app.useBarcode("3017620422003"))
    run(app.saveAmount("servings", 2, "breakfast"))
    clock.advance(hours=6)
    app.openAdd("snacks")
    [recent] = app.model.recent
    assert recent.last.portion == "servings" and recent.last.portionCount == 2
    run(app.again(recent))
    logs = sorted(live(app, "foodLogs"), key=lambda row: row["loggedAt"])
    assert [(row["meal"], row["grams"]) for row in logs] == [("breakfast", 30.0), ("snacks", 30.0)]
    assert app.model.screen == "main"
