"""Google Drive's REST API in memory, as far as the backups use it (F14.1): a transport for
usefulShared.backup.driveApi.DriveApi, so its real requests (searches, the multipart upload, deletes) are
what's tested. Not a test file itself: pytest only collects test*.py."""

import json
import re
import urllib.parse


class DriveStandIn:
    def __init__(self, validTokens: set[str] | None = None):
        self.validTokens = validTokens if validTokens is not None else {"driveToken1"}
        self.files: dict[str, dict] = {}  # id → {"id", "name", "mimeType", "parents", "content", "createdTime"}
        self.made = 0

    def _new(self, **fields) -> dict:
        self.made += 1
        file = {"id": f"file{self.made}", "createdTime": f"2026-01-01T00:00:{self.made:02d}Z", "parents": [],
                "content": b"", **fields}
        self.files[file["id"]] = file
        return file

    def zips(self) -> list[dict]:
        return [file for file in self.files.values() if file["mimeType"] == "application/zip"]

    async def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        if headers.get("Authorization", "").removeprefix("Bearer ") not in self.validTokens:
            return 401, json.dumps({"error": {"code": 401, "errors": [{"reason": "authError"}]}}).encode()
        address = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(address.query)
        if method == "GET" and address.path == "/drive/v3/files":
            found = sorted((file for file in self.files.values() if _matches(query["q"][0], file)),
                           key=lambda file: file["createdTime"], reverse=True)
            return 200, json.dumps({"files": [{key: file[key] for key in ("id", "name", "mimeType", "createdTime")}
                                              for file in found]}).encode()
        if method == "POST" and address.path == "/drive/v3/files":
            details = json.loads(body)
            return 200, json.dumps({"id": self._new(name=details["name"], mimeType=details["mimeType"])["id"]}).encode()
        if method == "POST" and address.path == "/upload/drive/v3/files":
            boundary = headers["Content-Type"].split("boundary=")[1].encode()
            parts = body.split(b"--" + boundary)
            metadata = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
            content = parts[2].split(b"\r\n\r\n", 1)[1][:-2]  # without the CRLF before the closing boundary
            file = self._new(name=metadata["name"], parents=metadata["parents"], mimeType="application/zip",
                             content=content)
            return 200, json.dumps({"id": file["id"], "name": file["name"], "size": str(len(content))}).encode()
        if method == "DELETE" and address.path.startswith("/drive/v3/files/"):
            self.files.pop(urllib.parse.unquote(address.path.rsplit("/", 1)[1]))
            return 204, b""
        return 404, json.dumps({"error": {"code": 404, "errors": [{"reason": "notFound"}]}}).encode()


def _matches(query: str, file: dict) -> bool:
    """The two searches the backups make: the folder by name, and the zips in a folder."""
    name = re.search(r"name = '([^']*)'", query)
    parent = re.search(r"'([^']*)' in parents", query)
    mimeType = re.search(r"mimeType = '([^']*)'", query)
    return ((name is None or file["name"] == name.group(1)) and (parent is None or parent.group(1) in file["parents"])
            and (mimeType is None or file["mimeType"] == mimeType.group(1)))
