"""Makes Gym Tracker's release signing key, once (plan 12b, "Signing key"; G3a, F20).

The key file and a random password go straight into a private folder outside the repo that only you
can read; the password is never shown, never typed and never on a command line (keytool gets it through
the environment). The certificate's name holds no personal details ("CN=Gym Tracker"), because anyone
can read it from the APK. At the end it prints the certificate's public fingerprints: the SHA-1 one is
what Google Cloud asks for when you add the Android sign-in client, and the SHA-256 one is saved in the
repo so the release script can check every APK was signed with this key.

Refuses to run if the key already exists: a release key is never replaced (the phone would refuse the
update). Afterwards, copy the whole folder to your second drive.

Usage (from the repo root): python3 tools/makeSigningKey.py
"""

import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[1]
signingFolder = Path.home() / ".local" / "share" / "usefulTrash" / "signing"
keystorePath = signingFolder / "gymTracker.jks"
signingEnvPath = signingFolder / "signing.env"  # the values Flet's Android build reads (FLET_ANDROID_SIGNING_*)
fingerprintPath = repoRoot / "apps" / "gym" / "signingCertificate.txt"  # public: SHA-256 of the certificate
alias = "upload"  # Flet's default key alias


def findKeytool() -> str | None:
    """Java's keytool: on the PATH, or in the JDK Flet installed for Android builds (~/java/<version>)."""
    found = shutil.which("keytool")
    if found:
        return found
    candidates = sorted((Path.home() / "java").glob("*/bin/keytool"))
    return str(candidates[-1]) if candidates else None


def fingerprints(listing: str) -> dict[str, str]:
    """The SHA-1 and SHA-256 fingerprints from `keytool -list -v` output."""
    found = {}
    for kind in ("SHA1", "SHA256"):
        match = re.search(rf"{kind}:\s*([0-9A-F]{{2}}(?::[0-9A-F]{{2}})+)", listing)
        if match:
            found[kind] = match.group(1)
    return found


def main() -> int:
    if keystorePath.exists() or signingEnvPath.exists():
        print(f"❌ A signing key already exists in {signingFolder}. A release key is never replaced.")
        return 1
    keytool = findKeytool()
    if keytool is None:
        print("❌ keytool not found (it comes with Java; Flet installs one into ~/java for Android builds).")
        return 1

    signingFolder.mkdir(parents=True, exist_ok=True)
    os.chmod(signingFolder, stat.S_IRWXU)  # 700: only you
    password = secrets.token_urlsafe(32)  # 256 random bits; never printed
    environment = {**os.environ, "USEFULTRASH_SIGNING_PASSWORD": password}
    made = subprocess.run(
        [keytool, "-genkeypair", "-keystore", str(keystorePath), "-storetype", "PKCS12", "-alias", alias,
         "-keyalg", "RSA", "-keysize", "4096", "-validity", "10000", "-dname", "CN=Gym Tracker",
         "-storepass:env", "USEFULTRASH_SIGNING_PASSWORD", "-keypass:env", "USEFULTRASH_SIGNING_PASSWORD"],
        env=environment, capture_output=True, text=True)
    if made.returncode != 0:
        print(f"❌ keytool couldn't make the key (exit {made.returncode}). Nothing was saved.")
        keystorePath.unlink(missing_ok=True)
        return 1
    os.chmod(keystorePath, stat.S_IRUSR | stat.S_IWUSR)  # 600

    # The values Flet's Android build reads, kept next to the key: the release script loads them into the
    # build's environment only (they're never typed, so they never reach the shell's history, F20).
    descriptor = os.open(signingEnvPath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(f"FLET_ANDROID_SIGNING_KEY_STORE={keystorePath}\n"
                   f"FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD={password}\n"
                   f"FLET_ANDROID_SIGNING_KEY_PASSWORD={password}\n"
                   f"FLET_ANDROID_SIGNING_KEY_ALIAS={alias}\n")

    listing = subprocess.run([keytool, "-list", "-v", "-keystore", str(keystorePath), "-alias", alias,
                              "-storepass:env", "USEFULTRASH_SIGNING_PASSWORD"],
                             env=environment, capture_output=True, text=True)
    found = fingerprints(listing.stdout)
    if set(found) != {"SHA1", "SHA256"}:
        print("❌ The key was made, but its fingerprints couldn't be read. Ask me to look into it.")
        return 1
    fingerprintPath.write_text(found["SHA256"] + "\n", encoding="utf-8")
    print(f"✅ Release key made in {signingFolder} (key file + password file, readable only by you).")
    print(f"   Certificate SHA-1 (for Google Cloud's Android client): {found['SHA1']}")
    print(f"   Certificate SHA-256 (saved in {fingerprintPath.relative_to(repoRoot)}): {found['SHA256']}")
    print("   Next: copy that whole folder to your second drive (G3a).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
