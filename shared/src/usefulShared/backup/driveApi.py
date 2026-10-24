"""Google Drive calls (F14.1; proven in Phase 0 check 7): plain HTTPS to Drive's REST API (v3) with a
short-lived access token, limited to files this app created (drive.file).

Rules (as supabaseApi):
- HTTPS to www.googleapis.com only. Redirects are refused, so the token can never go anywhere else.
- The token only travels in the Authorization header (never in a URL), and is never logged, printed or
  put in an error message.
- Every request has a timeout.
The phone gets its tokens from Google Play services (nativeGoogleSignIn.getDriveAccess); the PC view from
Google's sign-in page in a second window (BK1.1).
"""

import asyncio
import json
import secrets
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any

from usefulShared.cloud.supabaseApi import CloudError, requestTimeoutSec, urllibTransport

googleApisUrl = "https://www.googleapis.com/"
driveApiUrl = googleApisUrl + "drive/v3"
driveUploadUrl = googleApisUrl + "upload/drive/v3"
folderMimeType = "application/vnd.google-apps.folder"
maxOneRequestUploadBytes = 5 * 1024 * 1024  # Google's limit for an upload sent in one request (multipart)

Transport = Callable[[str, str, dict[str, str], bytes | None], Awaitable[tuple[int, bytes]]]


class DriveError(Exception):
    """A refused or failed Drive call. Holds only Google's own error details, never request data."""

    def __init__(self, statusCode: int, reason: str, message: str):
        super().__init__(f"{statusCode} {reason}: {message}")
        self.statusCode = statusCode  # HTTP status; 0 = no answer
        self.reason = reason  # e.g. "authError" (token refused), "accessNotConfigured"
        self.message = message


def readDriveError(statusCode: int, rawBody: bytes) -> DriveError:
    """Google APIs answer {"error": {"code", "message", "status", "errors": [{"reason"}]}}."""
    try:
        body = json.loads(rawBody or b"{}")
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, str):  # the OAuth style
        return DriveError(statusCode, error, str(body.get("error_description") or "")[:300])
    error = error if isinstance(error, dict) else {}
    details = error.get("errors")
    first = details[0] if isinstance(details, list) and details and isinstance(details[0], dict) else {}
    return DriveError(statusCode, str(first.get("reason") or error.get("status") or "unknown"),
                      str(error.get("message") or "")[:300])


def quoteDriveText(text: str) -> str:
    """Single quotes for a Drive search query, with backslashes and quotes escaped."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def multipartBody(metadata: dict, content: bytes, mimeType: str) -> tuple[bytes, str]:
    """A one-request upload's body: the file's details (JSON) and its content, as multipart/related, with a
    random boundary found in neither part. Returns (body, Content-Type)."""
    metadataBytes = json.dumps(metadata).encode("utf-8")
    while True:
        boundary = f"usefulTrash-{secrets.token_hex(16)}"
        if boundary.encode("ascii") not in metadataBytes and boundary.encode("ascii") not in content:
            break
    body = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("ascii"), metadataBytes,
        f"\r\n--{boundary}\r\nContent-Type: {mimeType}\r\n\r\n".encode("ascii"), content,
        f"\r\n--{boundary}--\r\n".encode("ascii")])
    return body, f"multipart/related; boundary={boundary}"


async def browserTransport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """The PC view's transport for Drive: like supabaseApi's fetchTransport, but the body goes as bytes,
    since an upload is a zip."""
    from pyodide.ffi import to_js  # only exists in the browser build
    from pyodide.http import pyfetch

    options: dict[str, Any] = {"method": method, "headers": headers, "redirect": "error", "credentials": "omit",
                               "cache": "no-store"}
    if body is not None:
        options["body"] = to_js(body)
    try:
        response = await asyncio.wait_for(pyfetch(url, **options), requestTimeoutSec)
        return response.status, await asyncio.wait_for(response.bytes(), requestTimeoutSec)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        raise DriveError(0, "network", f"{type(err).__name__}: {err}"[:300]) from None


class DriveApi:
    """Drive calls; the access token is passed in every time (it lasts about an hour)."""

    def __init__(self, transport: Transport | None = None):
        self.transport = transport or urllibTransport

    async def _send(self, method: str, url: str, accessToken: str, body: bytes | None = None,
                    contentType: str | None = None) -> Any:
        rawAnswer = await self._sendRaw(method, url, accessToken, body, contentType)
        return json.loads(rawAnswer) if rawAnswer else None

    async def _sendRaw(self, method: str, url: str, accessToken: str, body: bytes | None = None,
                       contentType: str | None = None) -> bytes:
        if not url.startswith(googleApisUrl):
            raise ValueError(f"Drive calls only go to {googleApisUrl}")
        headers = {"Authorization": f"Bearer {accessToken}", "Accept": "application/json"}
        if contentType:
            headers["Content-Type"] = contentType
        try:
            status, rawAnswer = await self.transport(method, url, headers, body)
        except CloudError as err:  # supabaseApi's transport says "network" this way
            raise DriveError(0, "network", err.message) from None
        if status >= 300:
            raise readDriveError(status, rawAnswer)
        return rawAnswer

    async def listFiles(self, query: str, accessToken: str) -> list[dict]:
        """Files matching a Drive search query, newest first; only this app's files are visible."""
        params = urllib.parse.urlencode({"q": query, "fields": "files(id,name,mimeType,size,createdTime)",
                                         "orderBy": "createdTime desc", "pageSize": "100", "spaces": "drive"},
                                        quote_via=urllib.parse.quote)
        answer = await self._send("GET", f"{driveApiUrl}/files?{params}", accessToken)
        return list((answer or {}).get("files", []))

    async def findOrCreateFolder(self, name: str, accessToken: str) -> str:
        """The ID of this app's folder with that name, made if there's none."""
        found = await self.listFiles(f"name = {quoteDriveText(name)} and mimeType = '{folderMimeType}' "
                                     "and trashed = false", accessToken)
        if found:
            return found[0]["id"]
        body = json.dumps({"name": name, "mimeType": folderMimeType}).encode("utf-8")
        made = await self._send("POST", f"{driveApiUrl}/files?fields=id", accessToken, body,
                                "application/json; charset=UTF-8")
        return made["id"]

    async def uploadFile(self, name: str, content: bytes, mimeType: str, parentId: str, accessToken: str) -> dict:
        """Uploads a file of up to 5 MB in one request; returns its id, name and size."""
        if len(content) > maxOneRequestUploadBytes:
            raise DriveError(0, "tooBig", "a backup over 5 MB needs Drive's resumable upload")
        body, contentType = multipartBody({"name": name, "parents": [parentId]}, content, mimeType)
        return await self._send("POST", f"{driveUploadUrl}/files?uploadType=multipart&fields=id,name,size",
                                accessToken, body, contentType)

    async def downloadFile(self, fileId: str, accessToken: str) -> bytes:
        """One of this app's files, as it is."""
        return await self._sendRaw("GET", f"{driveApiUrl}/files/{urllib.parse.quote(fileId, safe='')}?alt=media",
                                   accessToken)

    async def deleteFile(self, fileId: str, accessToken: str) -> None:
        """Deletes one of this app's files for good."""
        await self._send("DELETE", f"{driveApiUrl}/files/{urllib.parse.quote(fileId, safe='')}", accessToken)
