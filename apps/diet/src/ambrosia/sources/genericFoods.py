"""USDA's generic foods, bundled and searched offline (apps/diet/docs/plan.md 4d, AM5.3): rice, chicken breast,
an apple, which Open Food Facts covers poorly. FoodData Central's data is public domain (CC0). USDA asks for
credit: "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central."

The file (data/genericFoods.tsv.gz, made by apps/diet/makeGenericFoods.py) is read on the first search, not
at start. Search ranks plain foods first (Phase 0's new ranking, AM5.3): "salmon" finds salmon before
salmonberries, "rice" plain rice before rice crackers.
"""

import gzip
import re
import time
from pathlib import Path

from ambrosia.rules.foods import Food, Values

dataPath = Path(__file__).resolve().parent.parent / "data" / "genericFoods.tsv.gz"
credit = "Generic foods: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central."

# USDA names often start with a class: "Fish, salmon, ...", "Nuts, almonds". Skipping one isn't an extra word.
_classWords = {"fish", "nuts", "seeds", "spices", "beverages", "cereals", "crustaceans", "mollusks", "game", "meat",
               "cheese", "beans", "peas", "lentils", "egg", "milk", "yogurt", "beef", "pork", "lamb", "veal", "chicken",
               "turkey"}
# Words that mark a food as changed from its plain form.
_processingWords = {"dried", "dehydrated", "powder", "mix", "sweetened", "breaded", "fried", "substitute", "imitation",
                    "meatless", "glazed", "candied", "syrup", "flavored", "spread"}


class GenericFoods:
    """The bundled list, read once on the first search (so it doesn't slow the start)."""

    def __init__(self, path: Path = dataPath):
        self.path = path
        self.foods: list[tuple[str, list[str], bool, Food]] = []  # (source letter, the name's words, prepared, food)
        self.loadSec: float | None = None

    def load(self) -> None:
        started = time.perf_counter()
        lines = gzip.decompress(self.path.read_bytes()).decode("utf-8").splitlines()[1:]  # skip the header
        for line in lines:
            source, fdcId, name, prepared, kcal, protein, fat, carbs = line.split("\t")
            values = Values(float(kcal), float(protein), float(fat), float(carbs))
            self.foods.append((source, _words(name), prepared == "1",
                               Food("", "usda", name, values, usdaId=int(fdcId))))
        self.loadSec = time.perf_counter() - started

    def byUsdaId(self, usdaId: int) -> Food | None:
        if not self.foods:
            self.load()
        return next((food for _, _, _, food in self.foods if food.usdaId == usdaId), None)

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
