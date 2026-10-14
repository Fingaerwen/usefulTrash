"""The whole app: one screen at a time, chosen by the model (sign-in, first download, the tabs,
Problems, plan import). The phone's tabs are Today · Progress · Week · Weight (18.1)."""

import flet as ft

from gym.screens.common import (
    ComingSoon,
    DownloadingScreen,
    FailedScreen,
    SignInScreen,
    StartingScreen,
)
from gym.screens.importPlan import ImportPlanScreen
from gym.screens.problems import ProblemsScreen
from gym.screens.today import TodayTab

phoneTabs = (("today", "Today", ft.Icons.TODAY), ("progress", "Progress", ft.Icons.SHOW_CHART),
             ("week", "Week", ft.Icons.CALENDAR_VIEW_WEEK), ("weight", "Weight", ft.Icons.MONITOR_WEIGHT))


@ft.component
def GymApp(app, model):
    """The root: model is passed in so every change to it redraws what it touches."""
    screens = {"starting": StartingScreen, "failed": FailedScreen, "signIn": SignInScreen,
               "downloading": DownloadingScreen, "main": PhoneMain, "problems": ProblemsScreen,
               "importPlan": ImportPlanScreen}
    screen = screens.get(model.screen, StartingScreen)
    return ft.SafeArea(ft.Container(screen(app, model), padding=12, expand=True), expand=True)


@ft.component
def PhoneMain(app, model):
    """The tabs, with the bottom bar."""
    names = [name for name, _, _ in phoneTabs]
    selected = names.index(model.tab) if model.tab in names else 0

    def switch(e):
        app.model.tab = names[int(e.control.selected_index)]

    body = TodayTab(app, model) if names[selected] == "today" else ComingSoon(phoneTabs[selected][1])
    bar = ft.NavigationBar(destinations=[ft.NavigationBarDestination(icon=icon, label=label)
                                         for _, label, icon in phoneTabs],
                           selected_index=selected, on_change=switch)
    return ft.Column([ft.Container(body, expand=True), bar], spacing=0, expand=True)
