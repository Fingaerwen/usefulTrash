"""Tests for the public config writer (tools/makePublicConfig.py, K2a): exactly three public values, checked,
and anything secret-looking refused without ever repeating it. Fake values are built while the tests run,
so nothing key-shaped is in this file."""

import makePublicConfig

fakeUrl = "https://" + "abcdefghij" + ".supabase.co"
fakeKey = "sb_" + "publishable_" + "x" * 20
fakeClientId = "123-abc" + ".apps.googleusercontent.com"


def envText(**values) -> str:
    defaults = {"SUPABASE_URL": fakeUrl, "SUPABASE_PUBLISHABLE_KEY": fakeKey, "GOOGLE_WEB_CLIENT_ID": fakeClientId}
    defaults.update(values)
    return "# comment\n" + "\n".join(f"{name}={value}" for name, value in defaults.items()) + "\nOTHER=ignored\n"


def testOnlyTheThreePublicValuesAreCopied():
    config, problems = makePublicConfig.buildConfig(envText())
    assert problems == []
    assert config == {"supabaseUrl": fakeUrl, "supabasePublishableKey": fakeKey, "googleWebClientId": fakeClientId}


def testASecretLookingValueIsRefusedWithoutRepeatingIt():
    adminLookalike = "sb_" + "secret_" + "y" * 20
    config, problems = makePublicConfig.buildConfig(envText(SUPABASE_PUBLISHABLE_KEY=adminLookalike))
    assert problems == ["SUPABASE_PUBLISHABLE_KEY looks like a SECRET. Remove it from .env. The app must never contain it."]
    assert "supabasePublishableKey" not in config
    assert adminLookalike not in "".join(problems)


def testMissingAndMalformedValues():
    _, problems = makePublicConfig.buildConfig(envText(SUPABASE_URL="", GOOGLE_WEB_CLIENT_ID="not an id"))
    assert problems == ["SUPABASE_URL is missing or empty in .env",
                        "GOOGLE_WEB_CLIENT_ID doesn't look right (expected <numbers>-<letters>.apps.googleusercontent.com)"]


def testTheOutputFileIsIgnoredByGit():
    from pathlib import Path
    import subprocess
    repoRoot = Path(__file__).resolve().parents[2]
    result = subprocess.run(["git", "check-ignore", "-q", "apps/gym/src/publicConfig.json"], cwd=repoRoot)
    assert result.returncode == 0
