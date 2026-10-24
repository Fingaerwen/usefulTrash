"""Builds a release of Gym Tracker with every check before and after (plan 12b, RL3):

1. Checks: on main, nothing uncommitted, everything pushed, all tests pass, the version is new (no tag
   for it yet, versionCode above the last release's), and the package guard (CS1.1).
2. Writes the public config from .env (tools/makePublicConfig.py).
3. Builds the signed APK and the PC view. The signing values come from the private signing folder
   (tools/makeSigningKey.py) and reach the build through its environment only: never typed, never on a
   command line, never printed (F20; checked in Flet 1.0.3: its logs never show the environment).
4. Checks after: the package guard and the leak scan on both builds (secret formats, private .env values,
   the signing password), and the APK's signing certificate must match apps/gym/signingCertificate.txt.
5. Tags the version. Then, once you confirm any cloud upgrade for this release is done (14c), publishes
   the PC view to the gh-pages branch as one commit replacing the last (P6.1).
6. Tells you the rest: the GitHub release (made by you, on the website: no GitHub token anywhere) and
   Obtainium.

Usage (from the repo root): python3 tools/buildRelease.py [--cloudReady | --buildOnly]
  --cloudReady: you've already confirmed the cloud upgrade for this release is done (or there is none).
  --buildOnly: steps 1 to 4 only, a trial run: nothing is tagged or published.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import leakScan
import makePublicConfig
import packageGuard

repoRoot = Path(__file__).resolve().parents[1]
appFolder = repoRoot / "apps" / "gym"
python = repoRoot / ".venv" / "bin" / "python"
flet = repoRoot / ".venv" / "bin" / "flet"
signingEnvPath = Path.home() / ".local" / "share" / "usefulTrash" / "signing" / "signing.env"
fingerprintPath = appFolder / "signingCertificate.txt"
tagPrefix = "gym-v"  # one repo, several apps later: tags say which app


class ReleaseStopped(Exception):
    """A check failed; the message says which, in plain words."""


def run(command: list[str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=options.pop("cwd", repoRoot), text=True, **options)


def git(*arguments: str) -> str:
    result = run(["git", *arguments], capture_output=True)
    if result.returncode != 0:
        raise ReleaseStopped(f"git {arguments[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def versionInfo() -> tuple[str, int]:
    settings = tomllib.loads((appFolder / "pyproject.toml").read_text(encoding="utf-8"))
    return settings["project"]["version"], settings["tool"]["flet"]["build_number"]


def releasedBuildNumbers(tags: list[str]) -> list[int]:
    """The versionCodes of earlier releases, from their tags (gym-v0.3-alpha → 3)."""
    numbers = []
    for tag in tags:
        match = re.fullmatch(rf"{re.escape(tagPrefix)}0\.(\d+)-alpha", tag)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def readSigningValues() -> dict[str, str]:
    """The FLET_ANDROID_SIGNING_* values, from the private signing folder."""
    if not signingEnvPath.exists():
        raise ReleaseStopped("No signing key yet: run python3 tools/makeSigningKey.py once first.")
    values = {}
    for line in signingEnvPath.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.startswith("FLET_ANDROID_SIGNING_"):
            values[name] = value
    needed = {"FLET_ANDROID_SIGNING_KEY_STORE", "FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD",
              "FLET_ANDROID_SIGNING_KEY_PASSWORD", "FLET_ANDROID_SIGNING_KEY_ALIAS"}
    if set(values) != needed or not Path(values["FLET_ANDROID_SIGNING_KEY_STORE"]).exists():
        raise ReleaseStopped(f"The signing folder looks incomplete: {signingEnvPath.parent}")
    return values


def javaEnvironment() -> dict[str, str]:
    """apksigner needs Java; on this PC that's the JDK Flet installed for Android builds (~/java/<version>),
    which isn't on the PATH."""
    jdks = sorted((Path.home() / "java").glob("*/bin/java"))
    if not jdks:
        return dict(os.environ)
    home = jdks[-1].parent.parent
    return {**os.environ, "JAVA_HOME": str(home), "PATH": f"{home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}


def certificateDigest(apk: Path) -> str:
    """The APK's signing certificate SHA-256, from Android's apksigner, as AA:BB:… like keytool shows it."""
    candidates = sorted((Path.home() / "Android" / "sdk" / "build-tools").glob("*/apksigner"))
    if not candidates:
        raise ReleaseStopped("apksigner not found (it comes with the Android SDK Flet installed).")
    result = run([str(candidates[-1]), "verify", "--print-certs", str(apk)], capture_output=True, env=javaEnvironment())
    match = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})", result.stdout)
    if result.returncode != 0 or match is None:
        raise ReleaseStopped("The APK's signature couldn't be verified.")
    digest = match.group(1).upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def step(text: str) -> None:
    print(f"\n▶ {text}")


def checksBefore(tag: str, buildNumber: int) -> None:
    step("1. Checks before building")
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise ReleaseStopped("Releases are built from main.")
    if git("status", "--porcelain"):
        raise ReleaseStopped("There are uncommitted changes.")
    git("fetch", "--quiet", "origin")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        raise ReleaseStopped("main isn't the same as on GitHub: push (or pull) first.")
    tags = git("tag", "--list", f"{tagPrefix}*").split()
    if tag in tags:
        raise ReleaseStopped(f"{tag} already exists: raise the version first.")
    if any(number >= buildNumber for number in releasedBuildNumbers(tags)):
        raise ReleaseStopped("The versionCode must be above every earlier release's.")
    print("  tests…")
    if run([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider"], capture_output=True).returncode != 0:
        raise ReleaseStopped("A test failed: run the tests to see which.")
    problems = packageGuard.checkBeforeBuild(appFolder)
    if problems:
        raise ReleaseStopped("Package guard: " + "; ".join(problems))
    print("  ✓ main, pushed, tests pass, version is new, package guard")


def build(signing: dict[str, str]) -> Path:
    step("2. Public config from .env")
    problems = makePublicConfig.writePublicConfig()
    if problems:
        raise ReleaseStopped("Public config: " + "; ".join(problems))
    print("  ✓ written (values not shown)")

    step("3. Building the signed APK and the PC view")
    for leftover in ("apk", "web", "site-packages"):  # nothing old can be checked or published by mistake
        shutil.rmtree(appFolder / "build" / leftover, ignore_errors=True)
    environment = {**os.environ, **signing}  # the signing values travel only here
    if run([str(flet), "build", "apk", "--yes"], cwd=appFolder, env=environment).returncode != 0:
        raise ReleaseStopped("The APK build failed (see its output above).")
    if run([str(flet), "build", "web", "--yes"], cwd=appFolder).returncode != 0:
        raise ReleaseStopped("The PC view build failed (see its output above).")
    apks = sorted((appFolder / "build" / "apk").glob("*.apk"))
    if len(apks) != 1:
        raise ReleaseStopped(f"Expected one APK, found {len(apks)}.")
    return apks[0]


def checksAfter(apk: Path, signing: dict[str, str]) -> None:
    step("4. Checks after building")
    problems = packageGuard.checkAfterBuild(appFolder)
    if problems:
        raise ReleaseStopped("Package guard: " + "; ".join(problems))
    passwords = {name: value.encode() for name, value in signing.items() if name.endswith("PASSWORD")}
    findings = leakScan.scan([apk, appFolder / "build" / "web"], extra=passwords)
    if findings:
        raise ReleaseStopped("Leak scan: " + "; ".join(findings))
    expected = fingerprintPath.read_text(encoding="utf-8").strip()
    if certificateDigest(apk) != expected:
        raise ReleaseStopped("The APK isn't signed with the release key (its certificate doesn't match).")
    print("  ✓ package guard, leak scan, signed with the release key")


def publishPcView(tag: str) -> None:
    """The gh-pages branch: one commit holding the PC view, the home page and the privacy policy,
    replacing the last one (P6.1)."""
    step("5b. Publishing the PC view")
    oldCommit = git("rev-parse", "origin/gh-pages")
    with tempfile.TemporaryDirectory() as folder:
        site = Path(folder) / "site"
        shutil.copytree(appFolder / "build" / "web", site)
        for page in ("about.html", "privacy.html", "driveToken.html"):  # the last for Back up now (BK1.1)
            shutil.copy(repoRoot / "site" / page, site / page)
        (site / ".nojekyll").write_text("")
        (site / ".pre-commit-config.yaml").write_text(git("show", "origin/gh-pages:.pre-commit-config.yaml") + "\n")
        findings = leakScan.scan([site])
        if findings:
            raise ReleaseStopped("Leak scan of the website: " + "; ".join(findings))
        # A separate index and work tree, so the commit holds exactly the website and nothing of main.
        environment = {**os.environ, "GIT_DIR": str(repoRoot / ".git"), "GIT_INDEX_FILE": str(Path(folder) / "index"),
                       "GIT_WORK_TREE": str(site)}
        if run(["git", "add", "--all", "--force", "."], cwd=site, env=environment, capture_output=True).returncode != 0:
            raise ReleaseStopped("Preparing the website commit failed.")
        tree = run(["git", "write-tree"], env=environment, capture_output=True).stdout.strip()
        message = (f"Publish the PC view ({tag})\n\nBuilt with flet build web (base /usefulTrash/, no CDNs); "
                   "about.html, privacy.html and driveToken.html come from site/ on main. This branch is replaced "
                   "on every update.\n")
        commit = run(["git", "commit-tree", tree, "-m", message], capture_output=True).stdout.strip()
        if not commit:
            raise ReleaseStopped("Making the website commit failed.")
    git("push", f"--force-with-lease=gh-pages:{oldCommit}", "origin", f"{commit}:refs/heads/gh-pages")
    print("  ✓ published: https://fingaerwen.github.io/usefulTrash/")


def main() -> int:
    version, buildNumber = versionInfo()
    tag = f"{tagPrefix}{version}"
    try:
        checksBefore(tag, buildNumber)
        signing = readSigningValues()
        apk = build(signing)
        checksAfter(apk, signing)
        releaseApk = appFolder / "build" / "release" / f"GymTracker-{version}.apk"
        releaseApk.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(apk, releaseApk)
        if "--buildOnly" in sys.argv:
            print(f"\n✅ Built and checked: {releaseApk.relative_to(repoRoot)}. Nothing was tagged or published.")
            return 0

        step("5. Tagging and publishing")
        git("tag", "-a", tag, "-m", f"Gym Tracker {version}")
        git("push", "origin", tag)
        print(f"  ✓ tagged {tag}")
        cloudReady = "--cloudReady" in sys.argv
        if not cloudReady:
            answer = input("  Is the cloud upgrade for this release done (or is there none)? Type yes: ")
            cloudReady = answer.strip().lower() == "yes"
        if cloudReady:
            publishPcView(tag)
        else:
            print("  PC view NOT published. Run the cloud upgrade, then publish with this script again.")
    except ReleaseStopped as stopped:
        print(f"\n❌ Release stopped: {stopped}")
        return 1

    step("6. The rest is yours")
    print(f"  1. Open https://github.com/Fingaerwen/usefulTrash/releases/new?tag={tag}")
    print(f"  2. Title: Gym Tracker {version}. Leave \"Set as a pre-release\" OFF (Obtainium skips pre-releases).")
    print(f"  3. Drag in {releaseApk.relative_to(repoRoot)} and publish. Obtainium then updates the phone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
