"""The food sources: USDA's generic foods and their ranking (AM5.3), and Open Food Facts (4d, Phase 0)."""

import asyncio
import json

import pytest

from ambrosia.sources.genericFoods import GenericFoods
from ambrosia.sources.openFoodFacts import FoodSourceError, OpenFoodFacts, productFromJson
from usefulShared.cloud.supabaseApi import CloudError

generic = GenericFoods()


@pytest.mark.parametrize("words, plainFirst", [
    ("salmon", "Fish, salmon"), ("chicken breast", "Chicken, breast"), ("apple", "Apples,"),
    ("egg", "Egg"), ("shrimp", "Crustaceans, shrimp"), ("honey", "Honey"), ("mozzarella", "Cheese, mozzarella"),
])
def testPlainFoodsComeFirst(words, plainFirst):
    assert generic.search(words, 3)[0].name.startswith(plainFirst)


def testEveryGenericFoodHasItsUsdaNumberAndOneCopy():
    generic.search("rice")
    names = [food.name.lower() for _, _, _, food in generic.foods]
    assert len(names) == len(set(names)) and len(names) > 7000
    assert all(food.usdaId and food.source == "usda" for _, _, _, food in generic.foods)
    assert not any(food.name.startswith("Babyfood") for _, _, _, food in generic.foods)
    first = generic.search("salmon", 1)[0]
    assert generic.byUsdaId(first.usdaId) == first


class FakeNet:
    """Stands in for the network: answers by URL part, records what was asked."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    async def __call__(self, method, url, headers, body):
        self.asked.append((url, headers))
        for part, answer in self.answers.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return 404, b'{"status": 0}'


nutella = {"code": "3017620422003", "product_name": "Nutella", "brands": "Ferrero", "product_quantity": 400,
           "product_quantity_unit": "g", "serving_quantity": 15,
           "nutriments": {"energy-kcal_100g": 539, "proteins_100g": 6.3, "fat_100g": 30.9, "carbohydrates_100g": 57.5}}


def run(coroutine):
    return asyncio.run(coroutine)


def testABarcodeLookupAndWhatItSends():
    net = FakeNet({"3017620422003": (200, json.dumps({"status": 1, "product": nutella}).encode())})
    source = OpenFoodFacts("0.1-alpha", net)
    product = run(source.lookUp("3017620422003"))
    assert product.complete and product.asFood().per100.kcal == 539 and product.asFood().packG == 400
    url, headers = net.asked[0]
    assert url.startswith("https://world.openfoodfacts.org/api/v2/product/3017620422003.json?fields=")
    assert headers["User-Agent"] == "Ambrosia/0.1-alpha (https://github.com/Fingaerwen/usefulTrash)"


def testAnUnknownBarcodeIsNotFoundNotAFailure():
    """Phase 0 (2026-10-25): Open Food Facts answers 404 for a product it doesn't have."""
    assert run(OpenFoodFacts("0.1-alpha", FakeNet({})).lookUp("1400000000007")) is None


@pytest.mark.parametrize("answer, words", [
    ((503, b"busy page"), "busy"), ((429, b""), "busy"), ((500, b""), "answered 500"),
    ((200, b"<html>"), "can't be read"), (CloudError(0, "network", "offline"), "No connection"),
])
def testFailuresInPlainWords(answer, words):
    with pytest.raises(FoodSourceError, match=words):
        run(OpenFoodFacts("0.1-alpha", FakeNet({"product": answer})).lookUp("3017620422003"))


def testMissingValuesAndKilojoules():
    partial = productFromJson({"product_name": "Rye bread", "nutriments": {"energy-kj_100g": 1046,
                                                                            "proteins_100g": 8}}, "6411401015090")
    assert not partial.complete and partial.kcalFromKj and partial.kcal == pytest.approx(250, abs=0.1)
    drink = productFromJson({"product_name": "Coca-Cola", "product_quantity_unit": "ml", "product_quantity": 330,
                             "brands": ["Coca-Cola"], "nutriments": {"energy-kcal_100g": 42, "proteins_100g": 0,
                                                                     "fat_100g": 0, "carbohydrates_100g": 10.6}}, "1")
    assert drink.complete and drink.unit == "ml" and drink.brand == "Coca-Cola" and drink.packG == 330


def testSearchesWaitTheirTurn():
    """At most 10 searches a minute: the second waits until 6 s after the first."""
    now = [100.0]
    slept = []

    async def fakeSleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    net = FakeNet({"search.openfoodfacts.org": (200, json.dumps({"hits": [nutella]}).encode())})
    source = OpenFoodFacts("0.1-alpha", net, clock=lambda: now[0])

    async def twoSearches():
        original = asyncio.sleep
        asyncio.sleep = fakeSleep
        try:
            first = await source.search("nutella")
            now[0] += 1.5
            await source.search("skyr")
        finally:
            asyncio.sleep = original
        return first

    found = run(twoSearches())
    assert [product.name for product in found] == ["Nutella"] and slept == [pytest.approx(4.5)]
    assert "q=nutella" in net.asked[0][0] and "page_size=10" in net.asked[0][0]
