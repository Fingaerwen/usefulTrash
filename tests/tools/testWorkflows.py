"""Checks on the GitHub workflows (plan 12): no third-party actions, the least permissions, no secrets,
and the public values only through variables passed in the environment, never written into a command."""

from pathlib import Path

import yaml

workflows = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml"))


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def testThereIsTheDailyPing():
    assert [path.name for path in workflows] == ["dailyPing.yml"]


def testNoThirdPartyActions():
    for path in workflows:
        for job in load(path)["jobs"].values():
            assert all("uses" not in step for step in job["steps"]), path.name


def testLeastPermissions():
    for path in workflows:
        assert load(path)["permissions"] == {"actions": "write"}, path.name


def testNoSecretsAndNoValuesInCommands():
    for path in workflows:
        text = path.read_text()
        assert "secrets." not in text, path.name
        for job in load(path)["jobs"].values():
            for step in job["steps"]:
                assert "${{" not in step["run"], f"{path.name}: expressions go through env, never into the command"


def testThePingRunsDailyAndCanBeStartedByHand():
    triggers = load(workflows[0])[True]  # YAML reads the key "on" as True
    assert triggers["schedule"] == [{"cron": "17 6 * * *"}] and "workflow_dispatch" in triggers


def testKeepAliveRunsEvenWhenThePingFails():
    keepAlive = load(workflows[0])["jobs"]["ping"]["steps"][1]
    assert keepAlive["if"] == "always()"
