"""An in-memory stand-in for the Supabase project, for the sync tests ("sync against a fake cloud",
plan Verification). It follows the same rules as cloud/001_baseTables.sql, which tests/cloud proves
against real Postgres: users reach only their own rows, the newest edit wins, the cloud stamps
cloudUpdatedAt itself, and edits stamped more than 5 minutes ahead of its clock are refused.

Switches let a test cut the connection, lose the answer to a send, or store a row "slowly" (stamped
earlier than rows already fetched). Not a test file itself: pytest only collects test*.py.
"""

import asyncio
import datetime as dt
import hashlib
import time
from collections.abc import Callable, Sequence
from typing import Any

from gym.tables import appSchema
from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.tables import momentText


def _moment(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


class CloudStandIn:
    """The cloud: rows kept as the Data API's JSON, by table and id."""

    def __init__(self, clock: Callable[[], dt.datetime]):
        self.clock = clock
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.signedIn: dict[str, str] = {}  # access token -> user id
        self.schemaVersion = appSchema  # upgraded to what the app is built for
        self.minAppSchema = 1
        self.offline = False
        self.loseNextAnswer = False  # the next send is stored, but its answer never arrives
        self.callsUntilOffline: int | None = None  # the connection drops after this many more calls
        self.acceptsWrongNonce = False  # acts out "Skip nonce checks" switched on in Supabase
        self.dropNextSignIn = False  # the next sign-in request is lost on the way (a moment without internet)
        self.signUpsAllowedFor: set[str] = set()  # Google accounts that may sign in. Others get signup_disabled
        self.refreshTokens: dict[str, str] = {}  # live refresh token -> user id (rotation: each works once)
        self.sessionMinutes = 60
        self.calls: list[str] = []
        # Like the real tables' check constraints (cloud/001): a refused row gives Postgres's error code.
        self.checks: dict[str, Callable[[dict[str, Any]], bool]] = {
            "bodyWeight": lambda row: 0 < row["weightKg"] < 1000,
            "dailySteps": lambda row: 0 <= row["steps"] <= 200000,
        }

    def tokenFor(self, userId: str) -> str:
        """Signs a user in: returns an access token the stand-in accepts."""
        token = f"token{len(self.signedIn) + 1}"
        self.signedIn[token] = userId
        return token

    async def _userFor(self, accessToken: str) -> str:
        """Who the token belongs to. Waits a moment first, as a real request would, so other tasks run."""
        await asyncio.sleep(0)
        if self.callsUntilOffline is not None:
            self.offline = self.offline or self.callsUntilOffline <= 0
            self.callsUntilOffline -= 1
        if self.offline:
            raise CloudError(0, "network", "OSError: no connection")
        if accessToken not in self.signedIn:
            raise CloudError(401, "PGRST303", "JWT expired")
        return self.signedIn[accessToken]

    def visibleRows(self, table: str, userId: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.get(table, {}).values() if row["userId"] == userId]

    # --- Sign-in (Supabase Auth) ------------------------------------------------------------

    async def signInWithGoogleIdToken(self, idToken: str, rawNonce: str) -> dict:
        """The fake Google ID token is "googleIdToken:<account>:<hashed nonce>", like the real one carrying
        the hashed nonce inside. Supabase hashes the raw nonce and compares."""
        await asyncio.sleep(0)
        if self.offline or self.dropNextSignIn:
            self.dropNextSignIn = False
            raise CloudError(0, "network", "OSError: no connection")
        _, account, hashedNonce = idToken.split(":")
        if hashlib.sha256(rawNonce.encode()).hexdigest() != hashedNonce and not self.acceptsWrongNonce:
            raise CloudError(400, "bad_oauth_callback", "Nonces mismatch")
        if account not in self.signUpsAllowedFor:
            raise CloudError(422, "signup_disabled", "Signups not allowed for this instance")
        return self._newSession(account)

    async def refreshSession(self, refreshToken: str) -> dict:
        await asyncio.sleep(0)
        if self.offline:
            raise CloudError(0, "network", "OSError: no connection")
        if refreshToken not in self.refreshTokens:
            raise CloudError(400, "refresh_token_already_used", "Invalid Refresh Token: Already Used")
        return self._newSession(self.refreshTokens.pop(refreshToken))

    async def signOut(self, accessToken: str) -> None:
        await self._userFor(accessToken)

    def _newSession(self, userId: str) -> dict:
        refreshToken = f"refresh{len(self.refreshTokens) + len(self.signedIn) + 1}"
        self.refreshTokens[refreshToken] = userId
        expiresAt = time.time() + self.sessionMinutes * 60  # the session keeper checks against real time
        return {"access_token": self.tokenFor(userId), "refresh_token": refreshToken, "expires_at": expiresAt,
                "user": {"id": userId, "email": "testAccount"}}

    # --- The calls sync makes ----------------------------------------------------------------

    async def readCloudInfo(self, accessToken: str) -> tuple[int, int]:
        await self._userFor(accessToken)
        self.calls.append("cloudInfo")
        return self.schemaVersion, self.minAppSchema

    async def upsertRows(self, table: str, rows: Sequence[dict[str, Any]], accessToken: str) -> None:
        """Like INSERT ... ON CONFLICT (id) DO UPDATE with the keepNewestEdit trigger: one statement,
        so one refused row refuses the whole request."""
        userId = await self._userFor(accessToken)
        self.calls.append(f"upsert {table} {len(rows)}")
        stored = self.rows.setdefault(table, {})
        accepted: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row["userId"] != userId:
                raise CloudError(403, "42501", f'new row violates row-level security policy for table "{table}"')
            edit = _moment(row["updatedAt"])
            if edit > self.clock() + dt.timedelta(minutes=5):
                raise CloudError(400, "P0001", "futureEdit: this change is stamped in the future; check the "
                                               "device's clock.")
            if not self.checks.get(table, lambda _: True)(row):
                raise CloudError(400, "23514", f'new row for relation "{table}" violates check constraint')
            existing = accepted.get(row["id"]) or stored.get(row["id"])
            if existing is not None and existing["userId"] != userId:
                raise CloudError(403, "42501", f'new row violates row-level security policy for table "{table}"')
            if existing is not None and _moment(existing["updatedAt"]) >= edit:
                continue  # the trigger quietly ignores an edit that isn't newer
            accepted[row["id"]] = dict(row, cloudUpdatedAt=momentText(self.clock()))
        stored.update(accepted)
        if self.loseNextAnswer:
            self.loseNextAnswer = False
            raise CloudError(0, "network", "TimeoutError: the answer never came")

    async def fetchRows(self, table: str, columns: Sequence[str], since: str, after: tuple[str, str] | None,
                        limit: int, accessToken: str) -> list[dict[str, Any]]:
        """Like GET with cloudUpdatedAt=gte.since, the (cloudUpdatedAt, id) keyset, order and limit."""
        userId = await self._userFor(accessToken)
        self.calls.append(f"fetch {table}")
        found = [row for row in self.visibleRows(table, userId) if _moment(row["cloudUpdatedAt"]) >= _moment(since)]
        if after is not None:
            lastStamp, lastId = _moment(after[0]), after[1]
            found = [row for row in found if (_moment(row["cloudUpdatedAt"]), row["id"]) > (lastStamp, lastId)]
        found.sort(key=lambda row: (_moment(row["cloudUpdatedAt"]), row["id"]))
        return [{name: row[name] for name in columns} for row in found[:limit]]

    # --- Helpers for setting up tests ----------------------------------------------------------

    def storeDirectly(self, table: str, row: dict[str, Any], stampedAt: dt.datetime | None = None) -> None:
        """Puts a row (the Data API's JSON) in the cloud as if another device had sent it. stampedAt
        earlier than now acts out a slow save: stamped before rows that were fetched already."""
        self.rows.setdefault(table, {})[row["id"]] = dict(row, cloudUpdatedAt=momentText(stampedAt or self.clock()))
