"""Cuts USDA FoodData Central's generic foods down to what Ambrosia needs (plan 4d, AM5.3): each food's USDA
number (its fdc_id, so a food you've used keeps its ID when USDA publishes new data), name, kcal, protein, fat
and carbs per 100 g, and whether USDA files it as a prepared food (for the search's ranking). Writes
src/ambrosia/data/genericFoods.tsv.gz, bundled with the app. First made in Phase 0 (spike/).

The data is public domain (CC0 1.0); USDA asks for credit: "U.S. Department of Agriculture, Agricultural
Research Service. FoodData Central." Uses SR Legacy (7,793 foods, the classic reference list) and the
Foundation foods (newer lab values for common foods; only rows of type foundation_food). The zips are read as
they are, nothing is extracted. A food without all four values is left out, so are baby foods, and a name in
both lists is kept once, with the Foundation values (the newer lab analyses).

Usage (on the PC, from the repo root):
  python3 -I apps/diet/makeGenericFoods.py <sr_legacy_food_csv zip> <foundation_food_csv zip>
"""

import csv
import gzip
import io
import sys
import zipfile
from pathlib import Path

outputPath = Path(__file__).resolve().parent / "src" / "ambrosia" / "data" / "genericFoods.tsv.gz"

protein, fat, carbs = "1003", "1004", "1005"  # USDA nutrient IDs: grams per 100 g
# kcal per 100 g, in order of preference: SR Legacy has "Energy"; most Foundation foods only have the Atwater ones.
kcalIds = ("1008", "2048", "2047")
wantedIds = {protein, fat, carbs, *kcalIds}
leftOut = {"Baby Foods"}
# USDA's categories of prepared foods: the search shows them after plain foods with the same words (Phase 0, 2026-10-25).
preparedCategories = {"Fast Foods", "Restaurant Foods", "Meals, Entrees, and Side Dishes", "Snacks", "Sweets",
                      "Sausages and Luncheon Meats", "American Indian/Alaska Native Foods"}


def _rows(archive: zipfile.ZipFile, fileName: str):
    member = next(name for name in archive.namelist() if name.endswith("/" + fileName))
    with archive.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))


def foodsIn(zipPath: Path, dataType: str, source: str) -> list[tuple[str, int, str, int, float, float, float, float]]:
    """(source, fdc_id, name, prepared, kcal, protein, fat, carbs) for every food of the given type with all four
    values."""
    with zipfile.ZipFile(zipPath) as archive:
        categories = {row["id"]: row["description"] for row in _rows(archive, "food_category.csv")}
        names, prepared = {}, {}
        for row in _rows(archive, "food.csv"):
            category = categories.get(row["food_category_id"], "")
            if row["data_type"] == dataType and category not in leftOut:
                names[row["fdc_id"]] = row["description"].strip()
                prepared[row["fdc_id"]] = int(category in preparedCategories)
        values: dict[str, dict[str, float]] = {}
        for row in _rows(archive, "food_nutrient.csv"):
            if row["fdc_id"] in names and row["nutrient_id"] in wantedIds and row["amount"]:
                values.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount"])
    foods = []
    for fdcId, name in names.items():
        found = values.get(fdcId, {})
        kcal = next((found[nutrient] for nutrient in kcalIds if nutrient in found), None)
        if kcal is None or not all(nutrient in found for nutrient in (protein, fat, carbs)):
            continue
        # "Carbohydrate, by difference" can come out slightly below 0 (lab rounding): read as 0.
        foods.append((source, int(fdcId), name, prepared[fdcId], round(kcal), *(round(max(found[nutrient], 0.0), 1)
                                                  for nutrient in (protein, fat, carbs))))
    return foods


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    srLegacy = foodsIn(Path(sys.argv[1]), "sr_legacy_food", "S")
    foundation = foodsIn(Path(sys.argv[2]), "foundation_food", "F")
    byName: dict[str, tuple] = {}
    for food in foundation + srLegacy:  # Foundation first, so its copy of a shared name is the one kept
        byName.setdefault(food[2].lower(), food)
    foods = sorted(byName.values(), key=lambda food: food[2].lower())
    lines = ["\t".join([source, str(fdcId), name.replace("\t", " "), *(f"{value:g}" for value in numbers)])
             for source, fdcId, name, *numbers in foods]
    data = ("source\tfdcId\tname\tprepared\tkcal\tproteinG\tfatG\tcarbsG\n" + "\n".join(lines) + "\n").encode("utf-8")
    outputPath.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))  # mtime 0: the same input, the same file
    print(f"{len(srLegacy)} SR Legacy + {len(foundation)} Foundation foods, {len(foods)} names → {outputPath.name}: "
          f"{len(data) / 1024:.0f} KB, {outputPath.stat().st_size / 1024:.0f} KB compressed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
