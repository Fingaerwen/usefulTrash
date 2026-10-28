"""The PC view's Backup tab (4b, AM5.6), like Talon's:

    Backup     Last backup: 6 Dec 2026 (phone) · 3 days ago
               [ Back up now ]   [ Export CSV ]

The phone backs Ambrosia up to its own folder in your Google Drive every 30 days. Here Back up now does it on request
(Google's permission page opens in a second window), and Export CSV saves a copy to this PC with the readable
food.csv and days.csv. Over 60 days without a backup, a banner says so.
"""

import flet as ft

from ambrosia.screens.common import Banners, Menu, Notice
from ambrosia.screens.look import card, faint, header, label, mainButton, quiet, screen, softButton
from usefulShared.backup.backupJob import lastBackupText


@ft.component
def BackupTab(app, model):
    async def backUp(e):
        await app.backUpNow()

    async def export(e):
        await app.exportCsv()

    last = lastBackupText(list(app.state.rows.get("dietBackups", {}).values()), app.clock())
    return screen([
        header("Backup", trailing=[Menu(app)]),
        Banners(app, model), Notice(app, model),
        card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, size=28, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column([label("Last backup"), ft.Text(last, size=16, weight=ft.FontWeight.W_600)], spacing=2,
                              expand=True)], spacing=14),
            faint("The phone backs Ambrosia up to its own folder in your Google Drive every 30 days and keeps the "
                  "last 3, beside one history file that keeps everything. Talon backs up its own."),
        ], spacing=10)),
        ft.Row([mainButton("Back up now", backUp, icon=ft.Icons.BACKUP),
                softButton("Export CSV", export, icon=ft.Icons.DOWNLOAD)], wrap=True, spacing=8),
        quiet(model.backupStatus) if model.backupStatus else ft.Container(visible=False),
    ])
