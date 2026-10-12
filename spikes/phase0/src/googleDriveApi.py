"""Google Drive calls for the Phase 0 spike (check 7): plain HTTPS to Drive's REST API (v3), with a
short-lived access token from Google Play services (the nativeGoogleSignIn extension's getDriveAccess).

Rules for this module (same as supabaseApi):
- HTTPS to www.googleapis.com only, with certificate checks. Redirects are refused, so the token can
  never be forwarded to another address.
- The access token only travels to Google in the Authorization header (never in a URL), and is never
  printed, logged or put in error messages.
- Every request has a timeout, so a dead connection can't hang the app.
- The permission is "files this app created" (drive.file): Drive only lists and changes those files.
Phone only: the PC view doesn't use Drive in Phase 0."""

import asyncio
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

googleApisUrl = "https://www.googleapis.com/"
driveApiUrl = googleApisUrl + "drive/v3"
driveUploadUrl = googleApisUrl + "upload/drive/v3"
folderMimeType = "application/vnd.google-apps.folder"
requestTimeoutSec = 30
maxOneRequestUploadBytes = 5 * 1024 * 1024  # Google's limit for an upload sent in one request (multipart)


class DriveError(Exception):
    """A refused or failed Drive call. Holds only Google's own error details, never request data."""

    def __init__(self, statusCode: int, reason: str, message: str):
        super().__init__(f"{statusCode} {reason}: {message}")
        self.statusCode = statusCode  # HTTP status; 0 = no answer (network problem)
        self.reason = reason  # e.g. "authError" (token refused), "accessNotConfigured" (Drive API not enabled)
        self.message = message


def readDriveError(statusCode: int, rawBody: bytes) -> DriveError:
    """Turns an error answer into a DriveError. Google APIs answer {"error": {"code", "message", "status",
    "errors": [{"reason": ...}]}}; Google's sign-in servers use the OAuth style {"error": ..., "error_description": ...}."""
    try:
        body = json.loads(rawBody or b"{}")
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    error = body.get("error")
    if isinstance(error, str):  # OAuth style
        return DriveError(statusCode, error, str(body.get("error_description") or "")[:300])
    if not isinstance(error, dict):
        error = {}
    details = error.get("errors")
    firstDetail = details[0] if isinstance(details, list) and details and isinstance(details[0], dict) else {}
    reason = str(firstDetail.get("reason") or error.get("status") or "unknown")
    return DriveError(statusCode, reason, str(error.get("message") or "")[:300])


def quoteDriveText(text: str) -> str:
    """Puts text in single quotes for a Drive search query, escaping backslashes and quotes."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def buildMultipartBody(metadata: dict, content: bytes, mimeType: str) -> tuple[bytes, str]:
    """Builds the body of a one-request upload: the file's details (JSON) and its content, as
    multipart/related. Returns (body, Content-Type header). The boundary is random and checked
    not to occur in either part."""
    if any(char in mimeType for char in "\r\n"):
        raise ValueError("A MIME type can't contain line breaks")
    metadataBytes = json.dumps(metadata).encode("utf-8")
    while True:
        boundary = f"usefulTrash-{secrets.token_hex(16)}"
        if boundary.encode("ascii") not in metadataBytes and boundary.encode("ascii") not in content:
            break
    body = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("ascii"),
        metadataBytes,
        f"\r\n--{boundary}\r\nContent-Type: {mimeType}\r\n\r\n".encode("ascii"),
        content,
        f"\r\n--{boundary}--\r\n".encode("ascii"),
    ])
    return body, f"multipart/related; boundary={boundary}"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect (same as supabaseApi): urllib would otherwise resend the token to the new address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # no new request → urllib raises HTTPError for the 3xx answer instead


_opener = urllib.request.build_opener(_RefuseRedirects)


class GoogleDriveApi:
    """Drive calls. The access token is passed in every time: tokens last about an hour, and the caller
    (driveAccess.DriveKeeper) gets a fresh one from Google Play services when Drive refuses one."""

    @staticmethod
    def _call(method: str, url: str, accessToken: str, body: bytes | None = None, contentType: str | None = None):
        """Sends one request and returns the parsed JSON answer (None if empty). Blocking: the async
        methods below run it in a worker thread."""
        if not url.startswith(googleApisUrl):
            raise ValueError(f"Drive calls only go to {googleApisUrl}")
        if not accessToken:
            raise DriveError(401, "noToken", "No Drive access token")
        headers = {"Authorization": f"Bearer {accessToken}", "Accept": "application/json"}
        if contentType:
            headers["Content-Type"] = contentType
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with _opener.open(request, timeout=requestTimeoutSec) as response:
                rawAnswer = response.read()
        except urllib.error.HTTPError as err:
            # "from None" keeps the request (and its Authorization header) out of the error's traceback.
            raise readDriveError(err.code, err.read()) from None
        except OSError as err:  # no connection, timeout, certificate problem (URLError, TimeoutError, SSLError)
            reason = getattr(err, "reason", err)
            raise DriveError(0, "network", f"{type(reason).__name__}: {reason}") from None
        return json.loads(rawAnswer) if rawAnswer else None

    async def _send(self, method: str, url: str, accessToken: str, body: bytes | None = None,
                    contentType: str | None = None):
        """Sends one request in a worker thread, so the app keeps responding."""
        return await asyncio.to_thread(self._call, method, url, accessToken, body, contentType)

    async def listFiles(self, query: str, accessToken: str, pageSize: int = 100) -> list[dict]:
        """Finds files with a Drive search query, newest first. Only files this app created are visible."""
        params = urllib.parse.urlencode({
            "q": query,
            "fields": "files(id,name,mimeType,size,createdTime)",
            "orderBy": "createdTime desc",
            "pageSize": str(pageSize),
            "spaces": "drive",
        }, quote_via=urllib.parse.quote)
        answer = await self._send("GET", f"{driveApiUrl}/files?{params}", accessToken)
        return list((answer or {}).get("files", []))

    async def findFolder(self, name: str, accessToken: str) -> dict | None:
        """Returns the newest folder with this name that this app created (not in the bin), or None."""
        folders = await self.listFiles(
            f"name = {quoteDriveText(name)} and mimeType = '{folderMimeType}' and trashed = false", accessToken
        )
        return folders[0] if folders else None

    async def createFolder(self, name: str, accessToken: str) -> dict:
        """Creates a folder in My Drive and returns its id and name."""
        body = json.dumps({"name": name, "mimeType": folderMimeType}).encode("utf-8")
        return await self._send("POST", f"{driveApiUrl}/files?fields=id,name", accessToken, body,
                                "application/json; charset=UTF-8")

    async def uploadFile(self, name: str, content: bytes, mimeType: str, parentId: str | None, accessToken: str) -> dict:
        """Uploads a small file (up to 5 MB) in one request and returns its id, name, size and creation time."""
        if len(content) > maxOneRequestUploadBytes:
            raise ValueError("Files over 5 MB need Drive's resumable upload, which this spike doesn't have")
        metadata = {"name": name, "parents": [parentId]} if parentId else {"name": name}
        body, contentType = buildMultipartBody(metadata, content, mimeType)
        url = f"{driveUploadUrl}/files?uploadType=multipart&fields=id,name,size,createdTime"
        return await self._send("POST", url, accessToken, body, contentType)

    async def deleteFile(self, fileId: str, accessToken: str) -> None:
        """Deletes a file for good (it skips the bin). Only works on files this app created."""
        await self._send("DELETE", f"{driveApiUrl}/files/{urllib.parse.quote(fileId, safe='')}", accessToken)

    async def moveToBin(self, fileId: str, accessToken: str) -> None:
        """Moves a file or folder to Drive's bin (it can be restored there for 30 days)."""
        body = json.dumps({"trashed": True}).encode("utf-8")
        await self._send("PATCH", f"{driveApiUrl}/files/{urllib.parse.quote(fileId, safe='')}?fields=id",
                         accessToken, body, "application/json; charset=UTF-8")
