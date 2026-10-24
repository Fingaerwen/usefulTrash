"""Making a backup (F14.1): the zip of every table, uploaded to the app's folder in your Google Drive,
the last 3 kept, and a backups row recording it. The phone does it by itself when the last backup is 30+
days old; the PC view when you press Back up now (BK1.1).
"""

import datetime as dt
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from usefulShared.backup.backupFile import makeBackupZip
from usefulShared.backup.driveApi import DriveApi, DriveError
from usefulShared.tables import Table, newRowId

backupEvery = dt.timedelta(days=30)  # the phone's automatic backup (F14.1)
warnAfter = dt.timedelta(days=60)  # the PC view's warning (3.4)
keepBackups = 3  # the last 3 stay in Drive (F14.1)
folderName = "Gym Tracker backups"
zipMimeType = "application/zip"


def lastBackup(backupRows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The newest backup on record, from any device."""
    live = [row for row in backupRows if not row["deleted"]]
    return max(live, key=lambda row: row["madeAt"], default=None)


def backupDue(backupRows: Sequence[Mapping[str, Any]], now: dt.datetime) -> bool:
    last = lastBackup(backupRows)
    return last is None or now - last["madeAt"] >= backupEvery


def backupFileName(madeAt: dt.datetime) -> str:
    return f"GymTracker-backup-{madeAt.astimezone(dt.UTC):%Y-%m-%d-%H%M}.zip"


async def withFreshToken(getToken: Callable[[], Awaitable[str]], dropToken: Callable[[str], Awaitable[None]],
                         job: Callable[[str], Awaitable[Any]]) -> Any:
    """Runs job(token); if Drive refuses the token (401: expired or withdrawn), drops it and runs the job once
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
                     extraFiles: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Uploads the backup and deletes the app's older backups beyond the last 3; returns the backups row
    to save (the caller saves it, so it syncs like any edit)."""
    content = makeBackupZip(rowsByTable, tables, schemaVersion, now, madeBy, extraFiles)
    folderId = await drive.findOrCreateFolder(folderName, token)
    fileName = backupFileName(now)
    uploaded = await drive.uploadFile(fileName, content, zipMimeType, folderId, token)
    older = await drive.listFiles(f"'{folderId}' in parents and mimeType = '{zipMimeType}' and trashed = false",
                                  token)
    for file in older[keepBackups:]:  # newest first
        await drive.deleteFile(file["id"], token)
    return {"id": newRowId(), "userId": userId, "deleted": False, "madeAt": now, "fileName": fileName,
            "driveFileId": uploaded.get("id"), "sizeBytes": len(content), "schemaVersion": schemaVersion,
            "madeBy": madeBy}
