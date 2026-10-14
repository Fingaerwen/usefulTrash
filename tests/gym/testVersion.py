"""The version shown in the app, the build's version and Android's versionCode must agree (V3a, 12b)."""

import re
import tomllib
from pathlib import Path

from gym.model import appVersion

settings = tomllib.loads((Path(__file__).resolve().parents[2] / "apps" / "gym" / "pyproject.toml").read_text())


def testShownVersionMatchesTheBuild():
    assert appVersion == settings["project"]["version"]


def testVersionsLookLike0Point1Alpha():
    """0.1-alpha → 0.2-alpha → …: the middle number bumps, no third number (V3a)."""
    assert re.fullmatch(r"0\.\d+-alpha", appVersion)


def testVersionCodeIsTheMiddleNumber():
    """Android's versionCode must go up by one each release, so it's simply the middle number (12b)."""
    assert settings["tool"]["flet"]["build_number"] == int(appVersion.split(".")[1].split("-")[0])


def testTheAppIsCalledGymTracker():
    assert settings["tool"]["flet"]["product"] == "Gym Tracker"
    assert settings["tool"]["flet"]["android"]["bundle_id"] == "io.github.fingaerwen.gymtracker"
    assert settings["tool"]["flet"]["android"]["target_arch"] == ["arm64-v8a"]
