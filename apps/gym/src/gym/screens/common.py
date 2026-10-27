"""Pieces several screens share: the notice line, the banners (18.4a), the ⋮ menu and simple screens."""

import flet as ft

from gym.model import appName
from gym.rules.stats import summaryBanner, weighInBanner
from gym.screens.look import card, gap, mainButton, markFill, quiet, title

bannerIcons = {summaryBanner: ft.Icons.INSIGHTS, weighInBanner: ft.Icons.MONITOR_WEIGHT_OUTLINED}


@ft.component
def Notice(app, model):
    """A message shown once (a refused entry, a sign-in problem), with × to close it."""
    if not model.notice:
        return ft.Container(visible=False)

    def close(e):
        app.model.notice = ""

    return card(ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(model.notice, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="Close", on_click=close, icon_size=20)], spacing=10),
                padding=ft.Padding.only(left=14, top=4, bottom=4, right=4), raised=True)


@ft.component
def Banners(app, model):
    """Banners at the top of any tab (18.4a): not synced, refused changes, update needed, last week's summary
    (Mondays) and the weigh-in (Fridays). Tapping one of the last two opens its tab."""
    if not model.banners:
        return ft.Container(visible=False)
    return ft.Column([
        card(ft.Row([ft.Icon(bannerIcons.get(banner, ft.Icons.ERROR_OUTLINE), size=20),
                     ft.Text(banner, expand=True, weight=ft.FontWeight.W_500),
                     ft.Icon(ft.Icons.CHEVRON_RIGHT, size=20, color=ft.Colors.OUTLINE)
                     if banner in bannerIcons else ft.Container(visible=False)], spacing=12),
             padding=14, raised=True, tooltip=banner, on_click=lambda e, banner=banner: app.openBanner(banner))
        for banner in model.banners], spacing=8)


@ft.component
def Menu(app, items: tuple[str, ...] = ("problems", "history", "deload", "importPlan", "signOut")):
    """The ⋮ menu (SC2.1): Problems and Sign out. Starting or stopping a deload by hand (WD2.4), hidden while
    an automatic one runs. The phone also gets History (HI1.1) and "Import a plan file" (G2b-2)."""
    async def importPlan(e):
        await app.pickPlanFile()

    async def signOut(e):
        await app.signOut()

    async def startDeload(e):
        await app.startDeload()

    async def stopDeload(e):
        await app.stopDeload()

    entries = {
        "history": ft.PopupMenuItem(content="History", icon=ft.Icons.HISTORY, on_click=lambda e: app.openHistory()),
        "importPlan": ft.PopupMenuItem(content="Import a plan file", icon=ft.Icons.UPLOAD_FILE, on_click=importPlan),
        "problems": ft.PopupMenuItem(content="Problems", icon=ft.Icons.BUG_REPORT_OUTLINED,
                                     on_click=lambda e: app.openProblems()),
        "signOut": ft.PopupMenuItem(content="Sign out", icon=ft.Icons.LOGOUT, on_click=signOut),
    }
    if app.model.deloadAction == "start":
        entries["deload"] = ft.PopupMenuItem(content="Start a deload", icon=ft.Icons.SELF_IMPROVEMENT,
                                             on_click=startDeload)
    elif app.model.deloadAction == "stop":
        entries["deload"] = ft.PopupMenuItem(content="Stop the deload", icon=ft.Icons.SELF_IMPROVEMENT,
                                             on_click=stopDeload)
    return ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="More", bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                              shape=ft.RoundedRectangleBorder(radius=14),
                              items=[entries[name] for name in items if name in entries])


def appMark(size: int = 72) -> ft.Container:
    """The app's sign: a dumbbell in a circle of deep red fading to grey."""
    return ft.Container(ft.Icon(ft.Icons.FITNESS_CENTER, size=size * 0.5), width=size, height=size,
                        border_radius=size / 2, gradient=markFill(), alignment=ft.Alignment.CENTER)


def centred(parts: list[ft.Control]) -> ft.Column:
    return ft.Column(parts, spacing=16, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                     alignment=ft.MainAxisAlignment.CENTER, expand=True)


@ft.component
def StartingScreen(app, model):
    return centred([appMark(), title(appName), ft.ProgressRing(width=24, height=24, stroke_width=2.5)])


@ft.component
def FailedScreen(app, model):
    return centred([appMark(), title(appName), ft.Text(model.failure, text_align=ft.TextAlign.CENTER),
                    ft.TextButton("Problems", on_click=lambda e: app.openProblems())])


@ft.component
def SignInScreen(app, model):
    """Sign in with Google (AU1c). The phone shows Google's account picker."""
    async def signIn(e):
        await app.signIn()

    return centred([
        appMark(88), title(appName),
        quiet("Your plan, your sets, your progress.", size=15),
        ft.Container(height=8),
        Notice(app, model),
        ft.Row([mainButton("Sign in with Google", signIn, icon=ft.Icons.LOGIN, disabled=bool(model.busy),
                           expand=True)]),
        quiet(model.busy) if model.busy else ft.Container(visible=False),
        ft.TextButton("Problems", on_click=lambda e: app.openProblems()),
    ])


@ft.component
def DownloadingScreen(app, model):
    """First download (14b): everything is fetched before Today shows, with a running count."""
    async def retry(e):
        await app.firstDownload()

    rows = f"{model.downloaded:,} rows" if model.downloaded else ""
    return centred([
        appMark(),
        title("Downloading your data…" if model.busy else "First download"),
        ft.Row([ft.ProgressRing(width=20, height=20, stroke_width=2.5), ft.Text(rows)], tight=True)
        if model.busy else Notice(app, model),
        mainButton("Try again", retry) if not model.busy else ft.Container(visible=False),
    ])


@ft.component
def ComingSoon(what: str):
    return ft.Column([quiet(f"{what} comes in a later version.")], expand=True)


def gapped(parts: list[ft.Control]) -> ft.Column:
    """Parts stacked with the screen's gap, not scrolling on their own (inside a screen that does)."""
    return ft.Column(parts, spacing=gap)
