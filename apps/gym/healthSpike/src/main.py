"""Talon's Health Connect spike (plan HC1.1): Health Connect's status, its permission screen, and the last 7 days
of steps, active calories and total calories as Talon would read them. Shows the raw numbers, rounded nothing, so
we can compare them with OHealth."""

import datetime as dt

import flet as ft
from healthConnect import HealthConnect


def main(page: ft.Page):
    page.title = "Talon health spike"
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = ft.ScrollMode.AUTO
    health = HealthConnect()
    lines = ft.Column([], spacing=6)
    status = ft.Text("Status: …")

    def show(text: str) -> None:
        lines.controls.append(ft.Text(text, selectable=True))
        page.update()

    async def check(e=None):
        try:
            state = await health.status()
            allowed = await health.hasPermissions() if state == "available" else False
            status.value = f"Status: {state} · allowed: {allowed}"
        except Exception as problem:
            status.value = f"Status failed: {type(problem).__name__}: {problem}"
        page.update()

    async def ask(e):
        try:
            show(f"Asked: {await health.requestPermissions()}")
        except Exception as problem:
            show(f"Asking failed: {type(problem).__name__}: {problem}")
        await check()

    async def read(e):
        today = dt.date.today()
        try:
            days = await health.readDays((today - dt.timedelta(days=6)).isoformat(), today.isoformat())
            show(f"Read at {dt.datetime.now():%H:%M:%S}, {len(days)} day(s):")
            for day in days:
                show(f"  {day.get('date')}: steps {day.get('steps')} · active {day.get('activeKcal')} · "
                     f"total {day.get('totalKcal')}")
        except Exception as problem:
            show(f"Reading failed: {type(problem).__name__}: {problem}")

    page.add(ft.Text("Talon health spike", size=22, weight=ft.FontWeight.BOLD), status,
             ft.Row([ft.Button("Ask Health Connect", on_click=ask), ft.Button("Read 7 days", on_click=read)],
                    wrap=True),
             lines)
    page.run_task(check)


if __name__ == "__main__":
    ft.run(main)
