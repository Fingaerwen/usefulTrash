"""What the screens draw (plan 3b: declarative screens): one observable model per app. The controller
(phoneApp.py or pcApp.py) changes it; every screen that shows a changed field redraws by itself.

Also the Problems report (12d, DG1.1): plain words for each kind of problem, with the technical line
underneath, and nothing secret or personal in it (no tokens, no email address, no row values).
"""

import datetime as dt
from dataclasses import dataclass, field

import flet as ft

from gym.planImporter import PlanImport
from gym.rules.stats import ExerciseDetail, ProgressLine, WeekSummary
from gym.rules.today import TodayView

appName = "Gym Tracker"
appVersion = "0.1-alpha"  # the release script checks it matches pyproject.toml (V3a)


@ft.observable
@dataclass
class AppModel:
    """Everything the screens show. Fields are replaced, never changed in place, so each change redraws."""

    screen: str = "starting"  # starting, signIn, downloading, main, problems, importPlan or failed
    busy: str = ""  # what's running right now ("Signing in…"); buttons wait while it's set
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
    waiting: int = 0  # changes not sent yet: "3 waiting" (SC1.1)
    banners: tuple[str, ...] = ()  # shown at the top of any tab (18.4a)
    downloaded: int = 0  # first download: "Downloading your data… N rows" (14b)
    problems: tuple[str, ...] = ()  # the Problems page's lines (12d)
    planImport: PlanImport | None = None
    planLines: tuple[str, ...] = ()  # the PC view's Plans tab (SC6.1)
    tab: str = "today"


# --- Plain words for the cloud's reasons (12d) ------------------------------------------------

def plainReason(reason: str) -> str:
    """A refused change's reason in plain words; the cloud's own text stays in the technical line."""
    if reason.startswith("P0001: futureEdit"):
        return "Your phone's clock seems to be ahead. Set it to automatic time, then tap Try again."
    if reason.startswith("23514"):
        return "The cloud refused a value in this entry as impossible."
    if reason.startswith("42501"):
        return "The cloud says this entry belongs to another account."
    if reason.startswith("badRow"):
        return "This entry couldn't be put into the cloud's form."
    return "The cloud refused this entry."


def plainSyncStatus(status: str) -> str:
    return {
        "done": "up to date",
        "offline": "no internet right now; trying again every minute",
        "signedOut": "paused: signed out",
        "appTooOld": "stopped: this app needs an update",
        "cloudTooOld": "stopped: the cloud needs an upgrade first",
        "failed": "failed (see below)",
        "busy": "running",
        "versions": "stopped: the cloud and this app don't fit together (see the banner)",
        "none": "not run yet",
    }.get(status, status)


def ago(moment: dt.datetime | None, now: dt.datetime) -> str:
    """"5 min ago", "3 h ago", "2 days ago"; "never" for None."""
    if moment is None:
        return "never"
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 90:
        return "just now"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} min ago"
    if seconds < 36 * 3600:
        return f"{round(seconds / 3600)} h ago"
    return f"{round(seconds / 86400)} days ago"


@dataclass(frozen=True, slots=True)
class SyncFacts:
    """What the Problems page says about sync."""

    lastStatus: str
    lastProblem: str
    lastSyncAt: dt.datetime | None
    waiting: int
    oldestWaiting: dt.datetime | None
    refused: tuple[tuple[str, str, str], ...]  # (table, row id, reason)


@dataclass(frozen=True, slots=True)
class LogFacts:
    lines: int
    tokenShapedStrings: int
    knownSecretsFound: int
    recent: tuple[tuple[str, str, str, str], ...] = field(default=())  # (time, area, plain words, technical)


def problemsReport(schema: int, sync: SyncFacts, log: LogFacts, now: dt.datetime, unreadablePlans: int = 0,
                   lastBackup: str = "none yet (backups come with 0.3-alpha)",
                   startedIn: float | None = None) -> tuple[str, ...]:
    """The Problems page as lines of text; Copy puts exactly these on the clipboard (12d)."""
    started = f" · started in {startedIn:.1f} s" if startedIn is not None else ""  # cold start under 5 s (check 8)
    lines = [f"{appName} {appVersion} · schema {schema}{started}",
             f"Sync: {plainSyncStatus(sync.lastStatus)} · last synced {ago(sync.lastSyncAt, now)}",
             f"Waiting to be sent: {sync.waiting}" + (f" (oldest from {ago(sync.oldestWaiting, now)})"
                                                     if sync.oldestWaiting else "")]
    if sync.lastProblem:
        lines.append(f"  last sync problem: {sync.lastProblem}")
    for table, rowId, reason in sync.refused:
        lines.append(f"Refused: {plainReason(reason)}")
        lines.append(f"  {table} {rowId[:8]}…: {reason}")
    if unreadablePlans:
        lines.append(f"Plans that can't be read: {unreadablePlans} (made by a newer app version? Update the app.)")
    lines.append(f"Last backup: {lastBackup}")
    clean = log.tokenShapedStrings == 0 and log.knownSecretsFound == 0
    lines.append(f"Log check: {log.lines} lines, {log.tokenShapedStrings} token-shaped strings, "
                 f"{log.knownSecretsFound} current tokens found" + (" ✓" if clean else " ✗"))
    if log.recent:
        lines.append("Recent problems:")
        for at, area, plainWords, technical in log.recent:
            lines.append(f"  {at} {area}: {plainWords}")
            if technical:
                lines.append(f"    {technical}")
    else:
        lines.append("Recent problems: none")
    return tuple(lines)
