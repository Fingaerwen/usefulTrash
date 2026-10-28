"""Making a backup (F14.1): the zip of every table, uploaded to the app's folder in your Google Drive,
the last 3 kept, and a backups row recording it. Beside them, one history file is never rotated out: each
backup is merged into it, with the readable history (BK1.2). The phone does it by itself when the last
backup is 30+ days old. The PC view when you press Back up now (BK1.1). Each app has its own folder, file
names and backups table (AM5.6), so Talon's backups and Ambrosia's never mix.
"""

import datetime as dt
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from usefulShared.backup.backupFile import makeBackupZip, mergeHistory
from usefulShared.backup.driveApi import DriveApi, DriveError
from usefulShared.tables import Table, newRowId

backupEvery = dt.timedelta(days=30)  # the phone's automatic backup (F14.1)
warnAfter = dt.timedelta(days=60)  # the PC view's warning (3.4)
keepBackups = 3  # the last 3 stay in Drive (F14.1)
zipMimeType = "application/zip"


@dataclass(frozen=True, slots=True)
class BackupNames:
    """Where an app's backups go in your Drive and what they're called (AM5.6: each app its own)."""

    folder: str  # the Drive folder
    prefix: str  # the dated backups' names start with it. They're rotated
    history: str  # the history file, kept (BK1.2)
    app: str  # named in manifest.json, so a restore knows whose tables they are


talonBackups = BackupNames("Gym Tracker backups", "GymTracker-backup-", "GymTracker-history.zip", "Gym Tracker")
ambrosiaBackups = BackupNames("Ambrosia backups", "Ambrosia-backup-", "Ambrosia-history.zip", "Ambrosia")


def lastBackup(backupRows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The newest backup on record, from any device."""
    live = [row for row in backupRows if not row["deleted"]]
    return max(live, key=lambda row: row["madeAt"], default=None)


def lastBackupText(backupRows: Sequence[Mapping[str, Any]], now: dt.datetime) -> str:
    """"24 Oct 2026 (phone) · 3 days ago", or "none yet" (the Problems page, the PC view's Backup tab)."""
    live = [row for row in backupRows if not row["deleted"]]
    last = max(live, key=lambda row: row["madeAt"], default=None)
    if last is None:
        return "none yet"
    madeAt = last["madeAt"]
    days = (now - madeAt).days
    when = "today" if days == 0 else "1 day ago" if days == 1 else f"{days} days ago"
    by = "PC view" if last["madeBy"] == "pcView" else "phone"
    return f"{madeAt.day} {madeAt:%b %Y} ({by}) · {when}"


def backupDue(backupRows: Sequence[Mapping[str, Any]], now: dt.datetime) -> bool:
    last = lastBackup(backupRows)
    return last is None or now - last["madeAt"] >= backupEvery


def backupFileName(madeAt: dt.datetime, names: BackupNames = talonBackups) -> str:
    return f"{names.prefix}{madeAt.astimezone(dt.UTC):%Y-%m-%d-%H%M}.zip"


async def withFreshToken(getToken: Callable[[], Awaitable[str]], dropToken: Callable[[str], Awaitable[None]],
                         job: Callable[[str], Awaitable[Any]]) -> Any:
    """Runs job(token). If Drive refuses the token (401: expired or withdrawn), drops it and runs the job once
    more with a fresh one (Phase 0 check 7's rule). The job must be safe to repeat after a refusal."""
    token = await getToken()
    try:
        return await job(token)
    except DriveError as err:
        if err.statusCode != 401:
            raise
    await dropToken(token)
    return await job(await getToken())


async def makeBackup(drive: DriveApi, token: str, rowsByTable: Mapping[str, Sequence[Mapping[str, Any]]],
                     tables: Sequence[Table], schemaVersion: int, userId: str, now: dt.datetime, madeBy: str,
                     readableFiles: Mapping[str, str] | None = None,
                     names: BackupNames = talonBackups) -> dict[str, Any]:
    """Uploads the backup, deletes the app's dated backups beyond the last 3, and merges it into the
    history file with the readable history (BK1.2). Returns the backups row to save (the caller saves it,
    so it syncs like any edit, in its app's backups table)."""
    content = makeBackupZip(rowsByTable, tables, schemaVersion, now, madeBy, appName=names.app)
    folderId = await drive.findOrCreateFolder(names.folder, token)
    fileName = backupFileName(now, names)
    uploaded = await drive.uploadFile(fileName, content, zipMimeType, folderId, token)
    older = await drive.listFiles(f"'{folderId}' in parents and name contains '{names.prefix}' and trashed = false",
                                  token)
    for file in older[keepBackups:]:  # newest first. The history file isn't among them
        await drive.deleteFile(file["id"], token)
    await updateHistory(drive, token, folderId, rowsByTable, tables, schemaVersion, now, madeBy, readableFiles, names)
    return {"id": newRowId(), "userId": userId, "deleted": False, "madeAt": now, "fileName": fileName,
            "driveFileId": uploaded.get("id"), "sizeBytes": len(content), "schemaVersion": schemaVersion,
            "madeBy": madeBy}


async def updateHistory(drive: DriveApi, token: str, folderId: str,
                        rowsByTable: Mapping[str, Sequence[Mapping[str, Any]]], tables: Sequence[Table],
                        schemaVersion: int, now: dt.datetime, madeBy: str,
                        readableFiles: Mapping[str, str] | None, names: BackupNames = talonBackups) -> None:
    """The history file (BK1.2): the earlier one merged with this backup, uploaded, then the earlier one
    deleted, so there's always exactly one, and never none."""
    found = await drive.listFiles(f"'{folderId}' in parents and name = '{names.history}' and trashed = false", token)
    previous = await drive.downloadFile(found[0]["id"], token) if found else None
    content = mergeHistory(previous, rowsByTable, tables, schemaVersion, now, madeBy, readableFiles, appName=names.app)
    await drive.uploadFile(names.history, content, zipMimeType, folderId, token)
    for file in found:
        await drive.deleteFile(file["id"], token)
