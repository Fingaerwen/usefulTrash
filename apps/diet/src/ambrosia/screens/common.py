"""Pieces Ambrosia's screens share: the notice line, banners, the ⋮ menu, dates in words and simple screens."""

import datetime as dt

import flet as ft

from ambrosia.model import appName
from ambrosia.screens.look import appMark, card, gap, iconButton, quiet, title

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
    """Banners at the top of any tab (4a): the bulk check's suggestion comes with gate 2."""
    if not model.banners:
        return ft.Container(visible=False)
    return ft.Column([card(ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE, size=20), ft.Text(banner, expand=True)],
                                  spacing=12), padding=14, raised=True) for banner in model.banners], spacing=8)


@ft.component
def Menu(app):
    """The ⋮ menu (4a): History on the phone (AM5.5), importing a targets file, and Problems."""
    async def importTargets(e):
        await app.pickTargetsFile()

    items = []
    if app.mode == "phone":
        items.append(ft.PopupMenuItem(content="History", icon=ft.Icons.HISTORY, on_click=lambda e: app.openHistory()))
    items += [ft.PopupMenuItem(content="Import a targets file", icon=ft.Icons.UPLOAD_FILE, on_click=importTargets),
              ft.PopupMenuItem(content="Problems", icon=ft.Icons.BUG_REPORT_OUTLINED,
                               on_click=lambda e: app.openProblems())]
    return ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="More", bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                              shape=ft.RoundedRectangleBorder(radius=14), items=items)


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
def ComingSoon(what: str):
    """A part that comes later, in a screen that scrolls (so it mustn't stretch: Flutter's grey box)."""
    return card(quiet(what, size=15))


def gapped(parts: list[ft.Control]) -> ft.Column:
    return ft.Column(parts, spacing=gap)
