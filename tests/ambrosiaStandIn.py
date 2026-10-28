"""Ambrosia on a stand-in store: rows kept in memory, edit times stamped like the phone's store does, and a fake Open
Food Facts. Used by the tests of the shared flows and by the screenshot server. The phone and PC modes have their
own tests on the cloud stand-in (tests/diet/testPhoneApp.py, testPcApp.py). Not a test file."""

import datetime as dt
import json
from collections.abc import Sequence
from typing import Any

from ambrosia.appBase import AmbrosiaBase
from ambrosia.sources.openFoodFacts import OpenFoodFacts
from usefulShared.platform.appLog import AppLog
from usefulShared.platform.problems import SyncFacts
from usefulShared.tables import editTime

config = {"supabaseUrl": "https://example.supabase.co", "supabasePublishableKey": "testPublishableKey",
          "googleWebClientId": "testClient.apps.googleusercontent.com"}


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
        self.saved: dict[str, bytes] = {}  # Export CSV's files, by name

    async def pick_files(self, **options):
        return self.next

    async def save_file(self, file_name: str, src_bytes: bytes, **options):
        self.saved[file_name] = src_bytes


class FakeClipboard:
    def __init__(self):
        self.text = ""

    async def set(self, text: str) -> None:
        self.text = text


class Services:
    def __init__(self):
        self.scanner, self.filePicker, self.clipboard = FakeScanner(), FakePicker(), FakeClipboard()


class FakeGoogle:
    """Google's account picker: hands out an ID token carrying the hashed nonce, like the real one (the cloud stand-in
    checks it). And Google Play services' Drive permission, with a token that expires when a test says so."""

    def __init__(self, account: str):
        self.account = account
        self.answer: dict | None = None  # set to act out "cancelled" or an error
        self.driveToken = "driveToken1"
        self.driveAnswer: dict | None = None

    async def getIdToken(self, serverClientId: str, hashedNonce: str) -> dict:
        return self.answer or {"status": "ok", "idToken": f"googleIdToken:{self.account}:{hashedNonce}"}

    async def clearSignInState(self) -> dict:
        return {"status": "ok"}

    async def getDriveAccess(self, interactive: bool, accountEmail: str = "") -> dict:
        return self.driveAnswer or {"status": "ok", "accessToken": self.driveToken}

    async def clearDriveToken(self, accessToken: str) -> dict:
        self.driveToken = "driveToken2"
        return {"status": "ok"}


class FakePrefs:
    """This site's local storage, as Flet's SharedPreferences reads it (both PC views share it)."""

    def __init__(self):
        self.values: dict[str, str] = {}

    async def get(self, key):
        return self.values.get(key)

    async def remove(self, key):
        self.values.pop(key, None)
        return True


class FakeGoogleWindow:
    """The second window with Google's Drive permission page, answering the way site/driveToken.html does: under
    Ambrosia's own key when the request's state starts "ambrosia.", else under Talon's."""

    def __init__(self, prefs: FakePrefs):
        self.prefs = prefs
        self.opened: list[str] = []
        self.answer: dict | None = None  # None: allow, with the request's state

    async def launch_url(self, url, web_only_window_name=None, **options):
        import urllib.parse

        self.opened.append(url)
        state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        answer = self.answer or {"state": state, "accessToken": "driveToken1", "expiresIn": 3599, "error": ""}
        key = "ambrosiaDriveToken" if answer["state"].startswith("ambrosia.") else "driveToken"
        self.prefs.values[key] = json.dumps(answer)


class PhoneServices(Services):
    """The phone's: the scanner, file picker and clipboard, Google's sign-in and the phone-locked secret store."""

    def __init__(self, account: str):
        from usefulShared.signIn.sessionKeeper import MemoryStore

        super().__init__()
        self.googleSignIn, self.secretStore = FakeGoogle(account), MemoryStore()


class StandInApp(AmbrosiaBase):
    """The controller over rows kept in memory."""

    def __init__(self, userId: str, clock, localToday, mode: str = "phone", products: dict | None = None,
                 rows: dict[str, list[dict[str, Any]]] | None = None):
        self.mode = mode
        self.net = FakeOpenFoodFacts(products)
        super().__init__(config, Services(), AppLog(None, clock), clock, localToday,
                         foodSource=OpenFoodFacts("0.1-alpha", self.net, clock=lambda: 1e9))
        self.startActions(userId)
        self.dismissed = None
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

    def syncFacts(self) -> SyncFacts:
        return SyncFacts("done", "", self.clock(), 0, None, ())

    def dismissedCheck(self):
        return self.dismissed

    def rememberDismissed(self, checkDate) -> None:
        self.dismissed = checkDate

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


# --- A cloud with your bulk so far (tests/diet/testPhoneApp.py, testPcApp.py) ---------------------

def inCloud(cloud, tableName: str, **columns) -> dict:
    """A row another device (Talon, the PC view) put in the cloud stand-in earlier."""
    from usefulTestKit import exampleRow

    from ambrosia.tables import tablesByName
    from usefulShared.tables import toCloud

    row = exampleRow(tableName, updatedAt=dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.UTC), **columns)
    cloud.storeDirectly(tableName, toCloud(tablesByName[tableName], row))
    return row


def bulkInCloud(cloud, targetsFile: dict, kilos: tuple[float, ...] = (80.0, 80.0, 80.1, 80.1, 79.8, 79.8)) -> None:
    """Your targets file from 26 Oct and a Friday weigh-in a week from 30 Oct in Talon. With the default weights the
    block ending 6 Dec came in lower than the one 4 weeks earlier: a big miss (4g)."""
    from usefulTestKit import userA

    from ambrosia.tables import tablesByName
    from usefulShared.tables import dayRowId

    inCloud(cloud, "dietTargets", effectiveDate=dt.date(2026, 10, 26), targetsJson=targetsFile)
    for week, kilo in enumerate(kilos):
        date = dt.date(2026, 10, 30) + dt.timedelta(weeks=week)
        inCloud(cloud, "bodyWeight", date=date, weightKg=kilo, id=dayRowId(tablesByName["bodyWeight"], userA, date=date))


class PcServices(PhoneServices):
    """The browser's: the phone's fakes plus this site's storage and the second window."""

    def __init__(self, account: str):
        super().__init__(account)
        self.prefs = FakePrefs()
        self.urlLauncher = FakeGoogleWindow(self.prefs)
