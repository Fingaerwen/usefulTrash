"""Fetching what changed in the cloud (plan 14b, SY1.1), used by the phone's sync and by the PC view.

Each table is asked for the rows the cloud stored at or after the newest stamp seen so far, minus
5 minutes: the cloud stamps a change a moment before it finishes saving it, so a change saved
slowly could otherwise slip behind the stamp already seen. Pages come oldest first, ordered by
(cloudUpdatedAt, id), and each page starts right after the last row of the one before.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.tables import Table, fromCloud, momentText

overlap = dt.timedelta(minutes=5)
pageSize = 500
beforeEverything = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)  # where a first download starts


class FetchingCloud(Protocol):
    """The one cloud call fetching needs (SupabaseApi has it, tests use a stand-in)."""

    async def fetchRows(self, table: str, columns: Sequence[str], since: str, after: tuple[str, str] | None,
                        limit: int, accessToken: str) -> list[dict]: ...


async def fetchChanges(cloud: FetchingCloud, table: Table, cursor: dt.datetime | None, accessToken: str,
                       apply: Callable[[list[dict[str, Any]], dt.datetime], None]) -> int:
    """Fetches what the cloud stored in `table` since `cursor` (None: everything, a first download).

    Each page goes to apply(rows, newCursor) as Python rows, before the next is asked for, so an
    interrupted fetch keeps what it got and carries on from there next time. Returns how many rows came.
    Raises CloudError: a network problem, or a row the app can't read ("badRow").
    """
    since = cursor - overlap if cursor is not None else beforeEverything
    after: tuple[str, str] | None = None
    fetched = 0
    while True:
        page = await cloud.fetchRows(table.name, table.columnNames, momentText(since), after, pageSize, accessToken)
        try:
            rows = [fromCloud(table, data) for data in page]
        except ValueError as problem:
            raise CloudError(200, "badRow", str(problem)) from None
        if rows:
            newest = max(row["cloudUpdatedAt"] for row in rows)
            cursor = newest if cursor is None else max(cursor, newest)
            apply(rows, cursor)
            fetched += len(rows)
        if len(page) < pageSize:
            return fetched
        after = (momentText(rows[-1]["cloudUpdatedAt"]), rows[-1]["id"])
