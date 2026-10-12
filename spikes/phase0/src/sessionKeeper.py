"""Keeps the Supabase session for the Phase 0 spike: in memory while the app runs, and encrypted on the
phone between runs through the secureStore extension (plan T1.1).

Rules:
- Only what's needed is kept: tokens, expiry time, user ID and email.
- Supabase rotates refresh tokens: every renewal retires the old one, and reusing a retired one ends the
  whole sign-in. So a renewed session is saved before it's used, and renewals never run at the same time.
- The saved session is only deleted when Supabase clearly says the refresh token is dead, or on sign-out.
  Being offline never signs you out.
- Nothing here prints or logs tokens."""

import asyncio
import json
import time

from supabaseApi import SupabaseError

# Supabase error codes that mean "this refresh token will never work again": only a new sign-in helps.
deadSessionCodes = {
    "refresh_token_not_found", "refresh_token_already_used", "session_not_found", "session_expired",
    "user_not_found", "user_banned", "bad_jwt",
}


def isDeadSession(err: SupabaseError) -> bool:
    """True when a renewal failed because the refresh token itself is unusable: one of the codes above, or a
    400 about the refresh token (a damaged token gets "400 validation_failed: Refresh token is not valid").
    Network problems (status 0), rate limits and server errors are never treated as dead."""
    return err.errorCode in deadSessionCodes or (err.statusCode == 400 and "refresh token" in err.message.lower())


class MemoryStore:
    """Stand-in for the secureStore extension in the PC view (check 6): the session lives in the browser
    tab's memory only. Nothing goes into the browser's storage, and closing the tab signs you out."""

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

    async def info(self) -> dict:
        return {"status": "ok", "keyExists": False, "storedItems": len(self._items)}


class SessionKeeper:
    """The current Supabase session, saved encrypted under one secure store item."""

    storeName = "supabaseSession"
    renewMarginSec = 300  # renew when less than 5 minutes are left

    def __init__(self, supabase, secureStore):
        self.supabase = supabase
        self.secureStore = secureStore
        self.session: dict = {}
        self.lastProblem = ""  # last save/restore/renew problem, for the status line
        self.renewCount = 0  # renewals since the app started (shown on screen)
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

    async def save(self, newSession: dict) -> bool:
        """Uses newSession from now on and saves it encrypted. Returns False if saving failed
        (it's still used in memory, but won't survive closing the app)."""
        self.session = self.trim(newSession)
        answer = await self.secureStore.save(self.storeName, json.dumps(self.session))
        if answer.get("status") == "ok":
            return True
        self.lastProblem = f"couldn't save the session: {answer.get('errorType', '')} {answer.get('message', '')}"
        return False

    async def restore(self) -> str:
        """Loads the saved session. Returns "restored", "none", "unreadable" (deleted, sign in again) or "error"."""
        answer = await self.secureStore.load(self.storeName)
        status = answer.get("status")
        if status == "ok":
            try:
                self.session = self.trim(json.loads(answer["value"]))
                return "restored"
            except (ValueError, KeyError, TypeError):
                await self.forget()
                return "unreadable"
        if status == "missing":
            return "none"
        self.lastProblem = f"{answer.get('errorType', status)}: {answer.get('message', '')}"
        return "unreadable" if status == "unreadable" else "error"

    async def forget(self) -> None:
        """Signs out on this phone: drops the session from memory and deletes the saved copy."""
        self.session = {}
        await self.secureStore.delete(self.storeName)

    async def freshAccessToken(self) -> str:
        """Returns an access token with at least 5 minutes left, renewing the session first if needed.
        Raises SupabaseError: statusCode 0 means offline (the session is kept)."""
        async with self._renewLock:
            if not self.isSignedIn():
                raise SupabaseError(401, "notSignedIn", "Not signed in")
            if self.session.get("expires_at", 0) - time.time() > self.renewMarginSec:
                return self.session["access_token"]
            await self._renew()
            return self.session["access_token"]

    async def renewNow(self) -> None:
        """Renews the session even if the access token is still fresh (to test renewals)."""
        async with self._renewLock:
            if not self.isSignedIn():
                raise SupabaseError(401, "notSignedIn", "Not signed in")
            await self._renew()

    async def _renew(self) -> None:
        """Swaps the refresh token for a new session and saves it at once. Call only while holding the lock."""
        try:
            newSession = await self.supabase.refreshSession(self.session["refresh_token"])
        except SupabaseError as err:
            if isDeadSession(err):
                await self.forget()  # this sign-in is over on Supabase's side
            raise
        self.renewCount += 1
        await self.save(newSession)  # the old refresh token is already retired: keep the new one first
