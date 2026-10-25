"""Ambrosia on a stand-in store (until gate 2 builds the real one): rows kept in memory, edit times stamped like the
phone's store does, and a fake Open Food Facts. Used by the tests and the screenshot server. Not a test file."""

import datetime as dt
import json
from collections.abc import Sequence
from typing import Any

from ambrosia.appBase import AmbrosiaBase
from ambrosia.sources.openFoodFacts import OpenFoodFacts
from usefulShared.platform.appLog import AppLog
from usefulShared.tables import editTime


class FakeOpenFoodFacts:
    """Answers barcodes from a dict of product JSON, and searches with every product whose name has the words."""

    def __init__(self, products: dict[str, dict] | None = None):
        self.products = products or {}
        self.asked: list[str] = []

    async def __call__(self, method, url, headers, body):
        self.asked.append(url)
        if "search.openfoodfacts.org" in url:
            words = url.split("q=")[1].split("&")[0].replace("%20", " ").lower()
            hits = [product for product in self.products.values()
                    if all(word in product.get("product_name", "").lower() for word in words.split())]
            return 200, json.dumps({"hits": hits}).encode()
        for barcode, product in self.products.items():
            if f"/product/{barcode}.json" in url:
                return 200, json.dumps({"status": 1, "product": product}).encode()
        return 404, b'{"status": 0, "status_verbose": "product not found"}'


class FakeScanner:
    def __init__(self):
        self.next: dict = {"status": "cancelled"}

    async def scanOpen(self) -> dict:
        return self.next


class FakeFile:
    def __init__(self, content: bytes):
        self.bytes, self.name = content, "targets.json"


class FakePicker:
    def __init__(self):
        self.next: list | None = None

    async def pick_files(self, **options):
        return self.next


class Services:
    def __init__(self):
        self.scanner, self.filePicker = FakeScanner(), FakePicker()


class StandInApp(AmbrosiaBase):
    """The controller over rows kept in memory."""

    def __init__(self, userId: str, clock, localToday, mode: str = "phone", products: dict | None = None,
                 rows: dict[str, list[dict[str, Any]]] | None = None):
        self.mode = mode
        self.net = FakeOpenFoodFacts(products)
        super().__init__(Services(), AppLog(None, clock), clock, localToday, userId,
                         foodSource=OpenFoodFacts("0.1-alpha", self.net, clock=lambda: 1e9))
        self.foodSource._last = {"lookup": -1e12, "search": -1e12}  # no waiting between calls in tests
        self.foodSource.clock = lambda: 1e12 + len(self.net.asked) * 100
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        for table, tableRows in (rows or {}).items():
            for row in tableRows:
                self.rows.setdefault(table, {})[row["id"]] = row
        self.model.screen = "main"
        self.refresh()

    def rowsByTable(self) -> dict[str, list[dict[str, Any]]]:
        return {table: list(rows.values()) for table, rows in self.rows.items()}

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        saved = []
        for table, row in edits:
            existing = self.rows.get(table, {}).get(row["id"])
            stamped = dict(row, updatedAt=editTime(self.clock(), existing["updatedAt"] if existing else None),
                           cloudUpdatedAt=None)
            self.rows.setdefault(table, {})[row["id"]] = stamped
            saved.append(stamped)
        self.refresh()
        return saved


def localDay(clock) -> dt.date:
    return clock().date()
