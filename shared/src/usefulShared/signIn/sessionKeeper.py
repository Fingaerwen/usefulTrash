"""Keeps the Supabase session: in memory while the app runs, and between runs encrypted on the phone
through the secureStore extension (T1.1), or only in the browser tab's memory in the PC view (check 6).
Moved from the Phase 0 spike, where it was proven on the phone (check 4).

Rules:
- Only what's needed is kept: the tokens, their expiry time, the user's ID and email address.
- Supabase rotates refresh tokens: every renewal retires the old one, and reusing a retired one ends the
  whole sign-in. So a renewed session is saved before it's used, and renewals never run at the same time.
- The saved session is deleted only when Supabase clearly says the refresh token is dead, or on sign-out.
  Being offline never signs you out.
- Nothing here prints or logs tokens.
"""

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

from usefulShared.cloud.supabaseApi import CloudError

# Supabase error codes that mean "this refresh token will never work again": only a new sign-in helps.
deadSessionCodes = {
    "refresh_token_not_found", "refresh_token_already_used", "session_not_found", "session_expired",
    "user_not_found", "user_banned", "bad_jwt",
}


def isDeadSession(problem: CloudError) -> bool:
    """True when a renewal failed because the refresh token itself is unusable: one of the codes above,
    or a 400 about the refresh token (a damaged one gets "400 validation_failed: Refresh token is not
    valid"). Network problems, rate limits and server errors never count as dead."""
    return problem.errorCode in deadSessionCodes or (
        problem.statusCode == 400 and "refresh token" in problem.message.lower())


class SecretStore(Protocol):
    """Where the session is saved: the secureStore extension on the phone, MemoryStore in the PC view."""

    async def save(self, name: str, value: str) -> dict: ...

    async def load(self, name: str) -> dict: ...

    async def delete(self, name: str) -> dict: ...


class RenewingCloud(Protocol):
    async def refreshSession(self, refreshToken: str) -> dict: ...


class MemoryStore:
    """The PC view's stand-in for secureStore: the session lives in the browser tab's memory only.
    Nothing goes into the browser's storage, and closing the tab signs you out (check 6)."""

    def __init__(self):
        self._items: dict[str, str] = {}

    async def save(self, name: str, value: str) -> dict:
        self._items[name] = value
        return {"status": "ok"}

    async def load(self, name: str) -> dict:
        return {"status": "ok", "value": self._items[name]} if name in self._items else {"status": "missing"}

    async def delete(self, name: str) -> dict:
        self._items.pop(name, None)
        return {"status": "ok"}


class SessionKeeper:
    """The current Supabase session, saved under one secret store item."""

    storeName = "supabaseSession"
    renewMarginSec = 300  # renew when less than 5 minutes are left

    def __init__(self, cloud: RenewingCloud, secretStore: SecretStore, clock: Callable[[], float] = time.time):
        self.cloud = cloud
        self.secretStore = secretStore
        self.clock = clock  # seconds since 1970, like Supabase's expires_at
        self.session: dict[str, Any] = {}
        self.lastProblem = ""  # the last save, restore or renewal problem, for the Problems page (12d)
        self._renewLock = asyncio.Lock()

    @staticmethod
    def trim(session: dict) -> dict:
        """Keeps only the fields the app needs."""
        user = session.get("user") or {}
        return {
            "access_token": session.get("access_token", ""),
            "refresh_token": session.get("refresh_token", ""),
            "expires_at": session.get("expires_at", 0),
            "user": {"id": user.get("id", ""), "email": user.get("email", "")},
        }

    def isSignedIn(self) -> bool:
        return bool(self.session.get("refresh_token"))

    def userId(self) -> str:
        return str((self.session.get("user") or {}).get("id", ""))

    def email(self) -> str:
        """The signed-in Google account, for Drive access (never logged or shown in the Problems report)."""
        return str((self.session.get("user") or {}).get("email", ""))

    async def save(self, newSession: dict) -> bool:
        """Uses newSession from now on and saves it. Returns False if saving failed (it's still used in
        memory, but won't survive closing the app)."""
        self.session = self.trim(newSession)
        answer = await self.secretStore.save(self.storeName, json.dumps(self.session))
        if answer.get("status") == "ok":
            return True
        self.lastProblem = f"couldn't save the session: {answer.get('errorType', '')} {answer.get('message', '')}"
        return False

    async def restore(self) -> str:
        """Loads the saved session. Returns "restored", "none", "unreadable" (it was deleted: sign in
        again) or "error"."""
        answer = await self.secretStore.load(self.storeName)
        status = answer.get("status")
        if status == "ok":
            try:
                self.session = self.trim(json.loads(answer["value"]))
                return "restored"
            except (ValueError, KeyError, TypeError, AttributeError):
                await self.forget()
                return "unreadable"
        if status == "missing":
            return "none"
        self.lastProblem = f"{answer.get('errorType', status)}: {answer.get('message', '')}"
        return "unreadable" if status == "unreadable" else "error"

    async def forget(self) -> None:
        """Signs out on this device: drops the session from memory and deletes the saved copy."""
        self.session = {}
        await self.secretStore.delete(self.storeName)

    async def freshAccessToken(self) -> str:
        """An access token with at least 5 minutes left, renewing the session first if needed.
        Raises CloudError: status 0 means offline (the session is kept); "notSignedIn" if there's none."""
        async with self._renewLock:
            if not self.isSignedIn():
                raise CloudError(401, "notSignedIn", "Not signed in")
            if self.session.get("expires_at", 0) - self.clock() > self.renewMarginSec:
                return self.session["access_token"]
            await self._renew()
            return self.session["access_token"]

    async def renewNow(self) -> None:
        """Renews the session even if the access token still looks fresh (the cloud refused it)."""
        async with self._renewLock:
            if not self.isSignedIn():
                raise CloudError(401, "notSignedIn", "Not signed in")
            await self._renew()

    async def _renew(self) -> None:
        """Swaps the refresh token for a new session and saves it at once. Only while holding the lock."""
        try:
            newSession = await self.cloud.refreshSession(self.session["refresh_token"])
        except CloudError as problem:
            if isDeadSession(problem):
                self.lastProblem = f"signed out: {problem.errorCode}"
                await self.forget()  # this sign-in is over on Supabase's side
            raise
        await self.save(newSession)  # the old refresh token is already retired: keep the new one first
