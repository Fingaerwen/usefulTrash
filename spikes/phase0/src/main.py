"""Phase 0 spike: tests risky parts of the plan on a real phone.
Currently: startup time (check 8), version (check 12), picking a plan file (check 9).
More checks (sign-in, Supabase, offline queue, notifications) get added step by step."""

import time

# Measured as early as possible: the moment Python starts running this file.
pythonStartTime = time.monotonic()

import json  # noqa: E402  (imported after the timer on purpose)

import flet as ft  # noqa: E402

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

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    ft.Text("usefulTrash Phase 0", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Version: {appVersion}"),
                    ft.Text(f"Python start → screen: {pythonToScreenSec:.2f} s"),
                    ft.Divider(),
                    ft.Text("Check 9: pick a plan file", weight=ft.FontWeight.BOLD),
                    ft.FilledButton("Pick plan file", icon=ft.Icons.FOLDER_OPEN, on_click=pickPlanFile),
                    pickResultText,
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
