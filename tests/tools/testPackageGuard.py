"""Tests for the package guard (tools/packageGuard.py, CS1.1): our packages only ever come from this repo."""

import json
import zipfile
from pathlib import Path

import packageGuard

repoRoot = Path(__file__).resolve().parents[2]
realApp = repoRoot / "apps" / "gym"


def appWith(tmp_path: Path, dependencies: list[str], localPaths: dict[str, str]) -> Path:
    """An app folder with these settings (local paths may be absolute)."""
    folder = tmp_path / "app"
    folder.mkdir(exist_ok=True)
    lines = ["[project]", 'name = "testApp"', 'version = "0.1-alpha"', f"dependencies = {json.dumps(dependencies)}",
             "", "[tool.flet.dev_packages]"] + [f'{name} = "{path}"' for name, path in localPaths.items()]
    (folder / "pyproject.toml").write_text("\n".join(lines) + "\n")
    return folder


def testTheGymAppPassesBeforeBuilding():
    assert packageGuard.checkBeforeBuild(realApp) == []


def testAPackageWithoutALocalPathIsCaught(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3", "usefulTrashShared"], {})
    assert packageGuard.checkBeforeBuild(app) == [
        "'usefulTrashShared' has no local path in [tool.flet.dev_packages]: a build would look it up on PyPI."]


def testOnlyAPinnedFletAndOurPackages(tmp_path):
    app = appWith(tmp_path, ["flet>=1.0", "requests"], {})
    assert packageGuard.checkBeforeBuild(app) == [
        "Flet must be pinned to one exact version, not 'flet>=1.0'.",
        "'requests' isn't one of ours (no usefulTrash prefix): only Flet and our packages may be dependencies."]


def testALocalPathHoldingAnotherPackageIsCaught(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3", "usefulTrashSecureStore"],
                  {"usefulTrashSecureStore": str(repoRoot / "extensions" / "nativeGoogleSignIn")})
    assert packageGuard.checkBeforeBuild(app) == [
        "'usefulTrashSecureStore': its local path holds a package named 'usefulTrashNativeGoogleSignIn' instead."]


def builtPackage(sitePackages: Path, name: str, url: str | None) -> None:
    info = sitePackages / f"{name.lower()}-0.1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n")
    if url is not None:
        (info / "direct_url.json").write_text(json.dumps({"dir_info": {}, "url": url}))


def testAfterBuildingOurPackagesMustComeFromThisRepo(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3", "usefulTrashShared", "usefulTrashSecureStore"], {})
    arm = app / "build" / "site-packages" / "arm64-v8a"
    builtPackage(arm, "usefulTrashShared", (repoRoot / "shared").as_uri())
    builtPackage(arm, "usefulTrashSecureStore", "https://files.pythonhosted.org/somewhere")
    builtPackage(arm, "securestore", None)
    builtPackage(arm, "flet", "https://files.pythonhosted.org/flet")
    assert packageGuard.checkAfterBuild(app) == [
        "APK (arm64-v8a): a package named 'securestore' got into the build.",
        "APK (arm64-v8a): usefultrashsecurestore wasn't installed from this repo (it came from https)."]


def testTheWebsitesPackagesAreCheckedToo(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3", "usefulTrashShared"], {})
    bundle = app / "build" / "web" / "assets" / "app"
    bundle.mkdir(parents=True)
    with zipfile.ZipFile(bundle / "app.zip", "w") as archive:
        archive.writestr("__pypackages__/usefultrashshared-0.1.0.dist-info/METADATA", "Name: usefulTrashShared\n")
    assert packageGuard.checkAfterBuild(app) == [
        "website: usefultrashshared has no record of where it came from (direct_url.json)."]


def testAMissingPackageIsCaught(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3", "usefulTrashShared"], {})
    (app / "build" / "site-packages" / "arm64-v8a").mkdir(parents=True)
    assert packageGuard.checkAfterBuild(app) == ["APK (arm64-v8a): usefultrashshared is missing."]


def testNoBuildOutputIsAProblem(tmp_path):
    app = appWith(tmp_path, ["flet==1.0.3"], {})
    assert packageGuard.checkAfterBuild(app) == ["No build output found to check (build/site-packages or build/web)."]
