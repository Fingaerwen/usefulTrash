"""Python side of the nativeGoogleSignIn extension.

Each method sends a named request to the Dart side (src/flutter/native_google_sign_in),
which forwards it to the Kotlin plugin running on Android. The Google ID token comes back
as a return value only: this module never prints, logs or saves it."""

import flet as ft

__all__ = ["NativeGoogleSignIn"]

# Longest wait for Google's account picker. Generous, because adding an account on the phone takes a while.
# Every Android path replies (plan F9); this only guards against a reply that never arrives.
signInTimeoutSec = 300


@ft.control("NativeGoogleSignIn")
class NativeGoogleSignIn(ft.Service):
    """Native Google sign-in on Android. Create one (services register themselves with the page), then call its methods."""

    async def getIdToken(self, serverClientId: str, hashedNonce: str) -> dict:
        """Shows Google's account picker and returns one of:
        {"status": "ok", "idToken": ...}, {"status": "cancelled"}, {"status": "noAccount", "message": ...}
        or {"status": "error", "errorType": ..., "message": ...}.

        serverClientId: the *Web* client ID from Google Cloud (Google issues the token for it).
        hashedNonce: SHA-256 hex of a one-time random value. Google puts it inside the token;
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
