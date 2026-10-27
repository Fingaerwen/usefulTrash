"""Importing a plan file (plan 10, SC6.1): problems listed in plain words (G8a) → "is this the same
exercise?" for likely matches (11.3) → the week at a glance and Import → it takes effect. There's no
starting step to choose (WD1.1). The same screen serves the PC view's Plans tab and the phone's fallback
(G2b-2)."""

import flet as ft

from gym.rules.schedule import weekdayNames
from gym.screens.look import card, faint, gap, header, iconButton, label, listCard, listRow, mainButton, quiet, screen


@ft.component
def ImportPlanScreen(app, model):
    flow = model.planImport
    if flow is None:
        return ft.Column([])
    back = header("Import a plan", flow.fileName,
                  leading=iconButton(ft.Icons.ARROW_BACK, "Cancel", lambda e: app.closePlanImport()))
    warnings = [card(quiet(f"Note: {warning}"), padding=14) for warning in flow.warnings]
    if flow.step == "problems":
        body = [card(ft.Column([
            ft.Text("This plan can't be imported. Fix these in the file (or paste them to whoever wrote it):",
                    weight=ft.FontWeight.W_500),
            *[ft.Text(f"• {error}", selectable=True) for error in flow.errors]], spacing=8)), *warnings]
    elif flow.step == "questions":
        body = [*warnings, SameExerciseQuestions(app, flow, key=flow.fileName)]
    else:
        body = [*warnings, ReadyToImport(app, flow, key=flow.fileName)]
    return screen([back, *body])


@ft.component
def SameExerciseQuestions(app, flow):
    """One question per likely match. You answer each, nothing is assumed."""
    answers, setAnswers = ft.use_state({})

    def answer(index: int, value: str):
        setAnswers({**answers, index: value == "yes"})

    rows = []
    for index, question in enumerate(flow.questions):
        rows.append(card(ft.Column([
            ft.Text(f"Is “{question.newName}” the same exercise as “{question.knownName}” from your earlier plans? "
                    "Yes keeps its history."),
            ft.RadioGroup(content=ft.Row([ft.Radio(value="yes", label="Yes"), ft.Radio(value="no", label="No")]),
                          value=None if index not in answers else ("yes" if answers[index] else "no"),
                          on_change=lambda e, i=index: answer(i, e.control.value))], spacing=6)))
    allAnswered = len(answers) == len(flow.questions)
    return ft.Column([*rows, ft.Row([mainButton("Continue", lambda e: app.answerPlanQuestions(
        [answers[i] for i in range(len(flow.questions))]), disabled=not allAnswered, expand=True)])], spacing=gap)


@ft.component
def ReadyToImport(app, flow):
    """The plan's week at a glance, then Import: it takes effect today, or tomorrow if a workout is already
    logged today (PF1)."""
    async def finish(e):
        await app.finishPlanImport()

    when = "today" if flow.takesEffect == app.localToday() else "tomorrow"
    plan = flow.plan
    week = [listRow(ft.Row([ft.Text(weekdayNames[index][:3].capitalize(), width=44, color=ft.Colors.ON_SURFACE_VARIANT,
                                    weight=ft.FontWeight.W_600), ft.Text(step.title, expand=True)]),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10))
            for index, step in enumerate(plan.steps)]
    return ft.Column([
        card(ft.Column([ft.Text(f"{plan.name} (v{plan.version})", size=18, weight=ft.FontWeight.W_600),
                        quiet(f"{plan.weeklyTarget} workouts a week")], spacing=2)),
        label("The week"), listCard(week),
        *([label("Keeping your weights"), card(ft.Column([
            quiet("You've trained these already, so they keep your weights:"),
            *[ft.Text(f"• {line}") for line in flow.keptWeights]], spacing=4))] if flow.keptWeights else []),
        faint(f"It takes effect {when}."),
        ft.Row([mainButton("Import", finish, icon=ft.Icons.CHECK, expand=True)]),
    ], spacing=gap)
