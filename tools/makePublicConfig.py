"""Copies the public identifiers the apps need from the repo's .env into apps/gym/src/publicConfig.json (Talon) or
apps/diet/src/publicConfig.json (Ambrosia). Run before `flet build` (tools/buildRelease.py does it, for each app it
builds). Moved from the Phase 0 spike (CS1.1).

Only three names are copied, the ones the plan allows inside the app (K2a: public by design):
SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and GOOGLE_WEB_CLIENT_ID. Each value must have the expected
format, and anything that looks like a secret is refused. The output file is git-ignored, and values are
never printed.

Usage (from the repo root): python3 tools/makePublicConfig.py [apps/diet]
"""

import json
import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[1]
envPath = repoRoot / ".env"
outputPath = repoRoot / "apps" / "gym" / "src" / "publicConfig.json"

# .env name -> (name in publicConfig.json, format check, what the check expects)
allowedValues = {
    "SUPABASE_URL": (
        "supabaseUrl",
        lambda value: value.startswith("https://") and value.rstrip("/").endswith(".supabase.co") and " " not in value,
        "https://<project>.supabase.co",
    ),
    "SUPABASE_PUBLISHABLE_KEY": (
        "supabasePublishableKey",
        lambda value: value.startswith("sb_publishable_") and " " not in value,
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
    """Returns (config, problems). The config holds only the allowed public values. Problems name every
    missing, malformed or secret-looking value (by variable name only, never the value)."""
    envValues = readEnv(envText)
    config, problems = {}, []
    for envName, (configName, isValid, expected) in allowedValues.items():
        value = envValues.get(envName, "")
        if any(marker in value for marker in secretMarkers):
            problems.append(f"{envName} looks like a SECRET. Remove it from .env. The app must never contain it.")
        elif not value:
            problems.append(f"{envName} is missing or empty in .env")
        elif not isValid(value):
            problems.append(f"{envName} doesn't look right (expected {expected})")
        else:
            config[configName] = value
    return config, problems


def writePublicConfig(output: Path = outputPath) -> list[str]:
    """Writes publicConfig.json (Talon's unless another path is given). Returns the problems instead if there are
    any (nothing is written then)."""
    if not envPath.exists():
        return [f"No .env found at {envPath}. Copy .env.example to .env and fill it in."]
    config, problems = buildConfig(envPath.read_text(encoding="utf-8"))
    if problems:
        return problems
    output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return []


def main() -> int:
    output = repoRoot / sys.argv[1] / "src" / "publicConfig.json" if len(sys.argv) > 1 else outputPath
    problems = writePublicConfig(output)
    if problems:
        print("❌ publicConfig.json NOT written:")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print(f"✅ Wrote {output.relative_to(repoRoot)} with: {', '.join(sorted(n for n, _, _ in allowedValues.values()))} "
          "(values not shown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
