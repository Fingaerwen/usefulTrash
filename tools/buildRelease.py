"""Builds a release of Talon or Ambrosia, or both at once (the joint release), with every check before and after (plan
12b, RL3, apps/diet/docs/plan.md 4c, 4h):

1. Checks: on main, nothing uncommitted, everything pushed, all tests pass, each version is new (no tag for it yet,
   versionCode above the app's last release), and the package guard (CS1.1).
2. Writes the public config from .env into each app (tools/makePublicConfig.py).
3. Builds each signed APK and PC view. The signing values come from the private signing folder
   (tools/makeSigningKey.py) and reach the build through its environment only: never typed, never on a
   command line, never printed (F20, checked in Flet 1.0.3: its logs never show the environment). One release key
   signs both apps.
4. Checks after: the package guard and the leak scan on each build (secret formats, private .env values,
   the signing password), and each APK's signing certificate must match apps/gym/signingCertificate.txt.
5. Tags each version. Then, once you confirm any cloud upgrade for this release is done (14c), publishes the site
   to the gh-pages branch as one commit replacing the last (P6.1, 4c): the start page as its index, about.html,
   privacy.html and driveToken.html at the top, and both PC views, /talon/ and /ambrosia/. An app that isn't in
   this release keeps the PC view it has there.
6. Tells you the rest: the GitHub releases (made by you, on the website: no GitHub token anywhere) and
   Obtainium.

Usage (from the repo root): python3 tools/buildRelease.py talon|ambrosia [talon|ambrosia] [--cloudReady | --buildOnly]
  --cloudReady: you've already confirmed the cloud upgrade for this release is done (or there is none).
  --buildOnly: steps 1 to 4 only, a trial run: nothing is tagged or published.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import leakScan
import makePublicConfig
import packageGuard

repoRoot = Path(__file__).resolve().parents[1]
python = repoRoot / ".venv" / "bin" / "python"
flet = repoRoot / ".venv" / "bin" / "flet"
signingEnvPath = Path.home() / ".local" / "share" / "usefulTrash" / "signing" / "signing.env"
fingerprintPath = repoRoot / "apps" / "gym" / "signingCertificate.txt"  # the release key's, for both apps
siteAddress = "https://fingaerwen.github.io/usefulTrash/"
sitePages = ("about.html", "privacy.html", "driveToken.html")  # at the addresses Google has registered (4c)


@dataclass(frozen=True, slots=True)
class App:
    """One app the script releases."""

    key: str  # what the command line says
    title: str  # release titles and APK names: "Talon 0.4-alpha", Talon-0.4-alpha.apk
    folder: Path
    tagPrefix: str  # one repo, several apps: tags say which app
    sitePath: str  # its PC view's folder on the site

    @property
    def configPath(self) -> Path:
        return self.folder / "src" / "publicConfig.json"


apps = {
    # Talon keeps Gym Tracker's gym-v tags (AM1.4), so its versions carry on from 0.3-alpha
    "talon": App("talon", "Talon", repoRoot / "apps" / "gym", "gym-v", "talon"),
    "ambrosia": App("ambrosia", "Ambrosia", repoRoot / "apps" / "diet", "ambrosia-v", "ambrosia"),
}


class ReleaseStopped(Exception):
    """A check failed. The message says which, in plain words."""


def run(command: list[str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=options.pop("cwd", repoRoot), text=options.pop("text", True), **options)


def git(*arguments: str) -> str:
    result = run(["git", *arguments], capture_output=True)
    if result.returncode != 0:
        raise ReleaseStopped(f"git {arguments[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def versionInfo(app: App) -> tuple[str, int]:
    settings = tomllib.loads((app.folder / "pyproject.toml").read_text(encoding="utf-8"))
    return settings["project"]["version"], settings["tool"]["flet"]["build_number"]


def releasedBuildNumbers(tags: list[str], tagPrefix: str) -> list[int]:
    """The versionCodes of an app's earlier releases, from their tags (gym-v0.3-alpha → 3)."""
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
    """apksigner needs Java. On this PC that's the JDK Flet installed for Android builds (~/java/<version>),
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


def checksBefore(releases: list[tuple[App, str, int]]) -> None:
    step("1. Checks before building")
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise ReleaseStopped("Releases are built from main.")
    if git("status", "--porcelain"):
        raise ReleaseStopped("There are uncommitted changes.")
    git("fetch", "--quiet", "origin")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        raise ReleaseStopped("main isn't the same as on GitHub: push (or pull) first.")
    for app, tag, buildNumber in releases:
        tags = git("tag", "--list", f"{app.tagPrefix}*").split()
        if tag in tags:
            raise ReleaseStopped(f"{tag} already exists: raise {app.title}'s version first.")
        if any(number >= buildNumber for number in releasedBuildNumbers(tags, app.tagPrefix)):
            raise ReleaseStopped(f"{app.title}'s versionCode must be above every earlier release's.")
        problems = packageGuard.checkBeforeBuild(app.folder)
        if problems:
            raise ReleaseStopped(f"Package guard ({app.title}): " + "; ".join(problems))
    print("  tests…")
    if run([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider"], capture_output=True).returncode != 0:
        raise ReleaseStopped("A test failed: run the tests to see which.")
    print("  ✓ main, pushed, tests pass, versions are new, package guard")


def build(app: App, signing: dict[str, str]) -> Path:
    step(f"2. {app.title}: public config from .env")
    problems = makePublicConfig.writePublicConfig(app.configPath)
    if problems:
        raise ReleaseStopped("Public config: " + "; ".join(problems))
    print("  ✓ written (values not shown)")

    step(f"3. {app.title}: building the signed APK and the PC view")
    for leftover in ("apk", "web", "site-packages"):  # nothing old can be checked or published by mistake
        shutil.rmtree(app.folder / "build" / leftover, ignore_errors=True)
    environment = {**os.environ, **signing}  # the signing values travel only here
    if run([str(flet), "build", "apk", "--yes"], cwd=app.folder, env=environment).returncode != 0:
        raise ReleaseStopped(f"{app.title}'s APK build failed (see its output above).")
    if run([str(flet), "build", "web", "--yes"], cwd=app.folder).returncode != 0:
        raise ReleaseStopped(f"{app.title}'s PC view build failed (see its output above).")
    apks = sorted((app.folder / "build" / "apk").glob("*.apk"))
    if len(apks) != 1:
        raise ReleaseStopped(f"Expected one APK for {app.title}, found {len(apks)}.")
    return apks[0]


def checksAfter(app: App, apk: Path, signing: dict[str, str]) -> None:
    step(f"4. {app.title}: checks after building")
    problems = packageGuard.checkAfterBuild(app.folder)
    if problems:
        raise ReleaseStopped("Package guard: " + "; ".join(problems))
    passwords = {name: value.encode() for name, value in signing.items() if name.endswith("PASSWORD")}
    findings = leakScan.scan([apk, app.folder / "build" / "web"], extra=passwords)
    if findings:
        raise ReleaseStopped("Leak scan: " + "; ".join(findings))
    expected = fingerprintPath.read_text(encoding="utf-8").strip()
    if certificateDigest(apk) != expected:
        raise ReleaseStopped("The APK isn't signed with the release key (its certificate doesn't match).")
    print("  ✓ package guard, leak scan, signed with the release key")


# --- The site (P6.1, 4c) ------------------------------------------------------------------------

def assembleSite(site: Path, pcViews: Mapping[str, Path]) -> None:
    """The site's files in a fresh folder: the start page as index.html with its images, the pages Google knows at
    their addresses, and each PC view in its own folder (pcViews: its folder name → the build to copy)."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.copy(repoRoot / "site" / "start.html", site / "index.html")
    shutil.copytree(repoRoot / "site" / "images", site / "images")
    for page in sitePages:
        shutil.copy(repoRoot / "site" / page, site / page)
    for name, web in pcViews.items():
        shutil.copytree(web, site / name)
    (site / ".nojekyll").write_text("")


def publishedPcView(app: App, into: Path) -> bool:
    """Copies the PC view the site has now for an app that isn't in this release. False if there's none yet."""
    if not git("ls-tree", "-d", "origin/gh-pages", app.sitePath):
        return False
    archive = run(["git", "archive", "--format=tar", "origin/gh-pages", app.sitePath], capture_output=True, text=False)
    if archive.returncode != 0:
        raise ReleaseStopped(f"Reading {app.title}'s published PC view failed.")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
        bundle.extractall(into, filter="data")
    return True


def publishSite(built: list[App], tags: list[str]) -> None:
    """The gh-pages branch: one commit holding the whole site, replacing the last one (P6.1)."""
    step("5b. Publishing the site")
    oldCommit = git("rev-parse", "origin/gh-pages")
    with tempfile.TemporaryDirectory() as folder:
        kept = Path(folder) / "kept"
        pcViews = {app.sitePath: app.folder / "build" / "web" for app in built}
        for app in apps.values():
            if app not in built:
                if publishedPcView(app, kept):
                    pcViews[app.sitePath] = kept / app.sitePath
                    print(f"  {app.title}'s PC view stays as it's published")
                else:
                    print(f"  {app.title} has no PC view on the site yet: its link on the start page waits for it")
        site = Path(folder) / "site"
        assembleSite(site, pcViews)
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
        message = (f"Publish the site ({', '.join(tags)})\n\nThe start page, about.html, privacy.html and "
                   "driveToken.html from site/ on main, and the PC views built with flet build web (no CDNs) at "
                   "/usefulTrash/talon/ and /usefulTrash/ambrosia/. This branch is replaced on every update.\n")
        commit = run(["git", "commit-tree", tree, "-m", message], capture_output=True).stdout.strip()
        if not commit:
            raise ReleaseStopped("Making the website commit failed.")
    git("push", f"--force-with-lease=gh-pages:{oldCommit}", "origin", f"{commit}:refs/heads/gh-pages")
    print(f"  ✓ published: {siteAddress}")


def chosenApps(arguments: list[str]) -> list[App]:
    """The apps named on the command line, Talon first. At least one, each once."""
    names = [argument for argument in arguments if not argument.startswith("--")]
    if not names or any(name not in apps for name in names) or len(set(names)) != len(names):
        raise ReleaseStopped("Name the app: python3 tools/buildRelease.py talon|ambrosia [talon|ambrosia] "
                             "[--cloudReady | --buildOnly]")
    return [app for app in apps.values() if app.key in names]


def main() -> int:
    try:
        chosen = chosenApps(sys.argv[1:])
        releases = []
        for app in chosen:
            version, buildNumber = versionInfo(app)
            releases.append((app, f"{app.tagPrefix}{version}", buildNumber))
        checksBefore(releases)
        signing = readSigningValues()
        releaseApks = {}
        for app, _, _ in releases:
            apk = build(app, signing)
            checksAfter(app, apk, signing)
            releaseApk = app.folder / "build" / "release" / f"{app.title}-{versionInfo(app)[0]}.apk"
            releaseApk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(apk, releaseApk)
            releaseApks[app.key] = releaseApk
        if "--buildOnly" in sys.argv:
            names = ", ".join(str(path.relative_to(repoRoot)) for path in releaseApks.values())
            print(f"\n✅ Built and checked: {names}. Nothing was tagged or published.")
            return 0

        step("5. Tagging and publishing")
        for app, tag, _ in releases:
            git("tag", "-a", tag, "-m", f"{app.title} {versionInfo(app)[0]}")
            git("push", "origin", tag)
            print(f"  ✓ tagged {tag}")
        cloudReady = "--cloudReady" in sys.argv
        if not cloudReady:
            answer = input("  Is the cloud upgrade for this release done (or is there none)? Type yes: ")
            cloudReady = answer.strip().lower() == "yes"
        if cloudReady:
            publishSite(chosen, [tag for _, tag, _ in releases])
        else:
            print("  Site NOT published. Run the cloud upgrade, then publish with this script again.")
    except ReleaseStopped as stopped:
        print(f"\n❌ Release stopped: {stopped}")
        return 1

    step("6. The rest is yours")
    for app, tag, _ in releases:
        version = versionInfo(app)[0]
        print(f"  {app.title}: open https://github.com/Fingaerwen/usefulTrash/releases/new?tag={tag}")
        print(f"    Title: {app.title} {version}. Leave \"Set as a pre-release\" OFF (Obtainium skips pre-releases).")
        print(f"    Drag in {releaseApks[app.key].relative_to(repoRoot)} and publish. Obtainium then updates the phone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
