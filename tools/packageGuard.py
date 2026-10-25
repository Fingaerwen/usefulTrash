"""The package guard (plan 2 and 3b, CS1.1): our own packages must come from our own folders, never from
PyPI, where strangers' packages with similar names exist (PyPI already has a "securestore" and a "shared").

Before a build: every dependency of the app is either Flet (pinned) or one of ours (the usefulTrash
prefix), and each of ours has a local path in [tool.flet.dev_packages] that holds a package of exactly
that name. After a build: every one of ours inside the APK's and the website's packages was installed
from a file:// address inside this repo, and nothing with one of the old or colliding names got in.

Usage (from the repo root): python3 tools/packageGuard.py before|after [appFolder]
"""

import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

repoRoot = Path(__file__).resolve().parents[1]
ourPrefix = "usefultrash"  # normalized: every package of ours is named usefulTrash<Something>
# Names that must never appear in a build: our packages' old names and PyPI look-alikes.
forbiddenNames = {"securestore", "shared", "usefulshared", "nativegooglesignin", "weighinnotify", "barcodescan"}


def normalized(name: str) -> str:
    """A package name as pip compares them (PEP 503): lower case, runs of - _ . as one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def isOurs(name: str) -> bool:
    return normalized(name).startswith(ourPrefix)


def _requirementName(requirement: str) -> str:
    return re.split(r"[\s<>=!~;\[@]", requirement.strip(), maxsplit=1)[0]


def checkBeforeBuild(appFolder: Path) -> list[str]:
    """The app's settings: only Flet (pinned) and our own packages, each with a correct local path."""
    problems = []
    settings = tomllib.loads((appFolder / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = settings.get("project", {}).get("dependencies", [])
    localPaths = settings.get("tool", {}).get("flet", {}).get("dev_packages", {})
    localByName = {normalized(name): path for name, path in localPaths.items()}
    ours = set()
    for requirement in dependencies:
        name = _requirementName(requirement)
        if normalized(name) == "flet":
            if not re.fullmatch(r"flet==\d+\.\d+\.\d+", requirement.replace(" ", "")):
                problems.append(f"Flet must be pinned to one exact version, not {requirement!r}.")
            continue
        if not isOurs(name):
            problems.append(f"{name!r} isn't one of ours (no usefulTrash prefix): only Flet and our packages may "
                            "be dependencies.")
            continue
        ours.add(normalized(name))
        if normalized(name) not in localByName:
            problems.append(f"{name!r} has no local path in [tool.flet.dev_packages]: a build would look it up on PyPI.")
            continue
        folder = (appFolder / localByName[normalized(name)]).resolve()
        if not (folder / "pyproject.toml").exists():
            problems.append(f"{name!r}: its local path {localByName[normalized(name)]} has no pyproject.toml.")
            continue
        actualName = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]
        if normalized(actualName) != normalized(name):
            problems.append(f"{name!r}: its local path holds a package named {actualName!r} instead.")
        if repoRoot not in folder.parents:
            problems.append(f"{name!r}: its local path is outside this repo.")
    for name in localByName:
        if name not in ours:
            problems.append(f"[tool.flet.dev_packages] lists {name!r}, which isn't a dependency.")
    return problems


def checkAfterBuild(appFolder: Path) -> list[str]:
    """The built APK's and website's packages: ours came from this repo, and no forbidden name got in."""
    settings = tomllib.loads((appFolder / "pyproject.toml").read_text(encoding="utf-8"))
    expected = {normalized(_requirementName(r)) for r in settings["project"]["dependencies"] if isOurs(_requirementName(r))}
    problems = []
    places = 0
    build = appFolder / "build"
    for archFolder in sorted((build / "site-packages").glob("*")) if (build / "site-packages").exists() else []:
        if archFolder.is_dir():
            places += 1
            records = {path.parent.name: path.read_text(encoding="utf-8")
                       for path in archFolder.glob("*.dist-info/METADATA")}
            urls = {path.parent.name: path.read_text(encoding="utf-8") for path in archFolder.glob("*.dist-info/direct_url.json")}
            problems += _checkPackages(f"APK ({archFolder.name})", records, urls, expected)
    webZip = build / "web" / "assets" / "app" / "app.zip"
    if webZip.exists():
        places += 1
        with zipfile.ZipFile(webZip) as bundle:
            names = bundle.namelist()
            records = {PurePosixPath(name).parent.name: bundle.read(name).decode("utf-8") for name in names
                       if name.endswith(".dist-info/METADATA")}
            urls = {PurePosixPath(name).parent.name: bundle.read(name).decode("utf-8") for name in names
                    if name.endswith(".dist-info/direct_url.json")}
        problems += _checkPackages("website", records, urls, expected)
    if places == 0:
        problems.append("No build output found to check (build/site-packages or build/web).")
    return problems


def _checkPackages(where: str, metadata: dict[str, str], directUrls: dict[str, str], expected: set[str]) -> list[str]:
    problems = []
    found = set()
    for folder, text in sorted(metadata.items()):  # sorted, so the report is the same every time
        nameLine = next((line for line in text.splitlines() if line.startswith("Name:")), "Name: ?")
        name = normalized(nameLine.partition(":")[2].strip())
        if name in forbiddenNames:
            problems.append(f"{where}: a package named {name!r} got into the build.")
        if not name.startswith(ourPrefix):
            continue
        found.add(name)
        if folder not in directUrls:
            problems.append(f"{where}: {name} has no record of where it came from (direct_url.json).")
            continue
        url = json.loads(directUrls[folder]).get("url", "")
        parsed = urlparse(url)
        path = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else None
        if path is None or (path != repoRoot and repoRoot not in path.parents):
            problems.append(f"{where}: {name} wasn't installed from this repo (it came from {parsed.scheme or '?'}).")
    for name in sorted(expected - found):
        problems.append(f"{where}: {name} is missing.")
    return problems


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("before", "after"):
        print("Usage: python3 tools/packageGuard.py before|after [appFolder]")
        return 2
    appFolder = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else repoRoot / "apps" / "gym"
    problems = checkBeforeBuild(appFolder) if sys.argv[1] == "before" else checkAfterBuild(appFolder)
    for problem in problems:
        print(f"❌ {problem}")
    if not problems:
        print(f"✅ Package guard ({sys.argv[1]} the build): our packages come from this repo only.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
