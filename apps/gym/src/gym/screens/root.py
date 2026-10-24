"""The whole app: one screen at a time, chosen by the model (sign-in, first download, the tabs,
Problems, plan import). The phone's tabs are Today · Progress · Week · Weight (18.1); the PC view has
Today · Progress · Week · Plans (SC6.1). The Weight tab comes in a later version."""

import flet as ft

from gym.screens.common import (
    ComingSoon,
    DownloadingScreen,
    FailedScreen,
    SignInScreen,
    StartingScreen,
)
from gym.screens.importPlan import ImportPlanScreen
from gym.screens.plans import PlansTab
from gym.screens.problems import ProblemsScreen
from gym.screens.progress import ProgressTab
from gym.screens.today import TodayTab
from gym.screens.week import WeekTab

phoneTabs = (("today", "Today", ft.Icons.TODAY), ("progress", "Progress", ft.Icons.SHOW_CHART),
             ("week", "Week", ft.Icons.CALENDAR_VIEW_WEEK), ("weight", "Weight", ft.Icons.MONITOR_WEIGHT))
pcTabs = (("today", "Today", ft.Icons.TODAY), ("progress", "Progress", ft.Icons.SHOW_CHART),
          ("week", "Week", ft.Icons.CALENDAR_VIEW_WEEK), ("plans", "Plans", ft.Icons.LIST_ALT))
tabScreens = {"today": TodayTab, "progress": ProgressTab, "week": WeekTab, "plans": PlansTab}


@ft.component
def GymApp(app, model):
    """The root: model is passed in so every change to it redraws what it touches."""
    screens = {"starting": StartingScreen, "failed": FailedScreen, "signIn": SignInScreen,
               "downloading": DownloadingScreen, "main": PcMain if app.mode == "pc" else PhoneMain,
               "problems": ProblemsScreen, "importPlan": ImportPlanScreen}
    screen = screens.get(model.screen, StartingScreen)
    return ft.SafeArea(ft.Container(screen(app, model), padding=12, expand=True), expand=True)


@ft.component
def PhoneMain(app, model):
    """The phone's tabs, with the bottom bar (18.1)."""
    return Tabbed(app, model, phoneTabs)


@ft.component
def PcMain(app, model):
    """The PC view's tabs (SC6.1)."""
    return Tabbed(app, model, pcTabs)


@ft.component
def Tabbed(app, model, tabs):
    names = [name for name, _, _ in tabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        app.model.tab = names[int(e.control.selected_index)]

    name = names[selected]
    screen = tabScreens.get(name)
    body = screen(app, model) if screen else ComingSoon(tabs[selected][1])
    bar = ft.NavigationBar(destinations=[ft.NavigationBarDestination(icon=icon, label=label)
                                         for _, label, icon in tabs],
                           selected_index=selected, on_change=switch)
    return ft.Column([ft.Container(body, expand=True), bar], spacing=0, expand=True)
