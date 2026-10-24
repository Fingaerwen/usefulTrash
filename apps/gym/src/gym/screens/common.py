"""Pieces several screens share: the notice line, the banners (18.4a), the ⋮ menu and simple screens."""

import flet as ft

from gym.model import appName
from gym.screens.look import gap, quiet, title


@ft.component
def Notice(app, model):
    """A message shown once (a refused entry, a sign-in problem), with × to close it."""
    if not model.notice:
        return ft.Container(visible=False)

    def close(e):
        app.model.notice = ""

    return ft.Container(
        ft.Row([ft.Text(model.notice, expand=True), ft.IconButton(ft.Icons.CLOSE, tooltip="Close", on_click=close)]),
        border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=8, padding=ft.Padding.only(left=12))


@ft.component
def Banners(model):
    """Banners at the top of any tab (18.4a): not synced, refused changes, update needed."""
    if not model.banners:
        return ft.Container(visible=False)
    return ft.Column([ft.Container(ft.Text(banner), border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=8,
                                   padding=10) for banner in model.banners], spacing=gap)


@ft.component
def Menu(app, items: tuple[str, ...] = ("problems", "deload", "importPlan", "signOut")):
    """The ⋮ menu (SC2.1): Problems and Sign out; starting or stopping a deload by hand (WD2.4), hidden while
    an automatic one runs; the phone also gets "Import a plan file" (G2b-2)."""
    async def importPlan(e):
        await app.pickPlanFile()

    async def signOut(e):
        await app.signOut()

    async def startDeload(e):
        await app.startDeload()

    async def stopDeload(e):
        await app.stopDeload()

    entries = {
        "problems": ft.PopupMenuItem(content="Problems", on_click=lambda e: app.openProblems()),
        "importPlan": ft.PopupMenuItem(content="Import a plan file", on_click=importPlan),
        "signOut": ft.PopupMenuItem(content="Sign out", on_click=signOut),
    }
    if app.model.deloadAction == "start":
        entries["deload"] = ft.PopupMenuItem(content="Start a deload", on_click=startDeload)
    elif app.model.deloadAction == "stop":
        entries["deload"] = ft.PopupMenuItem(content="Stop the deload", on_click=stopDeload)
    return ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="More",
                              items=[entries[name] for name in items if name in entries])


@ft.component
def StartingScreen(app, model):
    return ft.Column([title(appName), ft.ProgressRing()], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                     alignment=ft.MainAxisAlignment.CENTER, expand=True)


@ft.component
def FailedScreen(app, model):
    return ft.Column([title(appName), ft.Text(model.failure),
                      ft.TextButton("Problems", on_click=lambda e: app.openProblems())], spacing=16)


@ft.component
def SignInScreen(app, model):
    """Sign in with Google (AU1c); the phone shows Google's account picker."""
    async def signIn(e):
        await app.signIn()

    return ft.Column([
        title(appName),
        Notice(app, model),
        ft.Button("Sign in with Google", icon=ft.Icons.LOGIN, on_click=signIn, disabled=bool(model.busy)),
        quiet(model.busy) if model.busy else ft.Container(visible=False),
        ft.TextButton("Problems", on_click=lambda e: app.openProblems()),
    ], spacing=16)


@ft.component
def DownloadingScreen(app, model):
    """First download (14b): everything is fetched before Today shows, with a running count."""
    async def retry(e):
        await app.firstDownload()

    rows = f"{model.downloaded:,} rows" if model.downloaded else ""
    return ft.Column([
        title("Downloading your data…" if model.busy else "First download"),
        ft.Row([ft.ProgressRing(width=20, height=20), ft.Text(rows)]) if model.busy else Notice(app, model),
        ft.Button("Try again", on_click=retry) if not model.busy else ft.Container(visible=False),
    ], spacing=16)


@ft.component
def ComingSoon(what: str):
    return ft.Column([quiet(f"{what} comes in a later version.")], expand=True)
