"""A day as Today (and History's day editor) shows it (apps/diet/docs/plan.md 4a): what's left of the day's
target, the four meals and water (with what adds itself, AM12.4)."""

import datetime as dt
from dataclasses import dataclass, field

from ambrosia.rules.foods import LoggedFood, Values
from ambrosia.rules.targets import DayTargets


shakeWaterMl = 600  # each protein shake comes with this much water (AM12.4)
workoutWaterMl = 1300  # drunk at a finished Talon workout that counts (AM12.4)


@dataclass(frozen=True, slots=True)
class DayWater:
    """A day's water and where it comes from (AM12.4): what you added with +250 ml or the pencil, 600 ml for each
    protein shake that day, and 1.3 L when Talon has a finished workout that counts. Only what you added is stored,
    the rest is worked out, so a deleted shake or workout takes its water with it (AM12.5)."""

    byHandMl: int = 0
    shakes: int = 0
    workout: bool = False

    @property
    def shakesMl(self) -> int:
        return self.shakes * shakeWaterMl

    @property
    def workoutMl(self) -> int:
        return workoutWaterMl if self.workout else 0

    @property
    def totalMl(self) -> int:
        return self.byHandMl + self.shakesMl + self.workoutMl


@dataclass(frozen=True, slots=True)
class DayView:
    date: dt.date
    kind: str  # training or rest (AM3.2)
    targets: DayTargets | None  # None before any targets file is imported
    eaten: Values
    meals: dict[str, tuple[LoggedFood, ...]] = field(default_factory=dict)  # meal -> what was eaten, in order
    waterMl: int = 0  # the day's total: what you added, and what shakes and Talon's workout add (AM12.4)
    waterTargetMl: int | None = None
    editable: bool = True  # the phone edits the last 7 days (AM5.5)
    targetsLater: bool = False  # no targets on this day, but a targets file applies from a later day
    ahead: bool = False  # a day after today (the day strip, AM12.1): food yes, water not yet, like Talon's steps
    water: "DayWater | None" = None  # where the day's water comes from (AM12.4)

    @property
    def leftKcal(self) -> float | None:
        return None if self.targets is None else self.targets.kcal - self.eaten.kcal
