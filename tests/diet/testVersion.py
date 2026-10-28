"""Ambrosia's version shown in the app, the build's version and Android's versionCode must agree (V3a, 12b), and its
build settings name it and place its PC view (AM1.2, 4c)."""

import re
import tomllib
from pathlib import Path

from ambrosia.model import appName, appVersion

settings = tomllib.loads((Path(__file__).resolve().parents[2] / "apps" / "diet" / "pyproject.toml").read_text())


def testShownVersionMatchesTheBuild():
    assert appVersion == settings["project"]["version"] == "0.1-alpha"


def testVersionsLookLike0Point1Alpha():
    assert re.fullmatch(r"0\.\d+-alpha", appVersion)


def testVersionCodeIsTheMiddleNumber():
    assert settings["tool"]["flet"]["build_number"] == int(appVersion.split(".")[1].split("-")[0])


def testTheAppIsCalledAmbrosia():
    assert settings["tool"]["flet"]["product"] == appName == "Ambrosia"
    assert settings["tool"]["flet"]["android"]["bundle_id"] == "io.github.fingaerwen.ambrosia"
    assert settings["tool"]["flet"]["android"]["target_arch"] == ["arm64-v8a"]


def testThePcViewIsBuiltForItsAddressWithoutCdns():
    assert settings["tool"]["flet"]["web"] == {"base_url": "/usefulTrash/ambrosia/", "cdn": False}


def testThePackageGuardIsHappyBeforeABuild():
    """Every package of ours has its local path (CS1.1)."""
    import packageGuard

    assert packageGuard.checkBeforeBuild(Path(__file__).resolve().parents[2] / "apps" / "diet") == []
