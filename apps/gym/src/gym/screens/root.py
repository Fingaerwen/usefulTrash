"""The whole app: one screen at a time, chosen by the model (sign-in, first download, the tabs,
Problems, plan import). The phone's tabs are Today · Progress · Charts · Week · Weight (18.1, SC8.1) in a bar
along the bottom; the PC view has the same and History, Plans and Backup (SC6.1) down the left, with the
content kept to a phone-like width in the middle so lines stay easy to read (LK1.2)."""

import flet as ft

from gym.screens.backup import BackupTab
from gym.screens.charts import ChartsTab
from gym.screens.common import (
    ComingSoon,
    DownloadingScreen,
    FailedScreen,
    SignInScreen,
    StartingScreen,
    appMark,
)
from gym.screens.history import HistoryScreen, HistoryTab
from gym.screens.importPlan import ImportPlanScreen
from gym.screens.look import backdrop, indicator, indicatorShape, pagePadding, redEdge
from gym.screens.plans import PlansTab
from gym.screens.problems import ProblemsScreen
from gym.screens.progress import ProgressTab
from gym.screens.today import TodayTab
from gym.screens.week import WeekTab
from gym.screens.weight import WeightTab

# (name, label, icon, icon when picked)
phoneTabs = (("today", "Today", ft.Icons.TODAY_OUTLINED, ft.Icons.TODAY),
             ("progress", "Progress", ft.Icons.EMOJI_EVENTS_OUTLINED, ft.Icons.EMOJI_EVENTS),
             ("charts", "Charts", ft.Icons.SHOW_CHART, ft.Icons.SHOW_CHART),
             ("week", "Week", ft.Icons.CALENDAR_VIEW_WEEK_OUTLINED, ft.Icons.CALENDAR_VIEW_WEEK),
             ("weight", "Weight", ft.Icons.MONITOR_WEIGHT_OUTLINED, ft.Icons.MONITOR_WEIGHT))
pcTabs = (*phoneTabs, ("history", "History", ft.Icons.HISTORY, ft.Icons.HISTORY),
          ("plans", "Plans", ft.Icons.LIST_ALT_OUTLINED, ft.Icons.LIST_ALT),
          ("backup", "Backup", ft.Icons.BACKUP_OUTLINED, ft.Icons.BACKUP))
tabScreens = {"today": TodayTab, "progress": ProgressTab, "charts": ChartsTab, "week": WeekTab, "weight": WeightTab,
              "history": HistoryTab, "plans": PlansTab, "backup": BackupTab}
pcContentWidth = 720  # the PC view's content, at most this wide


@ft.component
def GymApp(app, model):
    """The root: model is passed in so every change to it redraws what it touches."""
    screens = {"starting": StartingScreen, "failed": FailedScreen, "signIn": SignInScreen,
               "downloading": DownloadingScreen, "main": PcMain if app.mode == "pc" else PhoneMain,
               "problems": ProblemsScreen, "importPlan": ImportPlanScreen, "history": HistoryScreen}
    screen = screens.get(model.screen, StartingScreen)
    body = screen(app, model)
    if model.screen != "main":  # the tabs bring their own margins, so their bar can reach the edges
        body = Centred(body, app.mode == "pc")
    return ft.SafeArea(backdrop(body, app.mode == "pc"), expand=True)


@ft.component
def Centred(body, wide: bool):
    """A screen with its side margins; on the PC, kept to a readable width in the middle of the window."""
    width, setWidth = ft.use_state(0.0)
    side = max(pagePadding, (width - pcContentWidth) / 2) if wide and width else pagePadding

    def resized(e):
        if abs(e.width - width) > 1:
            setWidth(e.width)

    return ft.Container(body, expand=True, padding=ft.Padding.only(left=side, right=side, top=8),
                        on_size_change=resized if wide else None)


@ft.component
def PhoneMain(app, model):
    """The phone's tabs, with the bar along the bottom (18.1)."""
    names = [name for name, _, _, _ in phoneTabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        app.model.tab = names[int(e.control.selected_index)]

    bar = ft.NavigationBar(destinations=[ft.NavigationBarDestination(icon=icon, selected_icon=picked, label=label)
                                         for _, label, icon, picked in phoneTabs],
                           selected_index=selected, on_change=switch, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                           indicator_color=indicator, indicator_shape=indicatorShape, elevation=0, height=72,
                           label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW)
    return ft.Column([Centred(tabBody(app, model, phoneTabs, selected), False), redEdge(), bar], spacing=0, expand=True)


@ft.component
def PcMain(app, model):
    """The PC view's tabs (SC6.1), down the left."""
    names = [name for name, _, _, _ in pcTabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        app.model.tab = names[int(e.control.selected_index)]

    rail = ft.NavigationRail(destinations=[ft.NavigationRailDestination(icon=icon, selected_icon=picked, label=label)
                                           for _, label, icon, picked in pcTabs],
                             selected_index=selected, on_change=switch, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                             indicator_color=indicator, indicator_shape=indicatorShape,
                             label_type=ft.NavigationRailLabelType.ALL, min_width=88, group_alignment=-0.85,
                             leading=ft.Container(appMark(44), padding=ft.Padding.only(top=12, bottom=8)))
    return ft.Row([rail, redEdge(vertical=True), Centred(tabBody(app, model, pcTabs, selected), True)], spacing=0,
                  expand=True)


def tabBody(app, model, tabs, selected: int) -> ft.Control:
    name = tabs[selected][0]
    screen = tabScreens.get(name)
    return screen(app, model) if screen else ComingSoon(tabs[selected][1])
