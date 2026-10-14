"""The app's own log (plan 12d, DG1.1): recent events and problems for the Problems page. Nothing is
ever sent anywhere: you copy the report yourself if you want to.

Phone: two small files in the app's private storage. When the current one passes 256 KB it replaces
the older one, so the log never grows past about 512 KB. PC view: memory only, so nothing is stored in
the browser. The log never prints, so release builds write nothing to Android's own log.

No secrets or personal details: code logs events and kinds, never values. HTTP errors go in as status,
code and a short message; tokens only as fingerprints. Every line also passes a scrubber that removes
anything token-, key- or email-shaped, plus the current session's own token values, as a safety net.
"""

import datetime as dt
import hashlib
import os
import re
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass

maxFileBytes = 256 * 1024
maxLineLength = 600
memoryLines = 2000  # the PC view keeps this many lines
currentName, olderName = "appLog.txt", "appLog.old.txt"

# What the scrubber removes, most specific first. Each pattern stands for a kind of secret or personal detail.
scrubRules: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), "[private key]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"), "[token]"),  # JWTs: Supabase, Google ID
    (re.compile(r"ya29\.[A-Za-z0-9_-]{8,}"), "[token]"),  # Google access tokens (Drive)
    (re.compile(r"1//[A-Za-z0-9_-]{8,}"), "[token]"),  # Google refresh tokens
    (re.compile(r"sb_(?:secret|publishable)_[A-Za-z0-9_-]{6,}"), "[key]"),  # Supabase keys
    (re.compile(r"GOCSPX-[A-Za-z0-9_-]{6,}"), "[key]"),  # Google client secrets
    (re.compile(r"AIza[A-Za-z0-9_-]{30,}"), "[key]"),  # Google API keys
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{6,}"), r"\1[token]"),
    (re.compile(r"(?i)((?:access|refresh|id|provider)_?token|apikey|api_key|password|secret|nonce)"
                r"(\"?\s*[:=]\s*\"?)[^\s\"',;&}]{4,}"), r"\1\2[removed]"),
    (re.compile(r"[A-Za-z0-9_-]{40,}"), "[long value]"),  # any other long random-looking value
)
tokenShaped = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|ya29\.[A-Za-z0-9_-]{20,}")


def fingerprint(secret: str) -> str:
    """The first 8 hex characters of a token's SHA-256: enough to tell two tokens apart, useless to anyone."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8] if secret else "none"


def scrub(text: str, knownSecrets: Iterable[str] = ()) -> str:
    """Removes known secret values and anything token-, key- or email-shaped from text."""
    for secret in knownSecrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[token]")
    for pattern, replacement in scrubRules:
        text = pattern.sub(replacement, text)
    return text


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One line of the log, read back for the Problems page."""

    at: str  # UTC time, to the second
    level: str  # info, problem or crash
    area: str  # sync, signIn, backup, start, …
    plainWords: str  # what happened, for you
    technical: str  # the details underneath, for me


@dataclass(frozen=True, slots=True)
class LogCheck:
    """The Problems page's log check (Phase 0's): how many lines, and how many look like tokens."""

    lines: int
    tokenShapedStrings: int
    knownSecretsFound: int


class AppLog:
    """The log. folder=None keeps it in memory only (the PC view)."""

    def __init__(self, folder: str | None, clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
                 knownSecrets: Callable[[], Iterable[str]] = lambda: ()):
        self.folder = folder
        self.clock = clock
        self.knownSecrets = knownSecrets  # the current tokens, so even a short one can't reach the log
        self._memory: list[str] = []

    # --- Writing -----------------------------------------------------------------------------

    def info(self, area: str, plainWords: str, technical: str = "") -> None:
        self._write("info", area, plainWords, technical)

    def problem(self, area: str, plainWords: str, technical: str = "") -> None:
        self._write("problem", area, plainWords, technical)

    def crash(self, error: BaseException, area: str = "app") -> None:
        """An unexpected error: its kind, its message and where it happened (file and line, no values)."""
        frames = traceback.extract_tb(error.__traceback__)[-4:]
        where = " < ".join(f"{os.path.basename(frame.filename)}:{frame.lineno} {frame.name}"
                           for frame in reversed(frames))
        self._write("crash", area, "Something went wrong unexpectedly.",
                    f"{type(error).__name__}: {error} | at {where or 'unknown'}")

    def _write(self, level: str, area: str, plainWords: str, technical: str) -> None:
        secrets = list(self.knownSecrets())
        cleanWords = scrub(plainWords, secrets).replace("|", "/").replace("\n", " ")
        cleanTechnical = scrub(technical, secrets).replace("\n", " ")
        at = self.clock().astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{at} {level} {area}: {cleanWords}" + (f" | {cleanTechnical}" if cleanTechnical else "")
        line = line[:maxLineLength]
        if self.folder is None:
            self._memory.append(line)
            del self._memory[:-memoryLines]
            return
        current = os.path.join(self.folder, currentName)
        try:
            if os.path.exists(current) and os.path.getsize(current) >= maxFileBytes:
                os.replace(current, os.path.join(self.folder, olderName))  # the older file is dropped
            with open(current, "a", encoding="utf-8") as file:
                file.write(line + "\n")
        except OSError:
            pass  # a log that can't be written must never stop the app

    # --- Reading -----------------------------------------------------------------------------

    def lines(self) -> list[str]:
        """Every line, oldest first."""
        if self.folder is None:
            return list(self._memory)
        found: list[str] = []
        for name in (olderName, currentName):
            try:
                with open(os.path.join(self.folder, name), encoding="utf-8", errors="replace") as file:
                    found += file.read().splitlines()
            except OSError:
                continue
        return found

    def entries(self, levels: tuple[str, ...] = ("problem", "crash"), limit: int = 50) -> list[LogEntry]:
        """The newest problems and crashes first, for the Problems page."""
        entries = []
        for line in reversed(self.lines()):
            parts = line.split(" ", 3)
            if len(parts) < 4 or parts[1] not in levels:
                continue
            plainWords, _, technical = parts[3].partition(" | ")
            entries.append(LogEntry(parts[0], parts[1], parts[2].rstrip(":"), plainWords, technical))
            if len(entries) >= limit:
                break
        return entries

    def clear(self) -> None:
        """The Problems page's Clear button."""
        self._memory.clear()
        if self.folder is not None:
            for name in (olderName, currentName):
                try:
                    os.remove(os.path.join(self.folder, name))
                except OSError:
                    pass

    def check(self, extraFiles: Iterable[str] = ()) -> LogCheck:
        """Phase 0's log check: counts lines and token-shaped strings in the log (and in extraFiles, such
        as Flet's own console.log), and whether any current token value appears."""
        texts = ["\n".join(self.lines())]
        for path in extraFiles:
            try:
                with open(path, encoding="utf-8", errors="replace") as file:
                    texts.append(file.read())
            except OSError:
                continue
        everything = "\n".join(texts)
        secrets = [secret for secret in self.knownSecrets() if secret]
        return LogCheck(len(self.lines()), len(tokenShaped.findall(everything)),
                        sum(1 for secret in secrets if secret in everything))
