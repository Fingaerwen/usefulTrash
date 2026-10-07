"""Phase 0 spike: tests risky parts of the plan on a real phone.
Currently: startup time (check 8), version (check 12), picking a plan file (check 9),
scheduled notifications via our own weighInNotify extension (check 5).
More checks (sign-in, Supabase, offline queue, notifications) get added step by step."""

import time

# Measured as early as possible: the moment Python starts running this file.
pythonStartTime = time.monotonic()

import json  # noqa: E402  (imported after the timer on purpose)

import flet as ft  # noqa: E402
from weighInNotify import WeighInNotify  # noqa: E402

appVersion = "0.1-alpha"


def describePlan(planData: dict) -> str:
    """Returns a one-line summary of a plan: name, cycle days and exercise count."""
    cycle = planData.get("cycle", [])
    exerciseCount = sum(len(day.get("exercises", [])) for day in cycle)
    return f"{planData.get('name', '(no name)')}: {len(cycle)} cycle days, {exerciseCount} exercises"


def main(page: ft.Page):
    """Builds the single test screen."""
    page.title = "usefulTrash Phase 0"
    page.theme_mode = ft.ThemeMode.SYSTEM  # dark mode follows the phone (plan G1)

    # Time from Python starting to the first screen being built.
    pythonToScreenSec = time.monotonic() - pythonStartTime

    # Check 9: the phone's file picker. Services register themselves with the page in Flet 1.0.
    filePicker = ft.FilePicker()
    pickResultText = ft.Text("No file picked yet")

    async def pickPlanFile(e):
        """Opens the phone's file picker, reads the chosen JSON file and shows a summary."""
        # with_data=True returns the file's bytes; on Android a plain file path isn't always available.
        files = await filePicker.pick_files(
            dialog_title="Pick a plan JSON file",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
            with_data=True,
        )
        if not files:
            pickResultText.value = "Picking cancelled"
        else:
            picked = files[0]
            try:
                planData = json.loads(picked.bytes.decode("utf-8"))
                pickResultText.value = f"✅ Read {picked.name} ({picked.size} bytes)\n{describePlan(planData)}"
            except Exception as err:  # broken file: show the error instead of crashing
                pickResultText.value = f"❌ Could not read {picked.name}: {err}"
        page.update()

    # Check 5: scheduled notifications through our own Android plugin.
    notifier = WeighInNotify()
    notifyResultText = ft.Text("Notifications not tested yet")

    def showResult(message: str):
        """Shows the outcome of a notification test under the buttons."""
        notifyResultText.value = message
        page.update()

    async def allowNotifications(e):
        """Asks Android for notification permission."""
        allowed = await notifier.requestPermission()
        showResult("✅ Notifications allowed" if allowed else "❌ Notifications NOT allowed")

    async def showNow(e):
        """Shows a test notification right away."""
        shown = await notifier.showNow("usefulTrash test", "Notifications work 🎉")
        showResult("✅ Shown now: check the notification shade" if shown else "❌ Not shown: allow notifications first")

    async def scheduleIn60(e):
        """Schedules a test notification 60 seconds from now (close the app to test it fires anyway)."""
        plannedAt = await notifier.scheduleInSeconds(60, "usefulTrash test", "Scheduled 60 s ago: alarms work ⏰")
        showResult(f"⏰ Planned for {plannedAt}: close the app and lock the phone")

    async def scheduleFriday(e):
        """Sets the real weekly weigh-in reminder: Friday 07:00 (plan G9.1 + 16.1a)."""
        nextAt = await notifier.scheduleWeekly(
            5, 7, 0, "Weekly weigh-in", "Same day, morning, after toilet, before food."
        )
        showResult(f"📅 Weekly reminder set. Next: {nextAt}")

    async def showStatus(e):
        """Shows permission, exact-alarm and next-reminder status."""
        showResult(f"Status: {await notifier.getStatus()}")

    page.add(
        ft.SafeArea(
            ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("usefulTrash Phase 0", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Version: {appVersion}"),
                    ft.Text(f"Python start → screen: {pythonToScreenSec:.2f} s"),
                    ft.Divider(),
                    ft.Text("Check 9: pick a plan file", weight=ft.FontWeight.BOLD),
                    ft.FilledButton("Pick plan file", icon=ft.Icons.FOLDER_OPEN, on_click=pickPlanFile),
                    pickResultText,
                    ft.Divider(),
                    ft.Text("Check 5: notifications", weight=ft.FontWeight.BOLD),
                    ft.FilledButton("1. Allow notifications", on_click=allowNotifications),
                    ft.FilledButton("2. Show one now", on_click=showNow),
                    ft.FilledButton("3. Schedule one in 60 s", on_click=scheduleIn60),
                    ft.FilledButton("4. Set Friday 07:00 reminder", on_click=scheduleFriday),
                    ft.OutlinedButton("Status", on_click=showStatus),
                    notifyResultText,
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
