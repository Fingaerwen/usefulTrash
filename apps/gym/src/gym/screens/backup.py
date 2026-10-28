"""The PC view's Backup tab (SC6.1, F14.1), as approved:

    Backup     Last backup: 12 Sep (phone) · 32 days ago
               [ Back up now ]   [ Export CSV ]

The phone backs up to your Google Drive by itself every 30 days. Here Back up now does it on request
(Google's permission page opens in a second window, BK1.1), and Export CSV saves a copy to this PC with a
readable sets.csv (EX1.1). Over 60 days without a backup, a banner says so (3.4).
"""

import flet as ft

from usefulShared.backup.backupJob import lastBackupText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import card, faint, header, label, mainButton, quiet, screen, softButton


@ft.component
def BackupTab(app, model):
    async def backUp(e):
        await app.backUpNow()

    async def export(e):
        await app.exportCsv()

    last = lastBackupText(app._live("backups"), app.clock())
    return screen([
        header("Backup", trailing=[Menu(app, app.menuItems)]),
        Banners(app, model), Notice(app, model),
        card(ft.Row([ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, size=28, color=ft.Colors.ON_SURFACE_VARIANT),
                     ft.Column([label("Last backup"), ft.Text(last, size=16, weight=ft.FontWeight.W_600)], spacing=2,
                               expand=True)], spacing=14)),
        ft.Row([mainButton("Back up now", backUp, icon=ft.Icons.BACKUP),
                softButton("Export CSV", export, icon=ft.Icons.DOWNLOAD)], wrap=True, spacing=8),
        quiet(model.backupStatus) if model.backupStatus else ft.Container(visible=False),
        faint("The phone backs up to your Google Drive by itself every 30 days and keeps the last 3, beside one "
              "history file that keeps everything."),
    ])
