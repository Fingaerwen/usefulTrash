"""Drive access for the Phase 0 spike (check 7): short-lived access tokens from Google Play services
(the nativeGoogleSignIn extension), and one retry with a fresh token when Drive refuses one.

Rules:
- No client secret and no refresh token in the app: Google Play services keeps the long-lived Drive
  permission and hands out access tokens that last about an hour (plan R2). The app simply asks again
  whenever it needs one. Play services renews expired tokens itself.
- Tokens live in memory only. Nothing here prints, logs or saves them. On screen a token only appears
  as a fingerprint (8 characters of its SHA-256), which tells tokens apart but can't be turned back.
- No Google screen ever appears unless asked for (interactive=True), so a backup that runs when the
  app opens can't pop up a permission screen by surprise."""

import asyncio
import hashlib
import time

from googleDriveApi import DriveError


class DriveAccessError(Exception):
    """Google Play services didn't hand out a token. kind: "needsConsent" (allow Drive access first),
    "cancelled", or Play services' error type."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind
        self.message = message


def tokenFingerprint(token: str) -> str:
    """First 8 hex characters of the token's SHA-256: enough to tell two tokens apart, useless to anyone else."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8] if token else "none"


class DriveKeeper:
    """Gets Drive access tokens and runs Drive jobs with them."""

    def __init__(self, googleSignIn):
        self.googleSignIn = googleSignIn  # the nativeGoogleSignIn service
        self.accessToken = ""  # the latest token (memory only)
        self.fetchedAt = 0.0  # when this app first saw that token
        self.tokenChanges = 0  # how many different tokens this run has seen
        self.lastRetry = ""  # what the last refused-token retry did (shown on screen)
        self._jobLock = asyncio.Lock()

    async def getToken(self, accountEmail: str, interactive: bool = False) -> str:
        """Asks Google Play services for an access token: its cached one, or a fresh one once that has expired.
        interactive=True shows Google's permission screen if needed. Raises DriveAccessError."""
        answer = await self.googleSignIn.getDriveAccess(interactive, accountEmail)
        status = answer.get("status")
        token = answer.get("accessToken")
        if status == "ok" and token:
            if token != self.accessToken:
                self.accessToken = token
                self.fetchedAt = time.time()
                self.tokenChanges += 1
            return token
        if status == "ok":
            raise DriveAccessError("noToken", "Google returned no access token")
        if status == "needsConsent":
            raise DriveAccessError("needsConsent", "Google wants to ask you first: tap 'Allow Drive access'")
        if status == "cancelled":
            raise DriveAccessError("cancelled", "")
        raise DriveAccessError(str(answer.get("errorType") or status), str(answer.get("message") or ""))

    async def run(self, job, accountEmail: str):
        """Runs job(token) with a token from Google Play services, never showing a screen. If Drive refuses
        the token (401: expired or withdrawn), it's removed from Play services' cache and the job runs once
        more with a fresh one. Jobs must be safe to repeat after a refusal (a refused call changes nothing)."""
        async with self._jobLock:  # one Drive job at a time, so a retry can't clear another job's token
            token = await self.getToken(accountEmail)
            try:
                return await job(token)
            except DriveError as err:
                if err.statusCode != 401:
                    raise
            await self.googleSignIn.clearDriveToken(token)
            newToken = await self.getToken(accountEmail)
            self.lastRetry = (f"Drive refused token {tokenFingerprint(token)}, "
                              f"so it was retried with token {tokenFingerprint(newToken)}")
            return await job(newToken)
