"""The PC view's Backup tab (SC6.1, F14.1), as approved:

    Backup     Last backup: 12 Sep (phone) · 32 days ago
               [ Back up now ]   [ Export CSV ]

The phone backs up to your Google Drive by itself every 30 days; here Back up now does it on request
(Google's permission page opens in a second window, BK1.1), and Export CSV saves a copy to this PC with a
readable sets.csv (EX1.1). Over 60 days without a backup, a banner says so (3.4).
"""

import flet as ft

from gym.rules.stats import lastBackupText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, title


@ft.component
def BackupTab(app, model):
    async def backUp(e):
        await app.backUpNow()

    async def export(e):
        await app.exportCsv()

    last = lastBackupText(app._live("backups"), app.clock())
    return ft.Column([
        ft.Row([ft.Container(title("Backup"), expand=True), Menu(app, app.menuItems)]),
        Banners(app, model), Notice(app, model), ft.Divider(),
        ft.Text(f"Last backup: {last}"),
        ft.Row([ft.Button("Back up now", icon=ft.Icons.BACKUP, on_click=backUp),
                ft.OutlinedButton("Export CSV", icon=ft.Icons.DOWNLOAD, on_click=export)], wrap=True),
        quiet(model.backupStatus) if model.backupStatus else ft.Container(visible=False),
        quiet("The phone backs up to your Google Drive by itself every 30 days and keeps the last 3."),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)
