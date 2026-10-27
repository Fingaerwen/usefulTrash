"""Where food values come from (Phase 0 checks 2 and 3): Open Food Facts over the network, by barcode or by
name, and the bundled generic foods (USDA FoodData Central, public domain), searched offline.

Every value is per 100 g. Open Food Facts gets only the barcode or the search words, with a User-Agent naming
the app and the repo (never an email). Its limits (its API docs): 15 product lookups and 10 searches a minute per
internet connection."""

import asyncio
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

runsInBrowser = sys.platform == "emscripten"  # Pyodide (the PC view website)
userAgent = "AmbrosiaSpike/0.0.1 (https://github.com/Fingaerwen/usefulTrash)"
productUrl = "https://world.openfoodfacts.org/api/v2/product/{}.json"
productFields = "code,product_name,brands,nutriments,serving_quantity,product_quantity,product_quantity_unit"
searchUrls = {
    # Search-a-licious, Open Food Facts' newer search service. Phone only: it refuses calls from web pages.
    "new": "https://search.openfoodfacts.org/search?q={}&page_size=10&fields=" + productFields,
    # The classic search page's JSON.
    "classic": ("https://world.openfoodfacts.org/cgi/search.pl?search_terms={}&search_simple=1&action=process"
                "&json=1&page_size=10&fields=" + productFields),
}
searchGapSec = 6.0  # at most 10 searches a minute, as Open Food Facts asks
timeoutSec = 15
genericFoodsPath = Path(__file__).with_name("genericFoods.tsv.gz")


class SourceError(Exception):
    """A lookup failed: no connection, a refusal or a broken answer. The message says which, in plain words."""


class NotFound(SourceError):
    """Open Food Facts answered 404: it doesn't have this product (its answer then says "product not found")."""


@dataclass(frozen=True)
class Food:
    source: str  # "openFoodFacts" or "usda"
    name: str
    brand: str = ""
    barcode: str = ""
    kcal: float | None = None  # per 100 g
    proteinG: float | None = None
    fatG: float | None = None
    carbsG: float | None = None
    servingG: float | None = None
    packG: float | None = None
    kcalFromKj: bool = False  # the label only gave kJ, so kcal was worked out from it

    @property
    def complete(self) -> bool:
        """All four values known: the food can be logged without typing anything from the label."""
        return None not in (self.kcal, self.proteinG, self.fatG, self.carbsG)

    def describe(self) -> str:
        def number(value: float | None, unit: str) -> str:
            return "?" if value is None else f"{value:.0f}{unit}" if unit == " kcal" else f"{value:.1f}{unit}"

        name = f"{self.name or '(no name)'}" + (f" · {self.brand}" if self.brand else "")
        values = (f"{number(self.kcal, ' kcal')}{' (from kJ)' if self.kcalFromKj else ''}, "
                  f"P {number(self.proteinG, ' g')}, F {number(self.fatG, ' g')}, C {number(self.carbsG, ' g')}")
        extras = "".join([f", serving {self.servingG:g} g" if self.servingG else "",
                          f", pack {self.packG:g} g" if self.packG else ""])
        return f"{name}: {values} per 100 g{extras}"


# --- Open Food Facts ---------------------------------------------------------------------------------

async def _getJson(url: str) -> dict:
    """GETs a JSON answer: urllib in a worker thread on the phone, the browser's fetch in the PC view."""
    if runsInBrowser:
        from pyodide.http import pyfetch  # only exists in the browser build

        try:
            # A browser sets its own User-Agent. A plain request also needs no extra permission check (CORS).
            response = await asyncio.wait_for(pyfetch(url, credentials="omit", cache="no-store"), timeoutSec)
            if response.status == 404:
                raise NotFound("Open Food Facts answered 404")
            if response.status != 200:
                raise SourceError(f"Open Food Facts answered {response.status}")
            return json.loads(await response.string())
        except SourceError:
            raise
        except Exception as err:  # "failed to fetch": offline, blocked, or not allowed for web pages
            raise SourceError(f"{type(err).__name__}: {err}"[:300]) from None
    return await asyncio.to_thread(_urllibGetJson, url)


def _urllibGetJson(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": userAgent, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeoutSec) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as err:
        raise (NotFound if err.code == 404 else SourceError)(f"Open Food Facts answered {err.code}") from None
    except (OSError, ValueError) as err:
        raise SourceError(f"{type(err).__name__}: {err}"[:300]) from None


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def foodFromOpenFoodFacts(product: dict) -> Food:
    nutriments = product.get("nutriments") or {}
    kcal = _number(nutriments.get("energy-kcal_100g"))
    kcalFromKj = False
    if kcal is None and _number(nutriments.get("energy-kj_100g")) is not None:
        kcal, kcalFromKj = _number(nutriments.get("energy-kj_100g")) / 4.184, True
    brands = product.get("brands") or ""
    if isinstance(brands, list):  # Search-a-licious gives a list
        brands = ", ".join(brands)
    packG = _number(product.get("product_quantity")) if product.get("product_quantity_unit", "g") == "g" else None
    return Food("openFoodFacts", (product.get("product_name") or "").strip(), brands.strip(),
                str(product.get("code") or ""), kcal, _number(nutriments.get("proteins_100g")),
                _number(nutriments.get("fat_100g")), _number(nutriments.get("carbohydrates_100g")),
                _number(product.get("serving_quantity")), packG, kcalFromKj)


async def lookUpBarcode(barcode: str) -> Food | None:
    """The product with this barcode, or None when Open Food Facts doesn't have it."""
    if not barcode.isdigit():
        raise SourceError(f"{barcode!r} isn't a food barcode (digits only)")
    try:
        answer = await _getJson(productUrl.format(barcode) + "?fields=" + productFields)
    except NotFound:  # found on the phone, 2026-10-25: an unknown barcode is a 404, not a 200 with status 0
        return None
    if answer.get("status") != 1 or not answer.get("product"):
        return None
    return foodFromOpenFoodFacts(answer["product"])


_lastSearchAt = -searchGapSec


async def searchPackaged(words: str, engine: str = "new") -> list[Food]:
    """Up to 10 packaged foods matching the words. Waits if the last search was under 6 s ago."""
    global _lastSearchAt
    wait = _lastSearchAt + searchGapSec - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    _lastSearchAt = time.monotonic()
    answer = await _getJson(searchUrls[engine].format(urllib.parse.quote(words.strip())))
    products = answer.get("hits") if engine == "new" else answer.get("products")
    return [foodFromOpenFoodFacts(product) for product in products or []]


# --- Generic foods (bundled) -----------------------------------------------------------------------

class GenericFoods:
    """The bundled USDA list, read once on the first search (so it doesn't slow the start)."""

    def __init__(self, path: Path = genericFoodsPath):
        self.path = path
        self.foods: list[tuple[str, list[str], bool, Food]] = []  # (source letter, the name's words, prepared, food)
        self.loadSec: float | None = None

    def load(self) -> None:
        started = time.perf_counter()
        lines = gzip.decompress(self.path.read_bytes()).decode("utf-8").splitlines()[1:]  # skip the header
        for line in lines:
            source, name, prepared, kcal, protein, fat, carbs = line.split("\t")
            self.foods.append((source, _words(name), prepared == "1",
                               Food("usda", name, kcal=float(kcal), proteinG=float(protein), fatG=float(fat),
                                    carbsG=float(carbs))))
        self.loadSec = time.perf_counter() - started

    def search(self, words: str, limit: int = 10) -> list[Food]:
        """Foods with a word starting with each word searched ("apple" finds apples, not pineapple, "eggs" finds
        "Egg, whole"), plainest first (see _rank)."""
        if not self.foods:
            self.load()
        wanted = [_stem(word) for word in _words(words)]
        if not wanted:
            return []
        found = [item for item in self.foods
                 if all(any(_stem(word).startswith(part) or word.startswith(part) for word in item[1])
                        for part in wanted)]
        found.sort(key=lambda item: _rank(wanted, *item))
        return [item[3] for item in found[:limit]]


# USDA names often start with a class: "Fish, salmon, ...", "Nuts, almonds". Skipping one isn't an extra word.
_classWords = {"fish", "nuts", "seeds", "spices", "beverages", "cereals", "crustaceans", "mollusks", "game", "meat",
               "cheese", "beans", "peas", "lentils", "egg", "milk", "yogurt", "beef", "pork", "lamb", "veal", "chicken",
               "turkey"}
# Words that mark a food as changed from its plain form.
_processingWords = {"dried", "dehydrated", "powder", "mix", "sweetened", "breaded", "fried", "substitute", "imitation",
                    "meatless", "glazed", "candied", "syrup", "flavored", "spread"}


def _rank(wanted: list[str], source: str, nameWords: list[str], prepared: bool, food: Food) -> tuple:
    """Sort key, smallest first: every searched word found whole ("salmon" before "salmonberries"). The fewest
    words not searched for in the name's leading parts that hold the searched ones ("Rice, white, raw" before
    "Rice crackers"). Not a prepared food (USDA's categories). The fewest processing words and brand names (USDA
    writes brands in capitals). The fewest parts needed. Foundation before SR Legacy. The shortest name."""
    whole = all(any(_stem(word) == part for word in nameWords) for part in wanted)
    needed, extra, seen = 0, 0, set()
    for index, part in enumerate(_words(piece) for piece in food.name.split(",")):
        hits = {searched for searched in wanted if any(_stem(word).startswith(searched) for word in part)}
        if not hits and index == 0 and len(part) == 1 and part[0] in _classWords:
            continue
        needed += 1
        extra += sum(1 for word in part if not any(_stem(word).startswith(searched) for searched in wanted))
        seen |= hits
        if seen >= set(wanted):
            break
    marks = (sum(1 for word in nameWords if word in _processingWords)
             + len(re.findall(r"\b[A-Z][A-Z'.&-]{2,}", food.name)))
    return not whole, extra, prepared, marks, needed, source != "F", len(food.name)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _stem(word: str) -> str:
    """A plural's stem, enough for matching: berries → berr, potatoes → potato, eggs → egg."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3]
    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word
