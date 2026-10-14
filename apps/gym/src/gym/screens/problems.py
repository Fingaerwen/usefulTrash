"""The Problems page (plan 12d, DG1.1): version, sync status, refused changes, the log check and recent
problems in plain words with the technical line underneath. Copy puts the whole report on the
clipboard for you to paste to me; Clear empties the log. Nothing is ever sent anywhere by itself."""

import flet as ft

from gym.screens.common import Notice
from gym.screens.look import gap, title


@ft.component
def ProblemsScreen(app, model):
    async def copy(e):
        await app.copyProblems()

    hasRefused = any(line.startswith("Refused:") for line in model.problems)
    return ft.Column([
        ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=lambda e: app.closeProblems()),
                title("Problems")]),
        Notice(app, model),
        ft.Column([ft.Text(line, selectable=True, size=13) for line in model.problems], spacing=2),
        ft.Row([
            ft.Button("Copy", icon=ft.Icons.COPY, on_click=copy),
            ft.OutlinedButton("Try again", on_click=lambda e: app.tryRefusedAgain(), visible=hasRefused),
            ft.TextButton("Clear", on_click=lambda e: app.clearProblems()),
        ], wrap=True),
    ], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)
