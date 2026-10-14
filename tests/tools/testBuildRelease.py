"""Tests for the release script's own rules (tools/buildRelease.py); the full run needs the signing key."""

import buildRelease
import makeSigningKey


def testVersionCodesOfEarlierReleasesFromTheirTags():
    assert buildRelease.releasedBuildNumbers(["gym-v0.1-alpha", "gym-v0.12-alpha", "other-v1", "gym-v1.0"]) == [1, 12]


def testTheTagSaysWhichApp():
    version, buildNumber = buildRelease.versionInfo()
    assert f"{buildRelease.tagPrefix}{version}" == f"gym-v{version}" and buildNumber >= 1


def testFingerprintsAreReadFromKeytoolsListing():
    listing = ("Alias name: upload\nCertificate fingerprints:\n\t SHA1: 0A:1B:2C:3D\n"
               "\t SHA256: AA:BB:CC:DD:EE\nSignature algorithm name: SHA384withRSA\n")
    assert makeSigningKey.fingerprints(listing) == {"SHA1": "0A:1B:2C:3D", "SHA256": "AA:BB:CC:DD:EE"}


def testTheSigningFolderIsOutsideTheRepo():
    assert buildRelease.repoRoot not in buildRelease.signingEnvPath.parents
    assert makeSigningKey.signingFolder == buildRelease.signingEnvPath.parent
