"""Python side of the nativeGoogleSignIn extension.

Each method sends a named request to the Dart side (src/flutter/native_google_sign_in),
which forwards it to the Kotlin plugin running on Android. The Google ID token and Drive access
tokens come back as return values only: this module never prints, logs or saves them."""

import flet as ft

__all__ = ["NativeGoogleSignIn"]

# Longest wait for Google's account picker. Generous, because adding an account on the phone takes a while.
# Every Android path replies (plan F9). This only guards against a reply that never arrives.
signInTimeoutSec = 300

# Longest wait for a Drive token when no screen is shown (Google Play services answers in seconds).
silentTimeoutSec = 60


@ft.control("NativeGoogleSignIn")
class NativeGoogleSignIn(ft.Service):
    """Native Google sign-in on Android. Create one (services register themselves with the page), then call its methods."""

    async def getIdToken(self, serverClientId: str, hashedNonce: str) -> dict:
        """Shows Google's account picker and returns one of:
        {"status": "ok", "idToken": ...}, {"status": "cancelled"}, {"status": "noAccount", "message": ...}
        or {"status": "error", "errorType": ..., "message": ...}.

        serverClientId: the *Web* client ID from Google Cloud (Google issues the token for it).
        hashedNonce: SHA-256 hex of a one-time random value. Google puts it inside the token.
        Supabase gets the raw value and checks they match, so a stolen token can't be replayed."""
        return await self._invoke_method(
            method_name="getIdToken",
            arguments={"serverClientId": serverClientId, "hashedNonce": hashedNonce},
            timeout=signInTimeoutSec,
        )

    async def clearSignInState(self) -> dict:
        """Forgets the chosen Google account, so the next sign-in shows the account picker again.
        Returns {"status": "ok"} or {"status": "error", "errorType": ..., "message": ...}."""
        return await self._invoke_method(method_name="clearSignInState", timeout=30)

    async def getDriveAccess(self, interactive: bool, accountEmail: str = "") -> dict:
        """Gets a Drive access token from Google Play services (check 7), limited to files this app creates.
        Returns {"status": "ok", "accessToken": ..., "grantedScopes": [...]}, {"status": "needsConsent"}
        (only when interactive is False), {"status": "cancelled"} or {"status": "error", "errorType": ..., "message": ...}.

        interactive: True shows Google's consent screen if needed. False never shows anything.
        accountEmail: the Google account to use (the signed-in one). Empty lets Google ask.
        The token lasts about an hour. Don't save it: calling this again returns a fresh one."""
        return await self._invoke_method(
            method_name="getDriveAccess",
            arguments={"interactive": interactive, "accountEmail": accountEmail},
            timeout=signInTimeoutSec if interactive else silentTimeoutSec,
        )

    async def clearDriveToken(self, accessToken: str) -> dict:
        """Removes a Drive access token Google refused from Play services' cache, so the next
        getDriveAccess returns a new one. Returns {"status": "ok"} or an error answer like getDriveAccess."""
        return await self._invoke_method(
            method_name="clearDriveToken", arguments={"accessToken": accessToken}, timeout=30
        )
