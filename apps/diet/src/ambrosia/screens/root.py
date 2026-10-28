"""The whole app: one screen at a time, chosen by the model. The phone's tabs are Today · Week · Targets in a bar
along the bottom (AM5.8). The PC view has Today · Week · History · Targets · Backup down the left, with the
content kept to a readable width in the middle. Everything sits on Ambrosia's backdrop (AM7.1)."""

import flet as ft

from ambrosia.screens.addFood import AddScreen, AmountScreen, LabelScreen
from ambrosia.screens.backup import BackupTab
from ambrosia.screens.common import (
    DownloadingScreen,
    FailedScreen,
    ProblemsScreen,
    SignInScreen,
    StartingScreen,
)
from ambrosia.screens.history import HistoryScreen, HistoryTab
from ambrosia.screens.look import (
    appMark,
    backdrop,
    goldEdge,
    headroom,
    indicator,
    indicatorShape,
    pagePadding,
)
from ambrosia.screens.targets import ImportTargetsScreen, TargetsTab
from ambrosia.screens.today import TodayTab
from ambrosia.screens.week import WeekTab

# (name, label, icon, icon when picked)
phoneTabs = (("today", "Today", ft.Icons.TODAY_OUTLINED, ft.Icons.TODAY),
             ("week", "Week", ft.Icons.CALENDAR_VIEW_WEEK_OUTLINED, ft.Icons.CALENDAR_VIEW_WEEK),
             ("targets", "Targets", ft.Icons.TRACK_CHANGES_OUTLINED, ft.Icons.TRACK_CHANGES))
pcTabs = (phoneTabs[0], phoneTabs[1], ("history", "History", ft.Icons.HISTORY, ft.Icons.HISTORY), phoneTabs[2],
          ("backup", "Backup", ft.Icons.BACKUP_OUTLINED, ft.Icons.BACKUP))
pcContentWidth = 960  # the PC view's content, at most this wide (two columns of meals fit)


tabScreens = {"today": TodayTab, "week": WeekTab, "targets": TargetsTab, "history": HistoryTab, "backup": BackupTab}


@ft.component
def AmbrosiaApp(app, model):
    """The root: model is passed in so every change to it redraws what it touches."""
    screens = {"starting": StartingScreen, "failed": FailedScreen, "signIn": SignInScreen,
               "downloading": DownloadingScreen, "main": PcMain if app.mode == "pc" else PhoneMain,
               "add": AddScreen, "amount": AmountScreen, "label": LabelScreen, "importTargets": ImportTargetsScreen,
               "history": HistoryScreen, "problems": ProblemsScreen}
    body = screens.get(model.screen, StartingScreen)(app, model)
    if model.screen != "main":  # the tabs bring their own margins, so their bar can reach the edges
        body = Centred(body, app.mode == "pc")
    return ft.SafeArea(backdrop(body, app.mode == "pc"), expand=True)


@ft.component
def Centred(body, wide: bool):
    """A screen with its side margins and room at the top for the katana laid across it (AM9.4). On the PC, kept
    to a readable width in the middle of the window."""
    width, setWidth = ft.use_state(0.0)
    side = max(pagePadding, (width - pcContentWidth) / 2) if wide and width else pagePadding

    def resized(e):
        if abs(e.width - width) > 1:
            setWidth(e.width)

    return ft.Container(body, expand=True, padding=ft.Padding.only(left=side, right=side, top=headroom(wide)),
                        on_size_change=resized if wide else None)


@ft.component
def PhoneMain(app, model):
    names = [name for name, _, _, _ in phoneTabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        app.selectTab(names[int(e.control.selected_index)])

    bar = ft.NavigationBar(destinations=[ft.NavigationBarDestination(icon=icon, selected_icon=picked, label=label)
                                         for _, label, icon, picked in phoneTabs],
                           selected_index=selected, on_change=switch, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                           indicator_color=indicator, indicator_shape=indicatorShape, elevation=0, height=72,
                           label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW)
    return ft.Column([Centred(tabScreens[names[selected]](app, model), False), goldEdge(), bar], spacing=0,
                     expand=True)


@ft.component
def PcMain(app, model):
    names = [name for name, _, _, _ in pcTabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        name = names[int(e.control.selected_index)]
        if name == "history":
            app.openHistory()
        else:
            app.selectTab(name)

    rail = ft.NavigationRail(destinations=[ft.NavigationRailDestination(icon=icon, selected_icon=picked, label=label)
                                           for _, label, icon, picked in pcTabs],
                             selected_index=selected, on_change=switch, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                             indicator_color=indicator, indicator_shape=indicatorShape,
                             label_type=ft.NavigationRailLabelType.ALL, min_width=88,
                             group_alignment=-0.85,
                             leading=ft.Container(appMark(44), padding=ft.Padding.only(top=12, bottom=8)))
    return ft.Row([rail, goldEdge(vertical=True), Centred(tabScreens[names[selected]](app, model), True)], spacing=0,
                  expand=True)
