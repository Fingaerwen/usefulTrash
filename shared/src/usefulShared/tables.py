"""Table definitions (plan 14): the columns of every synced table and how their values are kept on the
phone and sent to the cloud. One place for this, so the phone's database, sync and backups always
agree with the cloud scripts in cloud/ (a test compares them with the real tables).

Rows are plain dicts of Python values: uuid and text are str, integers int, decimals float, booleans
bool, dates datetime.date, moments timezone-aware datetime.datetime in UTC, and JSON columns the
parsed JSON. This module holds the tables every app shares; each app adds its own (gym/tables.py).
"""

import datetime as dt
import json
import math
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

moment = "timestamp with time zone"  # Postgres's name for timestamptz
oneMicrosecond = dt.timedelta(microseconds=1)

# Made once with uuid5(NAMESPACE_URL, "https://github.com/Fingaerwen/usefulTrash/rowIds"). Never change
# it: every one-per-day row's ID is worked out from it, so a new value would duplicate those rows.
idNamespace = uuid.UUID("bc4b818e-5654-50eb-8ff8-4ddf39bda2ea")


@dataclass(frozen=True, slots=True)
class Column:
    """One column. cloudType is the type exactly as Postgres names it, e.g. "numeric(5,2)"."""

    name: str
    cloudType: str
    required: bool = True  # False: may be empty (NULL)
    stampedByCloud: bool = False  # the cloud sets it on every stored change; a device never sends it


@dataclass(frozen=True, slots=True)
class Table:
    """One synced table: its columns in the cloud's order (the common five first)."""

    name: str
    columns: tuple[Column, ...]
    dayKey: tuple[str, ...] = ()  # the columns that, with your user ID, make a row's ID (DT1.1); () = random

    @property
    def columnNames(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> Column:
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f"{self.name} has no column {name}")


# Every synced row has these (plan 14, SY1.1).
commonColumns = (
    Column("id", "uuid"),
    Column("userId", "uuid"),
    Column("updatedAt", moment),  # when the edit was made, from the device's clock; the newest edit wins
    Column("deleted", "boolean"),  # rows are never really removed: deleting is an edit like any other
    Column("cloudUpdatedAt", moment, stampedByCloud=True),  # when the cloud stored it; used only for fetching
)


def table(name: str, *columns: Column, dayKey: tuple[str, ...] = ()) -> Table:
    """A synced table: the common columns, then its own."""
    return Table(name, commonColumns + columns, dayKey)


# --- The tables every app shares ---------------------------------------------------------------

bodyWeight = table("bodyWeight", Column("date", "date"), Column("weightKg", "numeric(5,2)"), dayKey=("date",))
dailySteps = table("dailySteps", Column("date", "date"), Column("steps", "integer"), dayKey=("date",))
backups = table(
    "backups",
    Column("madeAt", moment),
    Column("fileName", "text"),
    Column("driveFileId", "text", required=False),
    Column("sizeBytes", "bigint", required=False),
    Column("schemaVersion", "integer"),
    Column("madeBy", "text"),  # "phone" or "pcView"
)
sharedTables = (bodyWeight, dailySteps, backups)


# --- IDs and edit times -------------------------------------------------------------------------

def newRowId() -> str:
    """A random ID, for rows that aren't one per day (plan imports, backups)."""
    return str(uuid.uuid4())


def dayRowId(table: Table, userId: str, **key: Any) -> str:
    """The ID of a one-per-day row (DT1.1 / DT2.1): the same table, user and date (plus exercise) always
    give the same ID, so the phone and the PC view logging the same thing make one row, never two."""
    if not table.dayKey:
        raise ValueError(f"{table.name} rows get random IDs")
    if set(key) != set(table.dayKey):
        raise ValueError(f"{table.name} IDs are made from {', '.join(table.dayKey)}")
    parts = [table.name, str(uuid.UUID(userId))]
    parts += [value.isoformat() if isinstance(value, dt.date) else str(value) for value in
              (key[name] for name in table.dayKey)]
    return str(uuid.uuid5(idNamespace, "/".join(parts)))


def editTime(now: dt.datetime, previous: dt.datetime | None = None) -> dt.datetime:
    """The time an edit is stamped with: now, or just after the version it replaces if the clock is
    behind that, so an edit always beats the version it was made from (the newest edit wins, F11.1)."""
    now = now.astimezone(dt.UTC)
    if previous is not None and now <= previous:
        return previous + oneMicrosecond
    return now


# --- Values: checking and converting -------------------------------------------------------------

_numericPattern = re.compile(r"numeric\((\d+),(\d+)\)")


def checkRow(table: Table, row: Mapping[str, Any]) -> None:
    """Raises ValueError if the row lacks a column, has an unknown one, or holds a value of the wrong
    kind. Messages name the table and column, never the value (they may end up in the log)."""
    unknown = set(row) - set(table.columnNames)
    if unknown:
        raise ValueError(f"{table.name} has no column {', '.join(sorted(unknown))}")
    for column in table.columns:
        if column.name not in row:
            raise ValueError(f"{table.name}.{column.name} is missing")
        _checkValue(table, column, row[column.name])


def _checkValue(table: Table, column: Column, value: Any) -> None:
    where = f"{table.name}.{column.name}"
    if value is None:
        if column.required and not column.stampedByCloud:  # the cloud's stamp is empty until it's stored there
            raise ValueError(f"{where} can't be empty")
        return
    kind = column.cloudType
    if kind == "uuid":
        if not isinstance(value, str) or not _isUuid(value):
            raise ValueError(f"{where} must be a UUID in text form")
    elif kind == "text":
        if not isinstance(value, str):
            raise ValueError(f"{where} must be text")
    elif kind in ("integer", "bigint"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{where} must be a whole number")
    elif kind.startswith("numeric"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{where} must be a number")
        precision, scale = _precisionAndScale(kind)
        scaled = value * 10**scale
        if abs(scaled - round(scaled)) > 1e-6:  # the cloud would round it, and the copies would differ
            raise ValueError(f"{where} can have at most {scale} decimals")
        if abs(value) >= 10 ** (precision - scale):
            raise ValueError(f"{where} is too big")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{where} must be true or false")
    elif kind == "date":
        if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
            raise ValueError(f"{where} must be a date")
    elif kind == moment:
        if not isinstance(value, dt.datetime) or value.utcoffset() is None:
            raise ValueError(f"{where} must be a moment with a time zone")
    elif kind == "jsonb":
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError(f"{where} must be JSON") from None
    else:
        raise ValueError(f"{where} has an unknown type {kind}")


def _isUuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value  # canonical form only: lower case with dashes
    except ValueError:
        return False


def toCloud(table: Table, row: Mapping[str, Any]) -> dict[str, Any]:
    """A checked row as JSON for the cloud's Data API, without the columns the cloud stamps itself."""
    checkRow(table, row)
    return {column.name: _toText(column, row[column.name], forCloud=True)
            for column in table.columns if not column.stampedByCloud}


def fromCloud(table: Table, data: Mapping[str, Any]) -> dict[str, Any]:
    """A row from the Data API's JSON as Python values, checked. Raises ValueError if it's malformed."""
    if not isinstance(data, Mapping):
        raise ValueError(f"{table.name}: a row must be a JSON object")
    missing = [name for name in table.columnNames if name not in data]
    if missing:
        raise ValueError(f"{table.name}: the cloud's row has no {', '.join(missing)}")
    row = {column.name: _fromText(table, column, data[column.name], fromJson=True) for column in table.columns}
    checkRow(table, row)
    return row


def toLocal(table: Table, row: Mapping[str, Any]) -> tuple[Any, ...]:
    """A checked row as SQLite values, in column order."""
    checkRow(table, row)
    return tuple(_toText(column, row[column.name], forCloud=False) for column in table.columns)


def fromLocal(table: Table, values: Sequence[Any]) -> dict[str, Any]:
    """A row read from SQLite (in column order) as Python values."""
    return {column.name: _fromText(table, column, value, fromJson=False)
            for column, value in zip(table.columns, values, strict=True)}


def _toText(column: Column, value: Any, forCloud: bool) -> Any:
    """One value for the cloud (JSON) or for SQLite. Moments become fixed-width UTC text, so they sort
    as text; dates become YYYY-MM-DD."""
    if value is None:
        return None
    kind = column.cloudType
    if kind == moment:
        return value.astimezone(dt.UTC).isoformat(timespec="microseconds")
    if kind == "date":
        return value.isoformat()
    if kind.startswith("numeric"):
        return round(float(value), _precisionAndScale(kind)[1])
    if kind == "boolean" and not forCloud:
        return int(value)
    if kind == "jsonb" and not forCloud:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return value


def _fromText(table: Table, column: Column, value: Any, fromJson: bool) -> Any:
    """One value read from the cloud's JSON (fromJson) or from SQLite, as its Python value. Anything
    that can't be read raises ValueError; checkRow then checks the kinds."""
    if value is None:
        return None
    kind = column.cloudType
    try:
        if kind == moment:
            return dt.datetime.fromisoformat(value).astimezone(dt.UTC)
        if kind == "date":
            return dt.date.fromisoformat(value)
        if kind.startswith("numeric") and isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if kind == "uuid" and isinstance(value, str):
            return str(uuid.UUID(value))
        if not fromJson and kind == "boolean" and isinstance(value, int):
            return bool(value)  # SQLite keeps booleans as 0 and 1
        if not fromJson and kind == "jsonb":
            return json.loads(value)  # SQLite keeps JSON as text
    except (TypeError, ValueError):
        raise ValueError(f"{table.name}.{column.name} can't be read") from None
    return value


def _precisionAndScale(cloudType: str) -> tuple[int, int]:
    """The digits in all and after the point that a numeric(precision,scale) column keeps."""
    match = _numericPattern.fullmatch(cloudType)
    if match is None:
        raise ValueError(f"not a numeric(precision,scale) type: {cloudType}")
    return int(match.group(1)), int(match.group(2))
