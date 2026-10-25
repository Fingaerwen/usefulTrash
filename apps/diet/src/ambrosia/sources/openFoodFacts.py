"""Open Food Facts, the free and open food database (apps/diet/docs/plan.md 4d; Phase 0 check 2): a product by its
barcode (phone and PC view), and packaged foods by name (phone only, AM5.2: the newer search lets no web page
use it, and the classic one refuses anonymous callers).

A request sends only the barcode or the search words, with a User-Agent naming the app and the repo, never
your email; in the browser the browser sets its own. Its limits (its API docs): 15 product lookups and 10
searches a minute per internet connection, so a barcode is looked up once per scan, never while typing, and
calls wait their turn. An unknown barcode comes back as 404 and reads as not found (Phase 0, 2026-10-25).
Its data is under the Open Database License: the app credits it.
"""

import asyncio
import json
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from ambrosia.rules.foods import Food, Values
from usefulShared.cloud.supabaseApi import CloudError, Transport, fetchTransport, runsInBrowser, urllibTransport

productUrl = "https://world.openfoodfacts.org/api/v2/product/{}.json"
searchUrl = "https://search.openfoodfacts.org/search"
fields = "code,product_name,brands,nutriments,serving_quantity,product_quantity,product_quantity_unit"
lookupGapSec = 4.0  # at most 15 lookups a minute
searchGapSec = 6.0  # at most 10 searches a minute
credit = "Packaged foods: Open Food Facts, under the Open Database License (openfoodfacts.org)."


class FoodSourceError(Exception):
    """A lookup that failed, in plain words for the screen (no connection, the service busy, a broken answer)."""


@dataclass(frozen=True, slots=True)
class Product:
    """A product as Open Food Facts has it. Any of the four values may be missing; then you type it from the
    label (AM2.3), starting from what's known."""

    barcode: str
    name: str
    brand: str
    unit: str  # g, or ml for a drink (its values are per 100 ml)
    kcal: float | None
    proteinG: float | None
    fatG: float | None
    carbsG: float | None
    servingG: float | None
    packG: float | None
    kcalFromKj: bool = False  # the label only gave kJ; kcal worked out from it

    @property
    def complete(self) -> bool:
        return None not in (self.kcal, self.proteinG, self.fatG, self.carbsG) and bool(self.name)

    def asFood(self) -> Food:
        """The product as a food to log; only when complete."""
        values = Values(round(self.kcal, 1), round(self.proteinG, 2), round(self.fatG, 2), round(self.carbsG, 2))
        return Food("", "openFoodFacts", self.name, values, self.brand, self.barcode, unit=self.unit,
                    servingG=self.servingG, packG=self.packG)


class OpenFoodFacts:
    def __init__(self, appVersion: str, transport: Transport | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.userAgent = f"Ambrosia/{appVersion} (https://github.com/Fingaerwen/usefulTrash)"
        self.transport = transport or (fetchTransport if runsInBrowser else urllibTransport)
        self.clock = clock
        self._last = {"lookup": -lookupGapSec, "search": -searchGapSec}

    async def _get(self, kind: str, url: str) -> tuple[int, bytes]:
        gap = lookupGapSec if kind == "lookup" else searchGapSec
        wait = self._last[kind] + gap - self.clock()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last[kind] = self.clock()
        headers = {"Accept": "application/json"}
        if not runsInBrowser:  # a browser sets its own and refuses ours
            headers["User-Agent"] = self.userAgent
        try:
            return await self.transport("GET", url, headers, None)
        except CloudError as problem:  # no answer at all
            raise FoodSourceError("No connection to Open Food Facts: check the internet and try again.") from problem

    async def lookUp(self, barcode: str) -> Product | None:
        """The product with this barcode, or None when Open Food Facts doesn't have it."""
        status, body = await self._get("lookup", productUrl.format(barcode) + "?fields=" + fields)
        if status == 404:
            return None
        answer = _answer(status, body)
        if answer.get("status") != 1 or not isinstance(answer.get("product"), dict):
            return None
        return productFromJson(answer["product"], barcode)

    async def search(self, words: str, limit: int = 10) -> list[Product]:
        """Packaged foods matching the words (the phone only: AM5.2)."""
        query = urllib.parse.urlencode({"q": words.strip(), "page_size": str(limit), "fields": fields},
                                       quote_via=urllib.parse.quote)
        status, body = await self._get("search", f"{searchUrl}?{query}")
        hits = _answer(status, body).get("hits")
        return [productFromJson(hit, str(hit.get("code") or "")) for hit in hits or [] if isinstance(hit, dict)]


def _answer(status: int, body: bytes) -> dict:
    if status in (429, 503):
        raise FoodSourceError("Open Food Facts is busy right now: try again in a few minutes.")
    if status != 200:
        raise FoodSourceError(f"Open Food Facts answered {status}: try again later.")
    try:
        answer = json.loads(body)
    except ValueError:
        raise FoodSourceError("Open Food Facts sent an answer that can't be read.") from None
    if not isinstance(answer, dict):
        raise FoodSourceError("Open Food Facts sent an answer that can't be read.")
    return answer


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def productFromJson(product: dict, barcode: str) -> Product:
    nutriments = product.get("nutriments") if isinstance(product.get("nutriments"), dict) else {}
    kcal, fromKj = _number(nutriments.get("energy-kcal_100g")), False
    if kcal is None and _number(nutriments.get("energy-kj_100g")) is not None:
        kcal, fromKj = _number(nutriments.get("energy-kj_100g")) / 4.184, True
    brands = product.get("brands") or ""
    if isinstance(brands, list):  # the newer search gives a list
        brands = ", ".join(str(brand) for brand in brands)
    unit = "ml" if str(product.get("product_quantity_unit") or "").lower() == "ml" else "g"
    servingG, packG = _number(product.get("serving_quantity")), _number(product.get("product_quantity"))
    return Product(barcode, str(product.get("product_name") or "").strip(), str(brands).strip(), unit, kcal,
                   _number(nutriments.get("proteins_100g")), _number(nutriments.get("fat_100g")),
                   _number(nutriments.get("carbohydrates_100g")), servingG or None, packG or None, fromKj)
