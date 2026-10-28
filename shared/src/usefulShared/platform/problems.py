"""The Problems page's report (plan 12d, DG1.1), the same in every app: plain words for each kind of problem, with
the technical line underneath, and nothing secret or personal in it (no tokens, no email address, no row values)."""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field


def plainReason(reason: str) -> str:
    """A refused change's reason in plain words. The cloud's own text stays in the technical line."""
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
        "offline": "no internet right now, trying again every minute",
        "signedOut": "paused: signed out",
        "appTooOld": "stopped: this app needs an update",
        "cloudTooOld": "stopped: the cloud needs an upgrade first",
        "failed": "failed (see below)",
        "busy": "running",
        "versions": "stopped: the cloud and this app don't fit together (see the banner)",
        "none": "not run yet",
    }.get(status, status)


def ago(moment: dt.datetime | None, now: dt.datetime) -> str:
    """"5 min ago", "3 h ago", "2 days ago". "never" for None."""
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


def problemsReport(title: str, schema: int, sync: SyncFacts, log: LogFacts, now: dt.datetime,
                   notes: Sequence[str] = (), lastBackup: str = "none yet",
                   startedIn: float | None = None) -> tuple[str, ...]:
    """The Problems page as lines of text. Copy puts exactly these on the clipboard (12d). title is the app's name
    and version, notes are the app's own lines (Talon's plans it can't read)."""
    started = f" · started in {startedIn:.1f} s" if startedIn is not None else ""  # cold start under 5 s (check 8)
    lines = [f"{title} · schema {schema}{started}",
             f"Sync: {plainSyncStatus(sync.lastStatus)} · last synced {ago(sync.lastSyncAt, now)}",
             f"Waiting to be sent: {sync.waiting}" + (f" (oldest from {ago(sync.oldestWaiting, now)})"
                                                     if sync.oldestWaiting else "")]
    if sync.lastProblem:
        lines.append(f"  last sync problem: {sync.lastProblem}")
    for table, rowId, reason in sync.refused:
        lines.append(f"Refused: {plainReason(reason)}")
        lines.append(f"  {table} {rowId[:8]}…: {reason}")
    lines += notes
    lines.append(f"Last backup: {lastBackup}")
    clean = log.tokenShapedStrings == 0 and log.knownSecretsFound == 0
    lines.append(f"Log check: {log.lines} lines, {log.tokenShapedStrings} token-shaped strings, "
                 f"{log.knownSecretsFound} current tokens found" + (", clean" if clean else ", not clean"))
    if log.recent:
        lines.append("Recent problems:")
        for at, area, plainWords, technical in log.recent:
            lines.append(f"  {at} {area}: {plainWords}")
            if technical:
                lines.append(f"    {technical}")
    else:
        lines.append("Recent problems: none")
    return tuple(lines)
