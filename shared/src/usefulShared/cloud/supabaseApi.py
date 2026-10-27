"""All Supabase calls (sign-in and table rows): one small module, plain HTTPS, no supabase-py (F9).
Moved from the Phase 0 spike, where each call was proven on the phone and in the browser.

Rules for this module:
- HTTPS only, with certificate checks. On Android, Flet's build supplies the certificate list.
- Redirects are refused, so the key and tokens can never be forwarded to another address.
- Tokens only travel to Supabase and back to the caller: never in URLs, error messages or the log.
- Every request gives up after 15 seconds, so a weak connection can't stall sync (SY2.2).
- On the phone requests go through urllib in a worker thread, so the screen never waits (3b). In the
  browser (PC view: Pyodide, no sockets or threads) through the browser's own fetch, same rules.
- Only the public address and publishable key are used (K2a). Row-level security limits every table
  call to the signed-in user's own rows.
"""

import asyncio
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

requestTimeoutSec = 15  # SY2.2
runsInBrowser = sys.platform == "emscripten"  # Pyodide (the PC view website)

# A transport sends one request and returns (HTTP status, answer bytes), or raises CloudError with
# status 0 when no answer came. Swappable, so tests can stand in for the network.
Transport = Callable[[str, str, dict[str, str], bytes | None], Awaitable[tuple[int, bytes]]]


class CloudError(Exception):
    """A refused or failed cloud call. Holds only Supabase's own error code and a short message."""

    def __init__(self, statusCode: int, errorCode: str, message: str):
        super().__init__(f"{statusCode} {errorCode}: {message}")
        self.statusCode = statusCode  # HTTP status. 0 = no answer (network problem)
        self.errorCode = errorCode
        self.message = message

    @property
    def isTemporary(self) -> bool:
        """No answer, a server problem or too many requests: the same call may work later."""
        return self.statusCode == 0 or self.statusCode == 429 or self.statusCode >= 500

    @property
    def isSessionProblem(self) -> bool:
        """The access token was refused (expired or ended): renew the session, then try again."""
        return self.statusCode == 401


def readCloudError(statusCode: int, rawBody: bytes) -> CloudError:
    """Turns an error answer into a CloudError. Supabase Auth answers {"error_code", "msg"} or the
    OAuth style {"error", "error_description"}. The Data API answers {"code", "message"}."""
    try:
        body = json.loads(rawBody or b"{}")
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    errorCode = str(body.get("error_code") or body.get("error") or body.get("code") or "unknown")[:100]
    message = str(body.get("msg") or body.get("error_description") or body.get("message") or "")[:300]
    return CloudError(statusCode, errorCode, message)


def makeNoncePair() -> tuple[str, str]:
    """Returns (rawNonce, hashedNonce): a one-time random value and its SHA-256 hex hash. Google gets
    the hash and puts it inside the ID token. Supabase gets the raw value, hashes it and checks they
    match, so a stolen ID token can't be replayed in another sign-in (F9)."""
    rawNonce = secrets.token_urlsafe(32)  # 256 random bits from the OS
    return rawNonce, hashlib.sha256(rawNonce.encode("ascii")).hexdigest()


# --- Transports ---------------------------------------------------------------------------------

class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: urllib would otherwise resend our headers (key, token) to the new address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # no new request: urllib raises HTTPError for the 3xx answer instead


_opener = urllib.request.build_opener(_RefuseRedirects)


def _urllibCall(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """Sends one request with urllib (blocking, runs in a worker thread)."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _opener.open(request, timeout=requestTimeoutSec) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        # An answer, just not a happy one (or a refused redirect). The caller reads it.
        try:
            return err.code, err.read()
        except OSError:
            return err.code, b""
    except OSError as err:  # no connection, timeout, certificate problem (URLError, TimeoutError, SSLError)
        reason = getattr(err, "reason", err)
        # "from None" keeps the request (and its headers) out of the error's traceback.
        raise CloudError(0, "network", f"{type(reason).__name__}: {reason}"[:300]) from None


async def urllibTransport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """The phone's transport: urllib in a worker thread, so the app's loop never waits on the network.
    urllib's timeout covers each wait for data. The overall limit here covers a slow trickle too."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_urllibCall, method, url, headers, body),
                                      requestTimeoutSec + 1)
    except TimeoutError:
        raise CloudError(0, "network", f"no answer within {requestTimeoutSec} s") from None


async def fetchTransport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """The browser's transport (PC view). The browser checks certificates itself. Redirects are refused
    ("error"), cookies are never sent and nothing is cached, matching the phone's rules."""
    from pyodide.http import pyfetch  # only exists in the browser build

    options: dict[str, Any] = {"method": method, "headers": headers, "redirect": "error", "credentials": "omit",
                               "cache": "no-store"}
    if body is not None:
        options["body"] = body.decode("utf-8")
    try:
        response = await asyncio.wait_for(pyfetch(url, **options), requestTimeoutSec)
        rawAnswer = await asyncio.wait_for(response.bytes(), requestTimeoutSec)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        raise CloudError(0, "network", f"no answer within {requestTimeoutSec} s") from None
    except Exception as err:  # the browser says "failed to fetch" for offline, blocked or redirected requests
        raise CloudError(0, "network", f"{type(err).__name__}: {err}"[:300]) from None
    return response.status, rawAnswer


# --- The API ------------------------------------------------------------------------------------

class SupabaseApi:
    """One Supabase project: Auth for sign-in, the Data API for table rows. Signed-in calls add the
    user's access token. Anonymous calls carry only the publishable key."""

    def __init__(self, projectUrl: str, publishableKey: str, transport: Transport | None = None):
        if not projectUrl.startswith("https://"):
            raise ValueError("The Supabase URL must start with https://")
        self.projectUrl = projectUrl.rstrip("/")
        self.publishableKey = publishableKey
        self.transport = transport or (fetchTransport if runsInBrowser else urllibTransport)

    async def _send(self, method: str, path: str, body: Any = None, accessToken: str | None = None,
                    prefer: str | None = None) -> Any:
        """Sends one request to projectUrl + path. Returns the parsed JSON answer (None if empty)."""
        headers = {"apikey": self.publishableKey, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if accessToken:
            headers["Authorization"] = f"Bearer {accessToken}"
        if prefer:
            headers["Prefer"] = prefer
        status, rawAnswer = await self.transport(method, self.projectUrl + path, headers, data)
        if not 200 <= status < 300:
            raise readCloudError(status, rawAnswer)
        try:
            return json.loads(rawAnswer) if rawAnswer else None
        except ValueError:
            raise CloudError(status, "badAnswer", "the answer isn't JSON") from None

    # --- Sign-in (Supabase Auth) ---

    async def signInWithGoogleIdToken(self, idToken: str, rawNonce: str) -> dict:
        """Swaps a Google ID token for a Supabase session (access_token, refresh_token, expires_at, user).
        Supabase checks the token's Google signature, that it was issued for our Web client ID, and that
        SHA-256(rawNonce) matches the nonce inside it."""
        return await self._send("POST", "/auth/v1/token?grant_type=id_token",
                                {"provider": "google", "id_token": idToken, "nonce": rawNonce})

    async def refreshSession(self, refreshToken: str) -> dict:
        """Swaps the refresh token for a new session. Supabase retires the old refresh token right away
        (rotation), so the caller must store the new one before doing anything else."""
        return await self._send("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": refreshToken})

    async def signOut(self, accessToken: str) -> None:
        """Ends this session on Supabase's side: its refresh token stops working."""
        await self._send("POST", "/auth/v1/logout?scope=local", None, accessToken)

    # --- Table rows (Supabase Data API) ---

    @staticmethod
    def tablePath(table: str, query: dict[str, str]) -> str:
        """Builds "/rest/v1/<table>?<query>" with everything URL-encoded. camelCase table and column names
        work as they are: the Data API quotes them for Postgres (11.4c)."""
        encoded = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)  # spaces as %20, "+" as %2B
        return f"/rest/v1/{urllib.parse.quote(table, safe='')}" + (f"?{encoded}" if encoded else "")

    async def readCloudInfo(self, accessToken: str) -> tuple[int, int]:
        """The cloud's (schemaVersion, minAppSchema), for the version check before each sync (UP1.1)."""
        rows = await self._send("GET", self.tablePath("cloudInfo", {"select": "schemaVersion,minAppSchema"}),
                                accessToken=accessToken)
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise CloudError(200, "noCloudInfo", "cloudInfo doesn't hold one row (has upgrade 001 been run?)")
        schemaVersion, minAppSchema = rows[0].get("schemaVersion"), rows[0].get("minAppSchema")
        if not isinstance(schemaVersion, int) or not isinstance(minAppSchema, int):
            raise CloudError(200, "noCloudInfo", "cloudInfo's numbers can't be read")
        return schemaVersion, minAppSchema

    async def upsertRows(self, table: str, rows: Sequence[dict], accessToken: str) -> None:
        """Adds or replaces rows by id in one request (all of them or none). The cloud's trigger keeps
        whichever edit is newer, so sending the same change twice is harmless (14b)."""
        await self._send("POST", self.tablePath(table, {"on_conflict": "id"}), list(rows), accessToken,
                         "resolution=merge-duplicates,return=minimal")

    async def fetchRows(self, table: str, columns: Sequence[str], since: str, after: tuple[str, str] | None,
                        limit: int, accessToken: str) -> list[dict]:
        """One page of rows the cloud stored at or after `since`, oldest first, ordered by (cloudUpdatedAt,
        id). `after` is the last (cloudUpdatedAt, id) of the previous page, so pages never skip or repeat
        rows, even rows stored in the same microsecond (14b). Times are the cloud's own text."""
        query = {
            "select": ",".join(columns),
            "cloudUpdatedAt": f"gte.{since}",
            "order": "cloudUpdatedAt.asc,id.asc",
            "limit": str(limit),
        }
        if after is not None:
            lastStamp, lastId = after
            # Values with ":" or "." must be in double quotes inside the Data API's or=(...) syntax.
            query["or"] = f'(cloudUpdatedAt.gt."{lastStamp}",and(cloudUpdatedAt.eq."{lastStamp}",id.gt.{lastId}))'
        rows = await self._send("GET", self.tablePath(table, query), accessToken=accessToken)
        if not isinstance(rows, list):
            raise CloudError(200, "badAnswer", f"{table}: the answer isn't a list of rows")
        return rows
