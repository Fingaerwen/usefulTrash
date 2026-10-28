"""Pieces Ambrosia's screens share: the notice line, banners, the ⋮ menu, dates in words, and the simple screens
(starting, signing in, the first download, Problems, failed)."""

import datetime as dt

import flet as ft

from ambrosia.model import appName
from ambrosia.screens.look import appMark, card, gap, header, iconButton, mainButton, quiet, screen, title

weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def dayText(date: dt.date) -> str:
    """ "Monday 26 Oct" """
    return f"{weekdays[date.weekday()]} {date.day} {months[date.month - 1]}"


def shortDay(date: dt.date) -> str:
    """ "Mon 26 Oct" """
    return f"{weekdays[date.weekday()][:3]} {date.day} {months[date.month - 1]}"


def kcalText(kcal: float) -> str:
    return f"{kcal:,.0f} kcal"


@ft.component
def Notice(app, model):
    """A message shown once (a refused entry, a lookup that failed), with × to close it."""
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
    """Banners at the top of any tab (12d, 18.4a): not synced, refused changes, an update needed, and in the PC view
    an old backup, which opens the Backup tab. The bulk check's suggestion has its own card (BulkCheckBanner)."""
    if not model.banners:
        return ft.Container(visible=False)
    return ft.Column([card(ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE, size=20), ft.Text(banner, expand=True)],
                                  spacing=12), padding=14, raised=True, tooltip=banner,
                           on_click=lambda e, banner=banner: app.openBanner(banner))
                      for banner in model.banners], spacing=8)


@ft.component
def Menu(app):
    """The ⋮ menu (4a): History on the phone (AM5.5), importing a targets file, Problems and Sign out."""
    async def importTargets(e):
        await app.pickTargetsFile()

    async def signOut(e):
        await app.signOut()

    entries = {
        "history": ft.PopupMenuItem(content="History", icon=ft.Icons.HISTORY, on_click=lambda e: app.openHistory()),
        "importTargets": ft.PopupMenuItem(content="Import a targets file", icon=ft.Icons.UPLOAD_FILE,
                                          on_click=importTargets),
        "problems": ft.PopupMenuItem(content="Problems", icon=ft.Icons.BUG_REPORT_OUTLINED,
                                     on_click=lambda e: app.openProblems()),
        "signOut": ft.PopupMenuItem(content="Sign out", icon=ft.Icons.LOGOUT, on_click=signOut),
    }
    return ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="More", bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                              shape=ft.RoundedRectangleBorder(radius=14),
                              items=[entries[name] for name in app.menuItems if name in entries])


def backButton(app) -> ft.IconButton:
    return iconButton(ft.Icons.ARROW_BACK, "Back", lambda e: app.back())


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
    """Sign in with Google (AU1c), the same account as Talon. The phone shows Google's account picker."""
    async def signIn(e):
        await app.signIn()

    return centred([
        appMark(88), title(appName),
        quiet("What you eat, against your targets.", size=15, style=ft.TextStyle(shadow=[
            ft.BoxShadow(blur_radius=8, color="#000000"), ft.BoxShadow(blur_radius=3, color="#000000")])),
        ft.Container(height=8),
        Notice(app, model),
        ft.Row([mainButton("Sign in with Google", signIn, icon=ft.Icons.LOGIN, disabled=bool(model.busy),
                           expand=True)]),
        quiet(model.busy) if model.busy else ft.Container(visible=False),
        ft.TextButton("Problems", on_click=lambda e: app.openProblems()),
    ])


@ft.component
def DownloadingScreen(app, model):
    """The first download (14b): everything is fetched before Today shows, with a running count."""
    async def retry(e):
        await app.firstDownload()

    rows = f"{model.downloaded:,} rows" if model.downloaded else ""
    return centred([
        appMark(),
        title(model.busy or "First download"),
        ft.Row([ft.ProgressRing(width=20, height=20, stroke_width=2.5), ft.Text(rows)], tight=True)
        if model.busy else Notice(app, model),
        mainButton("Try again", retry) if not model.busy else ft.Container(visible=False),
    ])


@ft.component
def ProblemsScreen(app, model):
    """The Problems page (12d, DG1.1): Copy puts it on the clipboard to paste to Claude. Try again sends changes the
    cloud refused once more (the phone), Clear empties the log."""
    async def copy(e):
        await app.copyProblems()

    hasRefused = any(line.startswith("Refused:") for line in model.problems)
    return screen([
        header("Problems", leading=iconButton(ft.Icons.ARROW_BACK, "Back", lambda e: app.closeProblems())),
        Notice(app, model),
        card(ft.Column([ft.Text(line, selectable=True, size=13) for line in model.problems], spacing=3)),
        ft.Row([
            mainButton("Copy", copy, icon=ft.Icons.COPY),
            ft.OutlinedButton("Try again", on_click=lambda e: app.tryRefusedAgain(), visible=hasRefused),
            ft.TextButton("Clear", on_click=lambda e: app.clearProblems()),
        ], wrap=True, spacing=8),
    ])


@ft.component
def ComingSoon(what: str):
    """A part that comes later, in a screen that scrolls (so it mustn't stretch: Flutter's grey box)."""
    return card(quiet(what, size=15))


def gapped(parts: list[ft.Control]) -> ft.Column:
    return ft.Column(parts, spacing=gap)
