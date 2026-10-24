"""Tests for the plan check (tools/checkPlan.py): the import's verdict and problems, and the week as the
app will run it, moves included."""

import json
from pathlib import Path

import checkPlan

examplePlan = Path(__file__).resolve().parents[2] / "plans" / "examplePlan.json"


def testTheExamplePlanWouldBeImported(capsys):
    assert checkPlan.main([str(examplePlan)]) == 0
    shown = capsys.readouterr().out
    assert "✅ The app would import examplePlan.json." in shown
    assert "Monday: Push" in shown and "Tuesday: Rest (rest day)" in shown
    assert "the flex day: makes up the first day missed that week, in this order: Monday, Wednesday, Friday" in shown


def testMovesShowWhatChangesInTheWeek(tmp_path, capsys):
    plan = json.loads(examplePlan.read_text(encoding="utf-8"))
    friday = plan["week"][4]
    moved = friday["exercises"][0]
    plan["week"][5]["moves"] = [{"exerciseId": moved["exerciseId"], "from": "friday", "to": "saturday",
                                 "when": ["monday"]}]
    path = tmp_path / "withMove.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert checkPlan.main([str(path)]) == 0
    shown = capsys.readouterr().out
    assert (f"Saturday as Monday: Friday leaves out {moved['name']}; Saturday ends with {moved['name']} "
            "(from Friday)") in shown
    assert "Saturday as Wednesday" not in shown  # no move then: nothing changes


def testAnEstimatedBarIsShownAsOne(tmp_path, capsys):
    plan = json.loads(examplePlan.read_text(encoding="utf-8"))
    deadlift = plan["week"][2]["exercises"][0]
    shown = checkPlanOutput(plan, tmp_path, capsys)
    assert ", bar 20 kg, compound" in shown  # the plan's barKg
    del deadlift["barKg"]
    assert ", bar 20 kg (estimated), compound" in checkPlanOutput(plan, tmp_path, capsys)


def checkPlanOutput(plan, tmp_path, capsys) -> str:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert checkPlan.main([str(path)]) == 0
    return capsys.readouterr().out


def testARefusedPlanListsItsProblems(tmp_path, capsys):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"planId": "old", "name": "Old", "version": 1, "weeklyTarget": 3, "cycle": []}),
                    encoding="utf-8")
    assert checkPlan.main([str(path)]) == 1
    shown = capsys.readouterr().out
    assert "❌ The app would refuse old.json:" in shown and '"cycle" is the old format' in shown


def testAWrongCommandLine(tmp_path, capsys):
    assert checkPlan.main([]) == 2
    assert checkPlan.main([str(tmp_path / "missing.json")]) == 2
    assert "Can't read" in capsys.readouterr().out
