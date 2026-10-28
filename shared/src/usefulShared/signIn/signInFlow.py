"""Signing in with Google (AU1c, 6.1), the same on the phone and in the PC view: Google hands over an ID
token carrying a hashed one-time nonce, and Supabase checks it. First the same token with a wrong nonce
must be refused, so sign-in never works if replay protection were ever switched off in Supabase (F9).
Nothing here logs or shows a token."""

from dataclasses import dataclass
from typing import Any

from usefulShared.cloud.supabaseApi import CloudError, makeNoncePair
from usefulShared.platform.appLog import AppLog


@dataclass(frozen=True, slots=True)
class SignInResult:
    session: dict | None  # Supabase's session, or None
    notice: str = ""  # what to tell you when it didn't work ("" when cancelled or fine)


async def signInWithGoogle(googleSignIn: Any, cloud: Any, clientId: str, log: AppLog) -> SignInResult:
    """Google's sign-in (the phone's account picker, or Google's button in the browser) → Supabase session."""
    rawNonce, hashedNonce = makeNoncePair()
    answer = await googleSignIn.getIdToken(clientId, hashedNonce)
    status = answer.get("status")
    if status == "cancelled":
        return SignInResult(None)
    if status != "ok":
        log.problem("signIn", "Google sign-in didn't work.", f"{answer.get('errorType', status)}: {answer.get('message', '')}")
        return SignInResult(None, "Google sign-in didn't work. Details are on the Problems page.")
    idToken = answer["idToken"]
    try:
        if not await _wrongNonceIsRefused(cloud, idToken, log):
            return SignInResult(None, "Sign-in was stopped for safety. Details are on the Problems page.")
        session = await cloud.signInWithGoogleIdToken(idToken, rawNonce)
    except CloudError as problem:
        log.problem("signIn", "Signing in didn't work.", f"{problem.statusCode} {problem.errorCode}: {problem.message}")
        if problem.isTemporary:
            return SignInResult(None, "No internet: signing in needs it.")
        if problem.errorCode == "signup_disabled":
            return SignInResult(None, "This Google account isn't allowed in this app.")
        return SignInResult(None, "Signing in didn't work. Details are on the Problems page.")
    log.info("signIn", "signed in")
    return SignInResult(session)


async def _wrongNonceIsRefused(cloud: Any, idToken: str, log: AppLog) -> bool:
    """The replay check: Supabase must refuse this ID token with a nonce it wasn't made for."""
    wrongNonce, _ = makeNoncePair()
    try:
        accidental = await cloud.signInWithGoogleIdToken(idToken, wrongNonce)
    except CloudError as problem:
        if problem.isTemporary:
            raise  # a network problem proves nothing about the nonce check
        return True
    try:  # end the session this check should never have produced
        await cloud.signOut(accidental["access_token"])
    except (CloudError, KeyError, TypeError):
        pass
    log.problem("signIn", "Sign-in was stopped for safety: the cloud accepted a wrong nonce.",
                "check Supabase: Authentication > Providers > Google > Skip nonce checks must be off")
    return False
