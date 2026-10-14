"""Tests for the build leak scan (tools/leakScan.py): secret formats and private .env values are found,
zips inside zips included, and reported by name only. Fake values are built while the tests run."""

import io
import zipfile

import leakScan

fakeAdminKey = ("sb_" + "secret_" + "z" * 20).encode()
fakePrivateValue = "private" + "Value" + "123"


def zipped(**files: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def testSecretFormatsAreFoundInsideZipsInsideZips(tmp_path):
    inner = zipped(**{"main.pyc": b"code " + fakeAdminKey + b" more"})
    apk = tmp_path / "app.apk"
    apk.write_bytes(zipped(**{"assets/app.zip": inner, "classes.dex": b"nothing here"}))
    findings = leakScan.scan([apk], envPath=tmp_path / "missing.env")
    assert findings == [f"{apk}!assets/app.zip!main.pyc: Supabase secret key"]
    assert fakeAdminKey.decode() not in "".join(findings)


def testPrivateEnvValuesAreFoundButPublicOnesAllowed(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"SUPABASE_URL=https://example.supabase.co\nOTHER_VALUE={fakePrivateValue}\n")
    site = tmp_path / "web"
    site.mkdir()
    (site / "index.html").write_text(f"https://example.supabase.co and {fakePrivateValue}")
    assert leakScan.scan([site], envPath=env) == [f"{site / 'index.html'}: the value of OTHER_VALUE"]


def testExtraValuesLikeTheSigningPasswordAreFound(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(zipped(**{"config.json": b'{"x": "' + fakePrivateValue.encode() + b'"}'}))
    assert leakScan.scan([apk], envPath=tmp_path / "missing.env", extra={"SIGNING_PASSWORD": fakePrivateValue.encode()}) == [
        f"{apk}!config.json: the value of SIGNING_PASSWORD"]


def testACleanBuildHasNoFindings(tmp_path):
    apk = tmp_path / "clean.apk"
    apk.write_bytes(zipped(**{"a.txt": b"hello"}))
    assert leakScan.scan([apk], envPath=tmp_path / "missing.env") == []
