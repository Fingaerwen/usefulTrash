"""The Targets tab and importing a targets file (apps/diet/docs/plan.md 4a, 4f): the file in effect, today's
targets for training and rest days, water, the bulk check's start and the changes applied. And before an
import, the new file next to the current targets, or its problems in plain words."""

import flet as ft

from ambrosia.rules.targets import DayTargets
from ambrosia.screens.bulkCheck import changeText, outcomeText
from ambrosia.screens.common import Menu, Notice, backButton, dayText, shortDay
from ambrosia.screens.look import (
    card,
    faint,
    header,
    heading,
    label,
    listCard,
    listRow,
    mainButton,
    quiet,
    screen,
    softButton,
)


def _row(key: str, value: str) -> ft.Row:
    return ft.Row([quiet(key, size=14), ft.Container(expand=True), ft.Text(value, size=14, weight=ft.FontWeight.W_600)])


def dayCard(name: str, targets: DayTargets | None, note: str, waterMl: int | None = None) -> ft.Container:
    rows = [] if targets is None else [_row("kcal", f"{targets.kcal:,}"), _row("Protein", f"{targets.proteinG} g"),
                                       _row("Fat", f"{targets.fatG} g"), _row("Carbs", f"{targets.carbsG} g")]
    if waterMl:
        rows.append(_row("Water", f"{waterMl:,} ml"))
    return card(ft.Column([ft.Row([heading(name), ft.Container(expand=True), faint(note)]), *rows], spacing=8))


@ft.component
def TargetsTab(app, model):
    view = model.targets

    async def pick(e):
        await app.pickTargetsFile()

    button = softButton("Import a targets file", pick, icon=ft.Icons.UPLOAD_FILE)
    if view is None or view.name is None:
        return screen([header("Targets", trailing=[Menu(app)]), Notice(app, model),
                       card(quiet("No targets yet. Your Claude project writes a targets file "
                                  "(apps/diet/plans/targetsFormat.md). Import it here.", size=14)), button])
    def changeRow(change) -> ft.Control:
        async def undo(e):
            await app.undoChange(change.checkDate)

        return listRow(ft.Row([quiet(f"From {shortDay(change.fromDate)}", size=14), ft.Container(expand=True),
                               ft.Text(changeText(change.kcalChange, change.macro, change.macroChangeG), size=14,
                                       weight=ft.FontWeight.W_600),
                               ft.TextButton("Undo", on_click=undo, visible=change.checkDate is not None)]),
                       padding=ft.Padding.only(left=16, right=4, top=4, bottom=4))

    changes = [changeRow(change) for change in view.changes] or [listRow(_row("Changes applied", "none yet"))]
    bulk = model.bulkCheck
    check = ([listRow(_row("First block", f"from {dayText(view.firstBlockStart)}")),
              listRow(ft.Text(outcomeText(bulk), size=14)),
              listRow(_row("Next check", shortDay(bulk.nextCheck)))] if view.firstBlockStart and bulk is not None
             else [listRow(_row("Bulk check", "off in this file"))])
    return screen([
        header("Targets", f"From \"{view.name}\", imported {shortDay(view.importedAt.date())}", trailing=[Menu(app)]),
        Notice(app, model),
        dayCard("Training day", view.trainingDay, "fixed sessions, the flex day once trained", view.waterMl),
        dayCard("Rest day", view.restDay, "the other days", view.waterMl),
        label("Bulk check"),
        listCard([*check, *changes]),
        button,
    ])


@ft.component
def ImportTargetsScreen(app, model):
    checked = model.targetsCheck
    if checked is None:
        return screen([])

    async def confirm(e):
        await app.confirmTargets()

    parts: list[ft.Control] = [header("Import targets", leading=backButton(app)), Notice(app, model)]
    if checked.targets is None:
        parts += [card(ft.Column([heading("This file can't be imported"),
                                  *[ft.Text(f"• {problem}", size=14) for problem in checked.problems]], spacing=8)),
                  quiet("Ask your Claude project to fix these, then import the new file.", size=14)]
        return screen(parts)
    new, current = checked.targets, model.targets
    parts += [quiet(f"\"{new.name}\" replaces your current targets from today, with any changes applied to them.",
                    size=14)]
    if current is not None and current.name is not None:
        parts += [label("Now"), dayCard("Training day", current.trainingDay, current.name),
                  dayCard("Rest day", current.restDay, current.name)]
    parts += [label("New"), dayCard("Training day", new.trainingDay, new.name, new.waterMl),
              dayCard("Rest day", new.restDay, new.name, new.waterMl),
              faint(f"Bulk check from {dayText(new.bulkCheck.firstBlockStart)}" if new.bulkCheck
                    else "No bulk check in this file: it's off.")]
    parts += [card(ft.Text(warning, size=14), raised=True) for warning in checked.warnings]
    parts.append(mainButton("Import", confirm, icon=ft.Icons.CHECK))
    return screen(parts)
