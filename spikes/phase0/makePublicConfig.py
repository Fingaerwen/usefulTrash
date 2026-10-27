"""Copies the public identifiers the app needs from the repo's .env into src/publicConfig.json. Run it before `flet build`.

Only three names are copied, the ones the plan allows inside the app (K2a: public by design):
SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and GOOGLE_WEB_CLIENT_ID. Each value must have the expected format,
and anything that looks like a secret is refused. The output file is git-ignored, and values are never printed.

Usage (from the repo root): python3 spikes/phase0/makePublicConfig.py"""

import json
import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[2]
envPath = repoRoot / ".env"
outputPath = Path(__file__).resolve().parent / "src" / "publicConfig.json"

# .env name → (name in publicConfig.json, format check, what the check expects)
allowedValues = {
    "SUPABASE_URL": (
        "supabaseUrl",
        lambda value: value.startswith("https://") and value.rstrip("/").endswith(".supabase.co"),
        "https://<project>.supabase.co",
    ),
    "SUPABASE_PUBLISHABLE_KEY": (
        "supabasePublishableKey",
        lambda value: value.startswith("sb_publishable_"),
        "sb_publishable_...",
    ),
    "GOOGLE_WEB_CLIENT_ID": (
        "googleWebClientId",
        lambda value: value.endswith(".apps.googleusercontent.com") and " " not in value,
        "<numbers>-<letters>.apps.googleusercontent.com",
    ),
}

# Formats that must never end up in the app (Supabase secret key, Google client secret, private keys).
secretMarkers = ("sb_secret_", "GOCSPX-", "PRIVATE KEY")


def readEnv(envText: str) -> dict[str, str]:
    """Parses NAME=value lines from .env text (comments and blank lines skipped, surrounding quotes removed)."""
    values = {}
    for line in envText.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def buildConfig(envText: str) -> tuple[dict[str, str], list[str]]:
    """Returns (config, problems). The config holds only the allowed public values. Problems name
    every missing, malformed or secret-looking value (by variable name only, never the value)."""
    envValues = readEnv(envText)
    config, problems = {}, []
    for envName, (configName, isValid, expected) in allowedValues.items():
        value = envValues.get(envName, "")
        if any(marker in value for marker in secretMarkers):
            problems.append(f"{envName} looks like a SECRET. Remove it from .env; the app must never contain it.")
        elif not value:
            problems.append(f"{envName} is missing or empty in .env")
        elif not isValid(value):
            problems.append(f"{envName} doesn't look right (expected {expected})")
        else:
            config[configName] = value
    return config, problems


def main() -> int:
    """Writes src/publicConfig.json, or explains what's wrong and writes nothing."""
    if not envPath.exists():
        print(f"❌ No .env found at {envPath}. Copy .env.example to .env and fill it in.")
        return 1
    config, problems = buildConfig(envPath.read_text(encoding="utf-8"))
    if problems:
        print("❌ publicConfig.json NOT written:")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    outputPath.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"✅ Wrote {outputPath.relative_to(repoRoot)} with: {', '.join(sorted(config))} (values not shown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
