"""The backup file (F14.1, G9.3b, F13.1): one zip holding a CSV file per table and manifest.json.

Every row is in it, deleted ones included, so a restore is exact (plan 14b). The manifest records the
data-structure version, so an older backup still restores after the tables have grown. Values are
written as the cloud reads them: dates and moments in ISO form, JSON columns as JSON text, true/false,
and an empty cell for no value.
"""

import csv
import datetime as dt
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

from usefulShared.tables import Column, Table, momentText

manifestName = "manifest.json"


def cellText(column: Column, value: Any) -> str:
    """One value as CSV text, the way the cloud reads it back."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.datetime):
        return momentText(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    if column.cloudType == "jsonb":
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return repr(value) if isinstance(value, float) else str(value)


def tableCsv(table: Table, rows: Sequence[Mapping[str, Any]]) -> str:
    """A table as CSV: a header with its columns, then its rows in ID order."""
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(table.columnNames)
    for row in sorted(rows, key=lambda row: row["id"]):
        writer.writerow([cellText(column, row.get(column.name)) for column in table.columns])
    return text.getvalue()


def makeBackupZip(rowsByTable: Mapping[str, Sequence[Mapping[str, Any]]], tables: Sequence[Table],
                  schemaVersion: int, madeAt: dt.datetime, madeBy: str,
                  extraFiles: Mapping[str, str] | None = None) -> bytes:
    """The backup zip: <table>.csv for each table, manifest.json, and any extra files (Export CSV's
    readable sets.csv, EX1.1)."""
    buffer = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in tables:
            rows = rowsByTable.get(table.name, [])
            archive.writestr(f"{table.name}.csv", tableCsv(table, rows))
            counts[table.name] = len(rows)
        manifest = {"app": "usefulTrash", "schemaVersion": schemaVersion, "madeAt": momentText(madeAt),
                    "madeBy": madeBy, "rows": counts}
        archive.writestr(manifestName, json.dumps(manifest, indent=2) + "\n")
        for name, content in (extraFiles or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def readBackupZip(content: bytes) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    """A backup's manifest and its tables' rows as text, by column name (tools/restoreBackup.py)."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest = json.loads(archive.read(manifestName))
        rows = {name: list(csv.DictReader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))
                for name in manifest["rows"]}
    return manifest, rows
