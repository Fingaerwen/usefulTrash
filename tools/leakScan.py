"""Leak scan for builds (plan 12b, release script step 4): searches an APK or the website's files, zips
inside zips included, for anything secret: known secret formats (Supabase secret keys, Google client
secrets, private keys) and every value in .env except the three public ones the app may hold (K2a).
Reports what and where by name only, never the value.

Usage (from the repo root): python3 tools/leakScan.py <apk or folder> ...
"""

import io
import re
import sys
import zipfile
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[1]
publicNames = {"SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "GOOGLE_WEB_CLIENT_ID"}  # allowed inside (K2a)
secretFormats = {
    "Supabase secret key": re.compile(rb"sb_secret_[A-Za-z0-9_-]{8,}"),
    "Google client secret": re.compile(rb"GOCSPX-[A-Za-z0-9_-]{8,}"),
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
maxDepth = 4  # zips inside zips, this deep


def envSecrets(envPath: Path) -> dict[str, bytes]:
    """Every .env value that must never be in a build: all of them except the three public ones."""
    found = {}
    if envPath.exists():
        for line in envPath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if name.strip() not in publicNames and len(value) >= 6:
                found[name.strip()] = value.encode("utf-8")
    return found


def scanBytes(where: str, content: bytes, secrets: dict[str, bytes], depth: int = 0) -> list[str]:
    """Findings in one file's bytes. A zip (an APK is one) is opened and each file in it scanned instead,
    so a find names the innermost file; anything that isn't a readable zip is scanned as it is."""
    if depth < maxDepth and content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                findings = _findings(f"{where} (zip comment)", archive.comment, secrets)
                for entry in archive.namelist():
                    findings += scanBytes(f"{where}!{entry}", archive.read(entry), secrets, depth + 1)
                return findings
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
            pass  # not a readable zip after all: scan its bytes as they are
    return _findings(where, content, secrets)


def _findings(where: str, content: bytes, secrets: dict[str, bytes]) -> list[str]:
    findings = [f"{where}: {kind}" for kind, pattern in secretFormats.items() if pattern.search(content)]
    return findings + [f"{where}: the value of {name} from .env" for name, value in secrets.items() if value in content]


def scan(paths: list[Path], envPath: Path = repoRoot / ".env") -> list[str]:
    """Findings in APKs, zips or folders of files."""
    secrets = envSecrets(envPath)
    findings = []
    for path in paths:
        files = sorted(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else [path]
        for file in files:
            findings += scanBytes(str(file.relative_to(repoRoot) if repoRoot in file.parents else file),
                                  file.read_bytes(), secrets)
    return findings


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 tools/leakScan.py <apk or folder> ...")
        return 2
    findings = scan([Path(argument).resolve() for argument in sys.argv[1:]])
    for finding in findings:
        print(f"❌ {finding}")
    if not findings:
        print("✅ Leak scan: no secret formats and no private .env values found.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
