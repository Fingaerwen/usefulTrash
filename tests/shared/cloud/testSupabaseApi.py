"""Tests for the Supabase calls (usefulShared.cloud.supabaseApi): what each request looks like, how
errors are read, and the phone's transport against a small local web server (redirects refused,
time limit kept). No real Supabase is reached."""

import asyncio
import http.server
import json
import threading
import time
import urllib.parse

import pytest

from usefulShared.cloud import supabaseApi
from usefulShared.cloud.supabaseApi import CloudError, SupabaseApi, makeNoncePair, readCloudError, urllibTransport

projectUrl = "https://example.supabase.co"
fakeKey = "testPublishableKey"  # made-up, and deliberately not key-shaped: no real key is ever in tests
fakeToken = "header.payload.signature"


class RecordingTransport:
    """Stands in for the network: records each request and gives the next canned answer."""

    def __init__(self, *answers: tuple[int, bytes]):
        self.answers = list(answers)
        self.requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

    async def __call__(self, method, url, headers, body):
        self.requests.append((method, url, headers, body))
        return self.answers.pop(0)


def api(*answers: tuple[int, bytes]) -> tuple[SupabaseApi, RecordingTransport]:
    transport = RecordingTransport(*answers)
    return SupabaseApi(projectUrl, fakeKey, transport), transport


def query(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query, strict_parsing=True))


# --- Requests -----------------------------------------------------------------------------------

def testOnlyHttps():
    with pytest.raises(ValueError):
        SupabaseApi("http://example.supabase.co", fakeKey)


def testRequestsCarryTheKeyAndTheToken():
    cloud, transport = api((200, b"[]"))
    asyncio.run(cloud.upsertRows("bodyWeight", [{"id": "x"}], fakeToken))
    method, url, headers, body = transport.requests[0]
    assert headers["apikey"] == fakeKey
    assert headers["Authorization"] == f"Bearer {fakeToken}"
    assert fakeToken not in url  # tokens never travel in addresses


def testUpsertKeepsTheNewestThroughTheCloud():
    """One request for the batch. The cloud's trigger decides which edit wins (14b)."""
    cloud, transport = api((201, b""))
    rows = [{"id": "a", "weightKg": 81.2}, {"id": "b", "weightKg": 80.9}]
    asyncio.run(cloud.upsertRows("bodyWeight", rows, fakeToken))
    method, url, headers, body = transport.requests[0]
    assert (method, url) == ("POST", f"{projectUrl}/rest/v1/bodyWeight?on_conflict=id")
    assert headers["Prefer"] == "resolution=merge-duplicates,return=minimal"
    assert json.loads(body) == rows


def testFetchAsksForChangesInOrder():
    cloud, transport = api((200, b"[]"))
    asyncio.run(cloud.fetchRows("bodyWeight", ["id", "weightKg"], "2026-10-12T07:00:00.000000+00:00", None, 500,
                                fakeToken))
    method, url, headers, body = transport.requests[0]
    assert (method, body) == ("GET", None)
    assert "%2B00%3A00" in url  # "+" must be encoded, or the server reads it as a space
    assert query(url) == {"select": "id,weightKg", "cloudUpdatedAt": "gte.2026-10-12T07:00:00.000000+00:00",
                          "order": "cloudUpdatedAt.asc,id.asc", "limit": "500"}


def testNextPageStartsRightAfterTheLastRow():
    cloud, transport = api((200, b"[]"))
    last = ("2026-10-12T07:00:01.5+00:00", "4b3cd21b-3fff-50d8-accf-b254a88d07fb")
    asyncio.run(cloud.fetchRows("sessions", ["id"], "2026-10-12T07:00:00+00:00", last, 500, fakeToken))
    assert query(transport.requests[0][1])["or"] == (
        '(cloudUpdatedAt.gt."2026-10-12T07:00:01.5+00:00",'
        'and(cloudUpdatedAt.eq."2026-10-12T07:00:01.5+00:00",id.gt.4b3cd21b-3fff-50d8-accf-b254a88d07fb))')


def testCloudInfo():
    cloud, _ = api((200, b'[{"schemaVersion": 3, "minAppSchema": 2}]'))
    assert asyncio.run(cloud.readCloudInfo(fakeToken)) == (3, 2)
    for answer in (b"[]", b'[{"schemaVersion": "3", "minAppSchema": 2}]'):
        cloud, _ = api((200, answer))
        with pytest.raises(CloudError, match="noCloudInfo"):
            asyncio.run(cloud.readCloudInfo(fakeToken))


def testSignInSendsTheRawNonce():
    rawNonce, hashedNonce = makeNoncePair()
    assert len(hashedNonce) == 64 and rawNonce != hashedNonce
    cloud, transport = api((200, b'{"access_token": "a"}'))
    asyncio.run(cloud.signInWithGoogleIdToken("googleIdToken", rawNonce))
    method, url, headers, body = transport.requests[0]
    assert url == f"{projectUrl}/auth/v1/token?grant_type=id_token"
    assert json.loads(body) == {"provider": "google", "id_token": "googleIdToken", "nonce": rawNonce}
    assert "Authorization" not in headers


# --- Errors -------------------------------------------------------------------------------------

def testDataApiErrorsKeepOnlyCodeAndMessage():
    body = json.dumps({"code": "P0001", "details": None, "hint": None,
                       "message": "futureEdit: this change is stamped " + "x" * 400}).encode()
    cloud, _ = api((400, body))
    with pytest.raises(CloudError) as problem:
        asyncio.run(cloud.upsertRows("bodyWeight", [{"id": "a"}], fakeToken))
    assert (problem.value.statusCode, problem.value.errorCode) == (400, "P0001")
    assert problem.value.message.startswith("futureEdit:") and len(problem.value.message) == 300
    assert not problem.value.isTemporary and not problem.value.isSessionProblem


def testAuthErrorsAreRead():
    assert readCloudError(400, b'{"error_code": "refresh_token_already_used", "msg": "Invalid"}').errorCode == (
        "refresh_token_already_used")
    assert readCloudError(400, b'{"error": "invalid_grant", "error_description": "bad"}').message == "bad"
    assert readCloudError(502, b"<html>Bad gateway</html>").errorCode == "unknown"


def testWhichErrorsAreWorthRetrying():
    assert CloudError(0, "network", "").isTemporary
    assert CloudError(503, "unknown", "").isTemporary
    assert CloudError(429, "over_request_rate_limit", "").isTemporary
    assert not CloudError(403, "42501", "").isTemporary
    assert CloudError(401, "PGRST301", "JWT expired").isSessionProblem


def testRedirectAnswerIsAnError():
    """The transport refuses to follow a redirect, and the API treats the 3xx answer as a failure."""
    cloud, _ = api((302, b""))
    with pytest.raises(CloudError) as problem:
        asyncio.run(cloud.readCloudInfo(fakeToken))
    assert problem.value.statusCode == 302


def testAnswerThatIsNotJson():
    cloud, _ = api((200, b"<html>captive portal</html>"))
    with pytest.raises(CloudError, match="badAnswer"):
        asyncio.run(cloud.readCloudInfo(fakeToken))


# --- The phone's transport, against a local web server ----------------------------------------

class LocalHandler(http.server.BaseHTTPRequestHandler):
    """Answers by path: /ok with JSON, /redirect with a 302 elsewhere, /slow after a pause, /trickle a
    byte at a time, /fail with 400. Counts requests, so a followed redirect would show."""

    hits: list[str] = []

    def do_GET(self):
        LocalHandler.hits.append(self.path)
        if self.path == "/ok":
            self._answer(200, b'{"fine": true}')
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(2)
            self._answer(200, b"{}")
        elif self.path == "/trickle":
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            for _ in range(10):  # each byte comes quickly, so only an overall time limit stops this
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.25)
        else:
            self._answer(400, b'{"code": "bad"}')

    def _answer(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep test output quiet


@pytest.fixture
def localServer():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    LocalHandler.hits = []
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def testTransportReturnsAnswers(localServer):
    assert asyncio.run(urllibTransport("GET", f"{localServer}/ok", {}, None)) == (200, b'{"fine": true}')
    assert asyncio.run(urllibTransport("GET", f"{localServer}/fail", {}, None)) == (400, b'{"code": "bad"}')


def testTransportRefusesRedirects(localServer):
    """Following a redirect would resend the key and token to wherever it points."""
    status, _ = asyncio.run(urllibTransport("GET", f"{localServer}/redirect", {"apikey": fakeKey}, None))
    assert status == 302
    assert LocalHandler.hits == ["/redirect"]


def testTransportGivesUp(localServer, monkeypatch):
    monkeypatch.setattr(supabaseApi, "requestTimeoutSec", 0.5)
    started = time.monotonic()
    with pytest.raises(CloudError) as problem:
        asyncio.run(urllibTransport("GET", f"{localServer}/slow", {}, None))
    assert problem.value.statusCode == 0 and problem.value.isTemporary
    assert time.monotonic() - started < 1.8


def testTransportGivesUpOnASlowTrickle(localServer, monkeypatch):
    """Timed inside the loop: the app carries on at once, while the abandoned worker thread finishes on its own."""
    monkeypatch.setattr(supabaseApi, "requestTimeoutSec", 0.5)

    async def timedRequest() -> tuple[CloudError, float]:
        started = time.monotonic()
        try:
            await urllibTransport("GET", f"{localServer}/trickle", {}, None)
        except CloudError as problem:
            return problem, time.monotonic() - started
        raise AssertionError("the trickle was waited out")

    problem, waited = asyncio.run(timedRequest())
    assert problem.statusCode == 0
    assert waited < 1.9


def testTransportWithoutAConnection(localServer):
    closedPort = localServer.rsplit(":", 1)[0] + ":9"  # nothing listens on port 9 (discard)
    with pytest.raises(CloudError) as problem:
        asyncio.run(urllibTransport("GET", f"{closedPort}/ok", {}, None))
    assert problem.value.statusCode == 0
