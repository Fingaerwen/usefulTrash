"""Ambrosia's readable history (AM5.6, like Talon's BK1.2 and EX1.1): every entry and every day against its targets, as
CSV files a spreadsheet opens. They go into the backups' history file and Export CSV, beside the tables themselves."""

import csv
import datetime as dt
import io
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ambrosia.rules.foods import LoggedFood, meals, total
from ambrosia.rules.targets import DayTargets


def _csv(header: list[str], rows: Iterable[list[Any]]) -> str:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return text.getvalue()


def _number(value: float, decimals: int = 1) -> str:
    """12, 12.5, 340: no needless ".0"."""
    text = f"{value:.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def readableFiles(logs: Iterable[LoggedFood], water: Mapping[dt.date, int], kindOf: Callable[[dt.date], str],
                  targetsFor: Callable[[dt.date, str], DayTargets | None], today: dt.date) -> dict[str, str]:
    """food.csv: every entry in the order of its day. days.csv: each day with food or water up to today, what you
    ate against that day's targets."""
    logs = sorted(logs, key=lambda log: (log.date, meals.index(log.meal), log.loggedAt, log.logId))
    food = _csv(["date", "meal", "food", "brand", "amount", "grams or ml", "kcal", "protein g", "fat g", "carbs g"],
                [[log.date.isoformat(), log.meal, log.name, log.brand, log.shortAmount, _number(log.grams),
                  _number(log.values.kcal, 0), _number(log.values.proteinG), _number(log.values.fatG),
                  _number(log.values.carbsG)] for log in logs])
    dates = sorted({log.date for log in logs} | {date for date, ml in water.items() if ml})
    rows = []
    for date in (date for date in dates if date <= today):
        eaten = total(log.values for log in logs if log.date == date)
        kind = kindOf(date)
        target = targetsFor(date, kind)
        rows.append([date.isoformat(), kind, _number(eaten.kcal, 0), _number(eaten.proteinG), _number(eaten.fatG),
                     _number(eaten.carbsG), *([target.kcal, target.proteinG, target.fatG, target.carbsG] if target
                                              else ["", "", "", ""]), water.get(date, 0)])
    days = _csv(["date", "day", "kcal", "protein g", "fat g", "carbs g", "target kcal", "target protein g",
                 "target fat g", "target carbs g", "water ml"], rows)
    return {"food.csv": food, "days.csv": days}
