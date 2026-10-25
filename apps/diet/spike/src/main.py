"""Ambrosia's Phase 0 spike (apps/diet/docs/plan.md, section 6): tests the diet app's risky parts on your phone,
and, built for the web, in the browser as the PC view would.

Checks: 1 barcode scanning with two scanners to compare (Google's and ZXing's), 2 Open Food Facts by barcode and
by name, 3 the bundled generic foods, 5 importing a file, 6 the start time. Every result also goes into a list
that "Copy the results" puts on the clipboard, to paste to Claude. Nothing is saved and nothing is signed in."""

import time

# Measured as early as possible: the moment Python starts running this file (check 6).
pythonStartTime = time.monotonic()

import json  # noqa: E402  (imported after the timer on purpose)

import flet as ft  # noqa: E402
from foodSources import Food, GenericFoods, SourceError, lookUpBarcode, searchPackaged  # noqa: E402

spikeVersion = "0.0.1"


def main(page: ft.Page):
    page.title = "Ambrosia spike"
    page.theme_mode = ft.ThemeMode.SYSTEM
    results: list[str] = []  # everything shown, for "Copy the results"
    scanned: dict[str, str] = {}  # barcode → complete, missing values, not found (the coverage count)
    genericFoods = GenericFoods()

    clipboard = ft.Clipboard()  # services register themselves with the page in Flet 1.0
    filePicker = ft.FilePicker()
    scanner = None
    if not page.web:
        from barcodeScan import BarcodeScan

        scanner = BarcodeScan()

    startText = ft.Text("")
    resultsText = ft.Text("", selectable=True, size=12)
    coverageText = ft.Text("Nothing scanned yet.")
    foodList = ft.Column(spacing=4)

    def note(line: str) -> None:
        results.append(line)
        resultsText.value = "\n".join(results[-30:])
        page.update()

    def showFoods(title: str, foods: list[Food]) -> None:
        foodList.controls = [ft.Text(title, weight=ft.FontWeight.BOLD)] + [
            ft.Text(("" if food.complete else "(missing values) ") + food.describe(), size=12) for food in foods]
        page.update()

    def updateCoverage() -> None:
        counts = {kind: list(scanned.values()).count(kind) for kind in ("complete", "missing values", "not found")}
        coverageText.value = (f"Scanned {len(scanned)}: {counts['complete']} complete, "
                              f"{counts['missing values']} with missing values, {counts['not found']} not found")
        page.update()

    # --- Check 1 + 2: scan, then look the barcode up -------------------------------------------------
    async def scanWith(which: str) -> None:
        started = time.perf_counter()
        answer = await scanner.scanOpen()
        took = time.perf_counter() - started
        if answer.get("status") == "cancelled":
            note(f"{which} scan: cancelled")
            return
        if answer.get("status") != "ok":
            note(f"{which} scan: error {answer.get('errorType')}: {answer.get('message')}")
            return
        barcode = answer.get("barcode", "")
        note(f"{which} scan: {barcode} ({answer.get('format')}) in {took:.1f} s, scanner screen included")
        await lookUp(barcode)

    async def lookUp(barcode: str) -> None:
        started = time.perf_counter()
        try:
            food = await lookUpBarcode(barcode)
        except SourceError as err:
            note(f"  lookup {barcode}: failed: {err}")
            return
        took = (time.perf_counter() - started) * 1000
        if food is None:
            scanned[barcode] = "not found"
            note(f"  lookup {barcode}: not in Open Food Facts ({took:.0f} ms)")
            showFoods("Not found: this is where you'd type it from the label (AM2.3)", [])
        else:
            scanned[barcode] = "complete" if food.complete else "missing values"
            note(f"  lookup {barcode}: {'complete' if food.complete else 'missing values'} ({took:.0f} ms): "
                 f"{food.describe()}")
            showFoods("Scanned", [food])
        updateCoverage()

    async def scanOpen(e):
        await scanWith("ZXing")

    barcodeField = ft.TextField(label="Or type a barcode", keyboard_type=ft.KeyboardType.NUMBER, width=220)

    async def lookUpTyped(e):
        if barcodeField.value.strip():
            note(f"Typed barcode: {barcodeField.value.strip()}")
            await lookUp(barcodeField.value.strip())

    # --- Check 2: search packaged foods by name ------------------------------------------------------
    packagedField = ft.TextField(label="Packaged food, e.g. skyr", width=220)

    async def searchOpenFoodFacts(engine: str) -> None:
        words = packagedField.value.strip()
        if not words:
            return
        started = time.perf_counter()
        try:
            foods = await searchPackaged(words, engine)
        except SourceError as err:
            note(f"Search ({engine}) {words!r}: failed: {err}")
            return
        took = (time.perf_counter() - started) * 1000
        note(f"Search ({engine}) {words!r}: {len(foods)} found, {sum(food.complete for food in foods)} complete "
             f"({took:.0f} ms, any wait for the 10-a-minute limit included)")
        showFoods(f"Open Food Facts ({engine}): {words}", foods)

    async def searchNew(e):
        # The newer search service refuses calls from web pages (no CORS permission), so the PC view uses the classic.
        await searchOpenFoodFacts("classic" if page.web else "new")

    async def searchClassic(e):
        await searchOpenFoodFacts("classic")

    # --- Check 3: search the bundled generic foods ---------------------------------------------------
    genericField = ft.TextField(label="Generic food, e.g. chicken breast", width=220)

    def searchGeneric(e):
        words = genericField.value.strip()
        if not words:
            return
        firstSearch = not genericFoods.foods
        started = time.perf_counter()
        foods = genericFoods.search(words)
        took = (time.perf_counter() - started) * 1000
        loaded = f", loading {len(genericFoods.foods)} foods took {genericFoods.loadSec * 1000:.0f} ms" if firstSearch else ""
        note(f"Generic {words!r}: {len(foods)} shown in {took:.0f} ms{loaded}")
        showFoods(f"Generic foods (USDA): {words}", foods)

    # --- Check 5: import a file ----------------------------------------------------------------------
    async def importFile(e):
        started = time.perf_counter()
        files = await filePicker.pick_files(dialog_title="Pick a JSON file", file_type=ft.FilePickerFileType.CUSTOM,
                                            allowed_extensions=["json"], with_data=True)
        if not files:
            note("Import: cancelled")
            return
        picked = files[0]
        data = picked.bytes or b""
        try:
            parsed = json.loads(data.decode("utf-8"))
            shape = f"JSON {type(parsed).__name__} with {len(parsed)} entries" if hasattr(parsed, "__len__") else "JSON"
        except (UnicodeDecodeError, ValueError) as err:
            shape = f"not readable JSON ({type(err).__name__})"
        note(f"Import: {picked.name}, {len(data)} bytes read, {shape} "
             f"({time.perf_counter() - started:.1f} s, picking included)")

    async def copyResults(e):
        await clipboard.set("\n".join([f"Ambrosia spike {spikeVersion} ({'PC view' if page.web else 'phone'})",
                                       coverageText.value, *results]))
        note("Copied the results to the clipboard.")

    if page.web:
        scanSection = [ft.Text("Scanning is phone only. Type a barcode instead:")]
    else:
        # Google's scanner left the extension once ZXing was chosen (AM5.1); the APK built in Phase 0 has both.
        scanSection = [ft.Row([ft.FilledButton("Scan (ZXing)", icon=ft.Icons.CAMERA_ALT, on_click=scanOpen)],
                              wrap=True)]

    page.add(
        ft.SafeArea(
            ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("Ambrosia spike", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Version {spikeVersion} · {'PC view' if page.web else 'phone'}"),
                    startText,
                    ft.Divider(),
                    ft.Text("1. Scan a barcode", weight=ft.FontWeight.BOLD),
                    *scanSection,
                    ft.Row([barcodeField, ft.OutlinedButton("Look up", on_click=lookUpTyped)], wrap=True),
                    coverageText,
                    ft.Divider(),
                    ft.Text("2. Search packaged foods (Open Food Facts)", weight=ft.FontWeight.BOLD),
                    ft.Row([packagedField, ft.OutlinedButton("Search", on_click=searchNew),
                            ft.OutlinedButton("Classic search", on_click=searchClassic, visible=not page.web)],
                           wrap=True),
                    ft.Divider(),
                    ft.Text("3. Search generic foods (bundled, offline)", weight=ft.FontWeight.BOLD),
                    ft.Row([genericField, ft.OutlinedButton("Search", on_click=searchGeneric)], wrap=True),
                    foodList,
                    ft.Divider(),
                    ft.Text("4. Import a file", weight=ft.FontWeight.BOLD),
                    ft.OutlinedButton("Pick a JSON file", icon=ft.Icons.UPLOAD_FILE, on_click=importFile),
                    ft.Divider(),
                    ft.Row([ft.Text("Results", weight=ft.FontWeight.BOLD),
                            ft.FilledButton("Copy the results", icon=ft.Icons.COPY, on_click=copyResults)]),
                    resultsText,
                ],
            ),
            # expand: the safe area fills the screen, which gives the column a fixed height to scroll in.
            expand=True,
        )
    )
    # Plain words only: the PC view's font has no arrows or ticks (TS1.1).
    startText.value = f"Python start to screen: {time.monotonic() - pythonStartTime:.2f} s"
    note(startText.value)


if __name__ == "__main__":
    ft.run(main)
