"""The PC view's Plans tab (SC6.1), as approved:

    Plans      Active:  Push Pull Legs (v2) · since 6 Oct · 4/week
               [ Import a plan file… ]
               Earlier: Full Body (v1) · 1 Sep – 5 Oct

Switching back to an earlier plan and archiving come later; importing it again works meanwhile.
"""

import flet as ft

from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import card, header, listCard, listRow, mainButton, quiet, screen


@ft.component
def PlansTab(app, model):
    async def importFile(e):
        await app.pickPlanFile()

    lines = [listRow(ft.Text(line)) for line in model.planLines]
    return screen([
        header("Plans", trailing=[Menu(app, app.menuItems)]),
        Banners(app, model),
        Notice(app, model),
        listCard(lines) if lines else card(quiet("No plan yet.")),
        ft.Row([mainButton("Import a plan file…", importFile, icon=ft.Icons.UPLOAD_FILE)]),
    ])
