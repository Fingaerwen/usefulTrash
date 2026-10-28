"""Tests for the release script's own rules (tools/buildRelease.py). The full run needs the signing key."""

import pytest

import buildRelease
import makeSigningKey

talon, ambrosia = buildRelease.apps["talon"], buildRelease.apps["ambrosia"]


def testVersionCodesOfEarlierReleasesFromTheirTags():
    tags = ["gym-v0.1-alpha", "gym-v0.12-alpha", "other-v1", "gym-v1.0", "ambrosia-v0.1-alpha"]
    assert buildRelease.releasedBuildNumbers(tags, "gym-v") == [1, 12]
    assert buildRelease.releasedBuildNumbers(tags, "ambrosia-v") == [1]


def testTheTagSaysWhichApp():
    """Talon keeps Gym Tracker's gym-v tags (AM1.4). Ambrosia's are its own (4h)."""
    assert (talon.tagPrefix, talon.title, talon.folder.name) == ("gym-v", "Talon", "gym")
    assert (ambrosia.tagPrefix, ambrosia.title, ambrosia.folder.name) == ("ambrosia-v", "Ambrosia", "diet")
    assert buildRelease.versionInfo(talon) == ("0.4-alpha", 4) and buildRelease.versionInfo(ambrosia) == ("0.1-alpha", 1)


def testTheCommandLineNamesTheApps():
    assert buildRelease.chosenApps(["ambrosia", "talon", "--buildOnly"]) == [talon, ambrosia]  # the joint release
    assert buildRelease.chosenApps(["ambrosia"]) == [ambrosia]
    for wrong in ([], ["--cloudReady"], ["gym"], ["talon", "talon"]):
        with pytest.raises(buildRelease.ReleaseStopped, match="Name the app"):
            buildRelease.chosenApps(wrong)


def testTheSiteHoldsTheStartPageThePagesAndBothPcViews(tmp_path):
    """4c: the start page as index.html with its images, about, privacy and driveToken.html where Google has them,
    and each PC view in the folder the start page links to."""
    builds = {}
    for name in ("talon", "ambrosia"):
        builds[name] = tmp_path / f"{name}Web"
        builds[name].mkdir()
        (builds[name] / "index.html").write_text(f"<title>{name}</title>")
    site = tmp_path / "site"
    buildRelease.assembleSite(site, builds)
    files = {path.relative_to(site).as_posix() for path in site.rglob("*") if path.is_file()}
    assert {"index.html", "about.html", "privacy.html", "driveToken.html", ".nojekyll", "talon/index.html",
            "ambrosia/index.html", "images/talon.webp", "images/goddess.webp", "images/katana.webp"} <= files
    start = (site / "index.html").read_text()
    assert 'href="talon/"' in start and 'href="ambrosia/"' in start
    assert {talon.sitePath, ambrosia.sitePath} == {"talon", "ambrosia"}


def testFingerprintsAreReadFromKeytoolsListing():
    listing = ("Alias name: upload\nCertificate fingerprints:\n\t SHA1: 0A:1B:2C:3D\n"
               "\t SHA256: AA:BB:CC:DD:EE\nSignature algorithm name: SHA384withRSA\n")
    assert makeSigningKey.fingerprints(listing) == {"SHA1": "0A:1B:2C:3D", "SHA256": "AA:BB:CC:DD:EE"}


def testTheSigningFolderIsOutsideTheRepo():
    assert buildRelease.repoRoot not in buildRelease.signingEnvPath.parents
    assert makeSigningKey.signingFolder == buildRelease.signingEnvPath.parent
