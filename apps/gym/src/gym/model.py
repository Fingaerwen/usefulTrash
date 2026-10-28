"""What the screens draw (plan 3b: declarative screens): one observable model per app. The controller
(phoneApp.py or pcApp.py) changes it. Every screen that shows a changed field redraws by itself.

Also the Problems report (12d, DG1.1): plain words for each kind of problem, with the technical line
underneath, and nothing secret or personal in it (no tokens, no email address, no row values).
"""

import datetime as dt
from dataclasses import dataclass

import flet as ft

from gym.planImporter import PlanImport, PlanSwitch
from gym.rules.stats import ChartView, ExerciseDetail, HistoryDay, MonthDiary, ProgressLine, WeekSummary, WeightView
from gym.rules.today import TodayView
from gym.state import PlanEntry
from usefulShared.platform import problems
from usefulShared.platform.problems import LogFacts, SyncFacts

appName = "Talon"  # Gym Tracker until 0.4-alpha (AM1.4, AM9.6): only the visible name changed
appVersion = "0.4-alpha"  # the release script checks it matches pyproject.toml (V3a)


@ft.observable
@dataclass
class AppModel:
    """Everything the screens show. Fields are replaced, never changed in place, so each change redraws."""

    screen: str = "starting"  # starting, signIn, downloading, main, problems, importPlan or failed
    busy: str = ""  # what's running right now ("Signing in…"). Buttons wait while it's set
    notice: str = ""  # a message shown once, like a refused entry or a sign-in problem
    failure: str = ""  # why the app can't start (screen "failed")
    today: TodayView | None = None
    deloadAction: str = ""  # the ⋮ menu's deload entry (WD2.4): "start", "stop" or "" (one is running)
    progress: tuple[ProgressLine, ...] = ()  # the Progress tab (SC3.1): the plan's exercises…
    pastProgress: tuple[ProgressLine, ...] = ()  # …and past ones (G10a)
    progressOpen: str = ""  # the exercise whose page is open, "" for the list
    progressRange: str = "3M"  # the chart's span: 3M, 1Y or All
    detail: ExerciseDetail | None = None
    weekOffset: int = 0  # the Week tab (SC4.1): 0 = this week, 1 = last week, …
    week: WeekSummary | None = None
    chartExercise: str = ""  # the Charts tab (SC8.1): the exercise picked, "" for the first one
    chartRange: str = "3M"
    chart: ChartView | None = None
    weightRange: str = "3M"  # the Weight tab (SC5.1)
    weight: WeightView | None = None
    historyMode: str = "days"  # History (HI1.1): "days" or "months" (the diary, DI1.1)
    historyMonth: dt.date | None = None  # the month shown (the PC view's days, and the diary). None = this month
    historyDays: tuple[HistoryDay, ...] = ()
    historyDay: dt.date | None = None  # the day being edited
    historyView: TodayView | None = None  # that day, laid out like Today
    diary: MonthDiary | None = None
    waiting: int = 0  # changes not sent yet: "3 waiting" (SC1.1)
    restUntil: dt.datetime | None = None  # the rest timer (RT1.1): when the rest is over, None when none runs
    restSeconds: int = 0  # how long that rest is in all, for its bar
    restName: str = ""  # the exercise it's for
    banners: tuple[str, ...] = ()  # shown at the top of any tab (18.4a)
    downloaded: int = 0  # first download: "Downloading your data… N rows" (14b)
    problems: tuple[str, ...] = ()  # the Problems page's lines (12d)
    planImport: PlanImport | None = None
    planEntries: tuple[PlanEntry, ...] = ()  # the PC view's Plans tab (SC6.1)
    planSwitch: PlanSwitch | None = None  # switching back to an earlier plan, asked first (SW1.1)
    backupStatus: str = ""  # the PC view's Backup tab: what Back up now or Export CSV just did (BK1.1, EX1.1)
    tab: str = "today"


# --- The Problems report (12d): shared with Ambrosia, in usefulShared.platform.problems --------------------------

def problemsReport(schema: int, sync: SyncFacts, log: LogFacts, now: dt.datetime, unreadablePlans: int = 0,
                   lastBackup: str = "none yet",
                   startedIn: float | None = None) -> tuple[str, ...]:
    """The Problems page as lines of text. Copy puts exactly these on the clipboard (12d)."""
    notes = ([f"Plans that can't be read: {unreadablePlans} (made by a newer app version? Update the app.)"]
             if unreadablePlans else [])
    return problems.problemsReport(f"{appName} {appVersion}", schema, sync, log, now, notes, lastBackup, startedIn)
