"""Tests for the session keeper (usefulShared.signIn.sessionKeeper): renewing in time, saving before
use, one renewal at a time, staying signed in while offline, and signing out only when Supabase says
the sign-in is over. All tokens here are made up."""

import asyncio
import json

import pytest

from usefulShared.cloud.supabaseApi import CloudError
from usefulShared.signIn.sessionKeeper import MemoryStore, SessionKeeper, isDeadSession

now = 1_800_000_000.0  # a fixed "now" in seconds since 1970


def session(number: int, expiresIn: float = 3600) -> dict:
    """A made-up Supabase session; the number tells the versions apart."""
    return {"access_token": f"access{number}", "refresh_token": f"refresh{number}", "expires_at": now + expiresIn,
            "token_type": "bearer", "user": {"id": "user-id", "email": "testAccount", "role": "authenticated"}}


class FakeAuth:
    """Supabase Auth's renewal: each call retires the refresh token it got and hands out the next session."""

    def __init__(self, store: MemoryStore):
        self.store = store
        self.renewals = 0
        self.problem: CloudError | None = None
        self.savedWhenAsked: list[str] = []  # what was saved at the moment each renewal began

    async def refreshSession(self, refreshToken: str) -> dict:
        self.savedWhenAsked.append(json.loads((await self.store.load("supabaseSession"))["value"])["refresh_token"])
        await asyncio.sleep(0.01)  # a moment on the network, so overlapping calls would show
        if self.problem is not None:
            raise self.problem
        self.renewals += 1
        return session(int(refreshToken.removeprefix("refresh")) + 1)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def auth(store) -> FakeAuth:
    return FakeAuth(store)


def keeper(store, auth, current: dict | None) -> SessionKeeper:
    sessionKeeper = SessionKeeper(auth, store, clock=lambda: now)
    if current is not None:
        asyncio.run(sessionKeeper.save(current))
    return sessionKeeper


def testOnlyWhatsNeededIsKept(store, auth):
    sessionKeeper = keeper(store, auth, session(1))
    saved = json.loads(asyncio.run(store.load("supabaseSession"))["value"])
    assert saved == {"access_token": "access1", "refresh_token": "refresh1", "expires_at": now + 3600,
                     "user": {"id": "user-id", "email": "testAccount"}}
    assert (sessionKeeper.userId(), sessionKeeper.isSignedIn()) == ("user-id", True)


def testAFreshTokenIsUsedAsItIs(store, auth):
    assert asyncio.run(keeper(store, auth, session(1)).freshAccessToken()) == "access1"
    assert auth.renewals == 0


def testRenewsWhenLessThanFiveMinutesAreLeftAndSavesFirst(store, auth):
    sessionKeeper = keeper(store, auth, session(1, expiresIn=200))
    assert asyncio.run(sessionKeeper.freshAccessToken()) == "access2"
    assert json.loads(asyncio.run(store.load("supabaseSession"))["value"])["refresh_token"] == "refresh2"


def testRenewalsNeverRunAtTheSameTime(store, auth):
    """Sync and a screen both ask for a token as it runs out: one renewal, both get the new token.
    Two renewals would use the same refresh token twice, which ends the whole sign-in."""
    sessionKeeper = keeper(store, auth, session(1, expiresIn=10))

    async def bothAtOnce():
        return await asyncio.gather(sessionKeeper.freshAccessToken(), sessionKeeper.freshAccessToken())

    assert asyncio.run(bothAtOnce()) == ["access2", "access2"]
    assert auth.renewals == 1


def testEachRenewalStartsFromTheSavedNewestSession(store, auth):
    sessionKeeper = keeper(store, auth, session(1))
    asyncio.run(sessionKeeper.renewNow())
    asyncio.run(sessionKeeper.renewNow())
    assert auth.savedWhenAsked == ["refresh1", "refresh2"]
    assert sessionKeeper.session["refresh_token"] == "refresh3"


def testBeingOfflineNeverSignsYouOut(store, auth):
    sessionKeeper = keeper(store, auth, session(1, expiresIn=10))
    auth.problem = CloudError(0, "network", "OSError: no connection")
    with pytest.raises(CloudError):
        asyncio.run(sessionKeeper.freshAccessToken())
    assert sessionKeeper.isSignedIn()
    assert asyncio.run(store.load("supabaseSession"))["status"] == "ok"


@pytest.mark.parametrize("problem", [
    CloudError(400, "refresh_token_already_used", "Invalid Refresh Token: Already Used"),
    CloudError(400, "validation_failed", "Refresh token is not valid"),
])
def testADeadSignInIsForgotten(store, auth, problem):
    sessionKeeper = keeper(store, auth, session(1, expiresIn=10))
    auth.problem = problem
    with pytest.raises(CloudError):
        asyncio.run(sessionKeeper.freshAccessToken())
    assert not sessionKeeper.isSignedIn()
    assert asyncio.run(store.load("supabaseSession")) == {"status": "missing"}


def testWhichProblemsMeanTheSignInIsOver():
    assert isDeadSession(CloudError(400, "session_not_found", ""))
    assert not isDeadSession(CloudError(0, "network", ""))
    assert not isDeadSession(CloudError(429, "over_request_rate_limit", ""))
    assert not isDeadSession(CloudError(500, "unexpected_failure", "refresh token store down"))


def testNotSignedIn(store, auth):
    with pytest.raises(CloudError) as problem:
        asyncio.run(keeper(store, auth, None).freshAccessToken())
    assert problem.value.errorCode == "notSignedIn"


def testRestoringASavedSession(store, auth):
    keeper(store, auth, session(1))
    restored = SessionKeeper(auth, store, clock=lambda: now)
    assert asyncio.run(restored.restore()) == "restored"
    assert restored.session["access_token"] == "access1"


def testRestoreWhenThereIsNothingOrItCantBeRead(store, auth):
    assert asyncio.run(keeper(store, auth, None).restore()) == "none"
    asyncio.run(store.save("supabaseSession", "not json"))
    sessionKeeper = keeper(store, auth, None)
    assert asyncio.run(sessionKeeper.restore()) == "unreadable"
    assert asyncio.run(store.load("supabaseSession")) == {"status": "missing"}  # deleted: sign in again


def testAFailedSaveIsReported(auth):
    class BrokenStore(MemoryStore):
        async def save(self, name, value):
            return {"status": "error", "errorType": "KeyStoreException", "message": "key unavailable"}

    sessionKeeper = SessionKeeper(auth, BrokenStore(), clock=lambda: now)
    assert asyncio.run(sessionKeeper.save(session(1))) is False
    assert sessionKeeper.isSignedIn()  # still usable until the app closes
    assert "KeyStoreException" in sessionKeeper.lastProblem and "access1" not in sessionKeeper.lastProblem
