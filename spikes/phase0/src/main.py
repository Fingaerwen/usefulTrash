"""Phase 0 spike: shows the app's startup time (check 8) and version (check 12).
More checks (sign-in, Supabase, offline queue, notifications, file picker) get added step by step."""

import time

# Measured as early as possible: the moment Python starts running this file.
pythonStartTime = time.monotonic()

import flet as ft  # noqa: E402  (imported after the timer on purpose)

appVersion = "0.1-alpha"


def main(page: ft.Page):
    """Builds the single test screen."""
    page.title = "usefulTrash Phase 0"
    page.theme_mode = ft.ThemeMode.SYSTEM  # dark mode follows the phone (plan G1)

    # Time from Python starting to the first screen being built.
    pythonToScreenSec = time.monotonic() - pythonStartTime

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    ft.Text("usefulTrash Phase 0", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Version: {appVersion}"),
                    ft.Text(f"Python start → screen: {pythonToScreenSec:.2f} s"),
                    ft.Text("Total cold start is measured from the outside with a stopwatch / adb."),
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
