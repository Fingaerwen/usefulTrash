"""Importing a plan file (plan 10, SC6.1): problems listed in plain words (G8a) → "is this the same
exercise?" for likely matches (11.3) → choose the starting step (17.2c) → it takes effect.
The same screen serves the PC view's Plans tab and the phone's fallback (G2b-2)."""

import flet as ft

from gym.screens.look import gap, quiet, title


@ft.component
def ImportPlanScreen(app, model):
    flow = model.planImport
    if flow is None:
        return ft.Column([])
    back = ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Cancel", on_click=lambda e: app.closePlanImport()),
                   title("Import a plan"), quiet(flow.fileName)])
    warnings = [quiet(f"Note: {warning}") for warning in flow.warnings]
    if flow.step == "problems":
        body = [ft.Text("This plan can't be imported. Fix these in the file (or paste them to whoever wrote it):"),
                *[ft.Text(f"• {error}", selectable=True) for error in flow.errors], *warnings]
    elif flow.step == "questions":
        body = [*warnings, SameExerciseQuestions(app, flow, key=flow.fileName)]
    else:
        body = [*warnings, StartStepChoice(app, flow, key=flow.fileName)]
    return ft.Column([back, *body], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def SameExerciseQuestions(app, flow):
    """One question per likely match; you answer each, nothing is assumed."""
    answers, setAnswers = ft.use_state({})

    def answer(index: int, value: str):
        setAnswers({**answers, index: value == "yes"})

    rows = []
    for index, question in enumerate(flow.questions):
        rows.append(ft.Text(f"Is “{question.newName}” the same exercise as “{question.knownName}” from your "
                            "earlier plans? Yes keeps its history."))
        rows.append(ft.RadioGroup(content=ft.Row([ft.Radio(value="yes", label="Yes"), ft.Radio(value="no", label="No")]),
                                  value=None if index not in answers else ("yes" if answers[index] else "no"),
                                  on_change=lambda e, i=index: answer(i, e.control.value)))
    allAnswered = len(answers) == len(flow.questions)
    return ft.Column([*rows, ft.Button("Continue", disabled=not allAnswered,
                                       on_click=lambda e: app.answerPlanQuestions(
                                           [answers[i] for i in range(len(flow.questions))]))], spacing=gap)


@ft.component
def StartStepChoice(app, flow):
    """You choose the step the plan starts on (17.2c); it takes effect today, or tomorrow if a workout is
    already logged today (PF1)."""
    chosen, setChosen = ft.use_state("0")

    async def finish(e):
        await app.finishPlanImport(int(chosen))

    when = "today" if flow.takesEffect == app.localToday() else "tomorrow"
    plan = flow.plan
    return ft.Column([
        ft.Text(f"{plan.name} (v{plan.version}) · {len(plan.steps)} steps · {plan.weeklyTarget} workouts a week"),
        ft.Text("Start on:"),
        ft.RadioGroup(content=ft.Column([ft.Radio(value=str(index), label=f"{index + 1} · {stepTitle}")
                                         for index, stepTitle in enumerate(flow.stepTitles)]),
                      value=chosen, on_change=lambda e: setChosen(e.control.value)),
        quiet(f"It takes effect {when}."),
        ft.Button("Import", icon=ft.Icons.CHECK, on_click=finish),
    ], spacing=gap)
