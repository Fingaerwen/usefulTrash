"""Gym Tracker: starts the app and picks phone or PC mode once (plan 3b, CS1.1).

Phone (the APK): the phone's database, sync, phone sign-in. PC view (the website): the cloud store and
the browser's Google sign-in. Nothing else in the app asks "am I a website?".
"""

import time

startedAt = time.monotonic()  # as early as possible: the cold start (under 5 s, check 8) is measured from here

import json  # noqa: E402  (imported after the timer on purpose)
import os  # noqa: E402
from pathlib import Path  # noqa: E402

import flet as ft  # noqa: E402

from gym.model import appName  # noqa: E402
from gym.screens.look import darkTheme, lightTheme  # noqa: E402
from gym.screens.root import GymApp  # noqa: E402
from usefulShared.platform.appLog import AppLog  # noqa: E402


def loadPublicConfig() -> dict:
    """The three public identifiers (K2a: Supabase address, publishable key, Google client ID), written
    into the app by tools/makePublicConfig.py before a build. Empty if the file is missing."""
    try:
        return json.loads(Path(__file__).with_name("publicConfig.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class _PhoneServices:
    """The phone's abilities: our extensions and Flet's services (created once, inside the page)."""

    def __init__(self):
        from nativeGoogleSignIn import NativeGoogleSignIn
        from secureStore import SecureStore

        self.googleSignIn = NativeGoogleSignIn()
        self.secretStore = SecureStore()
        self.clipboard = ft.Clipboard()
        self.filePicker = ft.FilePicker()


def main(page: ft.Page):
    page.title = appName
    page.theme_mode = ft.ThemeMode.SYSTEM  # dark mode follows the phone (G1)
    page.theme, page.dark_theme = lightTheme(), darkTheme()
    config = loadPublicConfig()

    if page.web:
        from gym.pcApp import PcApp, PcServices

        log = AppLog(None)  # memory only: nothing is stored in the browser (12d)
        app = PcApp(config, PcServices(), log)
    else:
        from gym.phoneApp import PhoneApp

        folder = os.getenv("FLET_APP_STORAGE_DATA") or os.getcwd()  # the app's private storage
        log = AppLog(folder)
        app = PhoneApp(config, folder, _PhoneServices(), log)

    def onError(e):
        """An unexpected error in a screen: written down before anything else (12d)."""
        log.problem("app", "Something went wrong unexpectedly.", str(e.data)[:500])

    def onLifecycle(e):
        if e.state in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            app.onResume()

    page.on_error = onError
    page.on_app_lifecycle_state_change = onLifecycle
    page.render(GymApp, app, app.model)

    async def startUp():
        try:
            await app.start()
        except Exception as problem:  # the app must still show something, and say why
            log.crash(problem, "start")
            app.model.failure = "The app couldn't start. Details are on the Problems page."
            app.model.screen = "failed"
            return
        app.startedIn = time.monotonic() - startedAt
        log.info("start", f"ready in {app.startedIn:.1f} s")

    page.run_task(startUp)


if __name__ == "__main__":
    ft.run(main)
