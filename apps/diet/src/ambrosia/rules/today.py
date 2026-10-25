"""A day as Today (and History's day editor) shows it (apps/diet/docs/plan.md 4a): what's left of the day's
target, the four meals and water."""

import datetime as dt
from dataclasses import dataclass, field

from ambrosia.rules.foods import LoggedFood, Values
from ambrosia.rules.targets import DayTargets


@dataclass(frozen=True, slots=True)
class DayView:
    date: dt.date
    kind: str  # training or rest (AM3.2)
    targets: DayTargets | None  # None before any targets file is imported
    eaten: Values
    meals: dict[str, tuple[LoggedFood, ...]] = field(default_factory=dict)  # meal -> what was eaten, in order
    waterMl: int = 0
    waterTargetMl: int | None = None
    editable: bool = True  # the phone edits the last 7 days (AM5.5)
    targetsLater: bool = False  # no targets on this day, but a targets file applies from a later day

    @property
    def leftKcal(self) -> float | None:
        return None if self.targets is None else self.targets.kcal - self.eaten.kcal
