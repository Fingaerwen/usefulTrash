"""The PC view's Plans tab (SC6.1), as approved, with Switch and Archive (SW1.1, SW1.2):

    Plans      Active:  Push Pull Legs (v2) · since 6 Oct · 4/week
               [ Import a plan file… ]
               Earlier: Full Body (v1) · 1 Sep – 5 Oct   [Switch] [Archive]
               Archived (1) ▸                                     a fold, each line with [Unarchive]

Switch asks first ("Switch to Full Body (v1) from today?"), then imports that plan again from today, or tomorrow
if you've logged a workout today. Archive only tucks a plan into the Archived fold: its weeks still count.
"""

import flet as ft

from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import card, header, label, listCard, listRow, mainButton, pill, quiet, screen, softButton


@ft.component
def PlansTab(app, model):
    showArchived, setShowArchived = ft.use_state(False)

    async def importFile(e):
        await app.pickPlanFile()

    entries = model.planEntries or ()
    shown = [entry for entry in entries if entry.kind != "archived"]
    archived = [entry for entry in entries if entry.kind == "archived"]
    parts = [header("Plans", trailing=[Menu(app, app.menuItems)]), Banners(app, model), Notice(app, model)]
    if model.planSwitch is not None:
        parts.append(SwitchQuestion(app, model.planSwitch))
    parts.append(listCard([PlanRow(app, entry) for entry in shown]) if shown else card(quiet("No plan yet.")))
    parts.append(ft.Row([mainButton("Import a plan file…", importFile, icon=ft.Icons.UPLOAD_FILE)]))
    if archived:
        fold = ft.Icons.EXPAND_LESS if showArchived else ft.Icons.EXPAND_MORE
        parts.append(ft.Row([label(f"Archived ({len(archived)})"),
                             ft.IconButton(fold, icon_size=20, tooltip="Hide archived plans" if showArchived
                                           else "Show archived plans",
                                           on_click=lambda e: setShowArchived(not showArchived))],
                            spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if showArchived:
            parts.append(listCard([PlanRow(app, entry) for entry in archived]))
    return screen(parts)


def PlanRow(app, entry) -> ft.Control:
    """One plan: its line, and for an earlier one Switch and Archive, for an archived one Unarchive."""
    async def archive(e):
        await app.setArchived(entry, True)

    async def unarchive(e):
        await app.setArchived(entry, False)

    actions = []
    if entry.kind == "earlier":
        actions = [pill("Switch", on_click=lambda e: app.askSwitch(entry), tooltip=f"Switch back to {entry.name}"),
                   pill("Archive", on_click=archive, tooltip=f"Archive {entry.name}")]
    elif entry.kind == "archived":
        actions = [pill("Unarchive", on_click=unarchive, tooltip=f"Unarchive {entry.name}")]
    return listRow(ft.Row([ft.Text(entry.text, expand=True), *actions], spacing=6,
                          vertical_alignment=ft.CrossAxisAlignment.CENTER))


def SwitchQuestion(app, asked) -> ft.Control:
    """Switch asks first, since it changes what Today shows (SW1.1)."""
    async def switch(e):
        await app.confirmSwitch()

    return card(ft.Column([
        ft.Text(asked.question, weight=ft.FontWeight.W_600),
        quiet("Your weights carry on from what you've logged. The plan's earlier weeks stay in History."),
        ft.Row([mainButton("Switch", switch), softButton("Cancel", lambda e: app.cancelSwitch())], spacing=8),
    ], spacing=10), raised=True)
