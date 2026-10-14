"""The PC view's Plans tab (SC6.1), as approved:

    Plans      Active:  Push Pull Legs (v2) · since 6 Oct · 4/week
               [ Import a plan file… ]
               Earlier: Full Body (v1) · 1 Sep – 5 Oct

Switching back to an earlier plan and archiving come later; importing it again works meanwhile.
"""

import flet as ft

from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, title


@ft.component
def PlansTab(app, model):
    async def importFile(e):
        await app.pickPlanFile()

    return ft.Column([
        ft.Row([ft.Container(title("Plans"), expand=True), Menu(app, app.menuItems)]),
        Banners(model),
        Notice(app, model),
        *[ft.Text(line) for line in model.planLines],
        ft.Button("Import a plan file…", icon=ft.Icons.UPLOAD_FILE, on_click=importFile),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)
