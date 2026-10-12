"""All Supabase calls for the Phase 0 spike (sign-in and table rows): one small module, plain HTTPS,
no supabase-py (plan F9).

Rules for this module:
- HTTPS only, with certificate checks. On Android, Flet's build supplies the certificate list.
- Redirects are refused, so keys and tokens can never be forwarded to another address.
- Tokens only travel to Supabase and back to the caller: never printed, logged or put in error messages.
- Every request has a timeout, so a dead connection can't hang the app."""

import asyncio
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

requestTimeoutSec = 20


class SupabaseError(Exception):
    """A refused or failed Supabase call. Holds only Supabase's own error code and message, never request data."""

    def __init__(self, statusCode: int, errorCode: str, message: str):
        super().__init__(f"{statusCode} {errorCode}: {message}")
        self.statusCode = statusCode  # HTTP status; 0 = no answer (network problem)
        self.errorCode = errorCode
        self.message = message


def readSupabaseError(statusCode: int, rawBody: bytes) -> SupabaseError:
    """Turns an error answer into a SupabaseError. Supabase Auth uses two shapes:
    {"error_code": ..., "msg": ...} and the OAuth style {"error": ..., "error_description": ...}."""
    try:
        body = json.loads(rawBody or b"{}")
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    errorCode = str(body.get("error_code") or body.get("error") or body.get("code") or "unknown")
    message = str(body.get("msg") or body.get("error_description") or body.get("message") or "")[:300]
    return SupabaseError(statusCode, errorCode, message)


def makeNoncePair() -> tuple[str, str]:
    """Returns (rawNonce, hashedNonce): a one-time random value and its SHA-256 hex hash.
    Google gets the hash and puts it inside the ID token; Supabase gets the raw value, hashes it
    and checks they match. So a stolen ID token can't be replayed in another sign-in (plan F9)."""
    rawNonce = secrets.token_urlsafe(32)  # 256 random bits from the OS
    return rawNonce, hashlib.sha256(rawNonce.encode("ascii")).hexdigest()


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: urllib would otherwise resend our headers (key, token) to the new address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # no new request → urllib raises HTTPError for the 3xx answer instead


_opener = urllib.request.build_opener(_RefuseRedirects)


class SupabaseApi:
    """Talks to one Supabase project (Auth for sign-in, the Data API for table rows) with its URL and
    publishable key (both public by design, plan K2a). Signed-in calls add the user's access token;
    row-level security then limits every table call to that user's own rows."""

    def __init__(self, projectUrl: str, publishableKey: str):
        if not projectUrl.startswith("https://"):
            raise ValueError("The Supabase URL must start with https://")
        self.projectUrl = projectUrl.rstrip("/")
        self.publishableKey = publishableKey

    def _call(self, method: str, path: str, body: dict | None = None, accessToken: str | None = None,
              prefer: str | None = None):
        """Sends one request to projectUrl + path and returns the parsed JSON answer (None if empty).
        No accessToken = an anonymous call. Blocking: the app uses the async methods below,
        which run this in a worker thread."""
        headers = {"apikey": self.publishableKey, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if accessToken:
            headers["Authorization"] = f"Bearer {accessToken}"
        if prefer:
            headers["Prefer"] = prefer  # e.g. "return=representation": send back the rows that were written
        request = urllib.request.Request(self.projectUrl + path, data=data, headers=headers, method=method)
        try:
            with _opener.open(request, timeout=requestTimeoutSec) as response:
                rawAnswer = response.read()
        except urllib.error.HTTPError as err:
            # "from None" keeps the request (and its headers) out of the error's traceback.
            raise readSupabaseError(err.code, err.read()) from None
        except OSError as err:  # no connection, timeout, certificate problem (URLError, TimeoutError, SSLError)
            reason = getattr(err, "reason", err)
            raise SupabaseError(0, "network", f"{type(reason).__name__}: {reason}") from None
        return json.loads(rawAnswer) if rawAnswer else None

    async def signInWithGoogleIdToken(self, idToken: str, rawNonce: str) -> dict:
        """Swaps a Google ID token for a Supabase session (access_token, refresh_token, expires_at, user).
        Supabase checks the token's Google signature, that it was issued for our Web client ID,
        and that SHA-256(rawNonce) matches the nonce inside it."""
        return await asyncio.to_thread(
            self._call, "POST", "/auth/v1/token?grant_type=id_token",
            {"provider": "google", "id_token": idToken, "nonce": rawNonce},
        )

    async def getUser(self, accessToken: str) -> dict:
        """Asks Supabase who an access token belongs to (proves the session works)."""
        return await asyncio.to_thread(self._call, "GET", "/auth/v1/user", None, accessToken)

    async def signOut(self, accessToken: str) -> None:
        """Ends this session on Supabase's side: its refresh token stops working."""
        await asyncio.to_thread(self._call, "POST", "/auth/v1/logout?scope=local", None, accessToken)

    # --- Table rows (Supabase Data API). Filters use its syntax, e.g. {"id": "eq.<uuid>"}. ---

    @staticmethod
    def tablePath(table: str, filters: dict[str, str]) -> str:
        """Builds "/rest/v1/<table>?<filters>" with everything URL-encoded. camelCase table and
        column names work as they are: the Data API quotes them for Postgres (plan 11.4c)."""
        query = urllib.parse.urlencode(filters)
        return f"/rest/v1/{urllib.parse.quote(table, safe='')}" + (f"?{query}" if query else "")

    @staticmethod
    def _requireFilters(filters: dict[str, str]):
        """Refuses an update or delete without a filter, which would hit every row the user can see."""
        if not filters:
            raise ValueError("Updates and deletes need at least one filter")

    async def selectRows(self, table: str, filters: dict[str, str], accessToken: str | None) -> list[dict]:
        """Reads rows. Row-level security returns only the signed-in user's rows; no token = anonymous."""
        return await asyncio.to_thread(self._call, "GET", self.tablePath(table, filters), None, accessToken)

    async def insertRow(self, table: str, row: dict, accessToken: str | None) -> dict:
        """Saves one row and returns it as stored (with the columns the database filled in)."""
        rows = await asyncio.to_thread(
            self._call, "POST", self.tablePath(table, {}), row, accessToken, "return=representation"
        )
        return rows[0] if rows else {}

    async def updateRows(self, table: str, filters: dict[str, str], changes: dict, accessToken: str | None) -> list[dict]:
        """Changes the matching rows and returns them as stored. Rows hidden by row-level security
        are simply not matched, so the result can be an empty list."""
        self._requireFilters(filters)
        return await asyncio.to_thread(
            self._call, "PATCH", self.tablePath(table, filters), changes, accessToken, "return=representation"
        )

    async def deleteRows(self, table: str, filters: dict[str, str], accessToken: str | None) -> list[dict]:
        """Deletes the matching rows and returns what was deleted."""
        self._requireFilters(filters)
        return await asyncio.to_thread(
            self._call, "DELETE", self.tablePath(table, filters), None, accessToken, "return=representation"
        )
