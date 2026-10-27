"""Tests for the app's log and its scrubber (plan 12d): fake tokens, keys and email addresses go in and
must come out removed, useful details stay, and the log never grows past two small files.

The fake secrets are built while the tests run, so nothing token-, key- or email-shaped is in this
file itself (the repo's leak checks would rightly refuse it)."""

import base64
import json
import os

import pytest

from usefulShared.platform.appLog import AppLog, fingerprint, maxFileBytes, memoryLines, scrub


def fakeJwt() -> str:
    """A made-up token shaped like Supabase's access tokens and Google's ID tokens."""
    def part(content: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(content).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'HS256', 'typ': 'JWT'})}.{part({'sub': 'someone', 'role': 'authenticated'})}.c2lnbmF0dXJl"


fakeEmail = "someone" + "@" + "example.com"
fakeSecrets = {
    "jwt": fakeJwt(),
    "googleAccessToken": "ya29" + ".a0AfB_" + "x" * 40,
    "googleRefreshToken": "1/" + "/0g" + "y" * 30,
    "supabaseAdmin": "sb_" + "secret_" + "k" * 30,
    "supabasePublishable": "sb_" + "publishable_" + "p" * 30,
    "googleClient": "GOCSPX" + "-" + "s" * 28,
    "email": fakeEmail,
    "privateKey": "-----BEGIN " + "PRIVATE KEY-----\nMIIEv" + "q" * 60 + "\n-----END " + "PRIVATE KEY-----",
    "longRandomValue": "Zx9" * 20,
}


@pytest.mark.parametrize("kind", fakeSecrets)
def testSecretsAreRemoved(kind):
    secret = fakeSecrets[kind]
    cleaned = scrub(f"sign-in failed for {secret} at step 2")
    assert secret not in cleaned
    assert cleaned.startswith("sign-in failed for [") and cleaned.endswith("at step 2")


@pytest.mark.parametrize("line", [
    'Authorization: Bearer abc123shortToken',
    '{"refresh_token": "v1shortRandom", "expires_in": 3600}',
    "access_token=abcdefgh&token_type=bearer",
    "password: hunter22",
])
def testLabelledSecretsAreRemovedEvenWhenShort(line):
    cleaned = scrub(line)
    assert "abc123shortToken" not in cleaned and "v1shortRandom" not in cleaned
    assert "abcdefgh" not in cleaned and "hunter22" not in cleaned


def testTheSessionsOwnTokensAreRemovedWhateverTheirShape():
    """Supabase refresh tokens are short and look like nothing in particular, so the log is told the
    current ones."""
    log = AppLog(None, knownSecrets=lambda: ["qwErty12zx"])
    log.problem("signIn", "renewal failed", "refresh qwErty12zx was refused")
    assert "qwErty12zx" not in "\n".join(log.lines())


def testUsefulDetailsStay():
    line = ("400 P0001: futureEdit: check the device's clock | bodyWeight be055b0d-fdfa-5290-8a6f-eb9d25bde5f3 "
            "| code 23514 | syncEngine.py:120 _sendOne | token a1b2c3d4")
    assert scrub(line) == line


def testFingerprints():
    assert len(fingerprint("one token")) == 8
    assert fingerprint("one token") == fingerprint("one token") != fingerprint("another token")
    assert fingerprint("") == "none"


# --- The log files ------------------------------------------------------------------------------

def testLogKeepsAtMostTwoSmallFiles(tmp_path):
    log = AppLog(str(tmp_path))
    for number in range(4000):  # about 1.2 MB of lines
        log.info("sync", f"round {number} done", "some detail " * 23)
    sizes = {name: os.path.getsize(tmp_path / name) for name in os.listdir(tmp_path)}
    assert set(sizes) == {"appLog.txt", "appLog.old.txt"}
    assert all(size <= maxFileBytes + 700 for size in sizes.values())
    lines = log.lines()
    assert "round 3999 done" in lines[-1] and "round 0 done" not in lines[0]  # the oldest were dropped


def testPcViewKeepsItInMemoryOnly(tmp_path):
    log = AppLog(None)
    log.info("start", "PC view opened")
    assert log.lines()[0].endswith("info start: PC view opened")
    assert os.listdir(tmp_path) == []
    for number in range(memoryLines + 10):
        log.info("sync", f"round {number}")
    assert len(log.lines()) == memoryLines and log.lines()[-1].endswith(f"round {memoryLines + 9}")


def testUnwritableFolderNeverStopsTheApp(tmp_path):
    log = AppLog(str(tmp_path / "missing" / "folder"))
    log.problem("sync", "couldn't send")  # no error
    assert log.lines() == []


def testCrashesSayWhereButNeverTheValues(tmp_path):
    log = AppLog(str(tmp_path))

    def failingStep():
        raise ValueError(f"bad answer containing {fakeSecrets['jwt']}")

    try:
        failingStep()
    except ValueError as error:
        log.crash(error, "sync")
    (entry,) = log.entries()
    assert (entry.level, entry.area, entry.plainWords) == ("crash", "sync", "Something went wrong unexpectedly.")
    assert entry.technical.startswith("ValueError: bad answer containing [token]")
    assert "testAppLog.py:" in entry.technical and "failingStep" in entry.technical
    assert fakeSecrets["jwt"] not in "\n".join(log.lines())


def testProblemsPageEntriesNewestFirst(tmp_path):
    log = AppLog(str(tmp_path))
    log.problem("sync", "A change was refused by the cloud.", "400 P0001: futureEdit")
    log.info("sync", "round done")
    log.problem("backup", "The backup couldn't be uploaded | twice", "0 network: OSError")
    first, second = log.entries()
    assert (first.area, first.plainWords, first.technical) == ("backup", "The backup couldn't be uploaded / twice",
                                                               "0 network: OSError")
    assert (second.area, second.technical) == ("sync", "400 P0001: futureEdit")
    log.clear()
    assert log.lines() == [] and log.entries() == []


def testLogCheckCountsTokenShapedStrings(tmp_path):
    """Phase 0's check: our log has none. Flet's own console.log is checked too."""
    log = AppLog(str(tmp_path), knownSecrets=lambda: ["currentRefresh9"])
    log.problem("signIn", f"refused {fakeSecrets['jwt']}")
    consoleLog = tmp_path / "console.log"
    consoleLog.write_text(f"something printed {fakeSecrets['jwt']} and currentRefresh9\n")
    check = log.check([str(consoleLog)])
    assert (check.lines, check.tokenShapedStrings, check.knownSecretsFound) == (1, 1, 1)
    assert log.check().tokenShapedStrings == 0
