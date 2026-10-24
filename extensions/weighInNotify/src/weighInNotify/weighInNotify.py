"""Python side of the weighInNotify extension.

Each method sends a named request to the Dart side (src/flutter/weigh_in_notify),
which forwards it to the Kotlin plugin running on Android."""

import flet as ft

__all__ = ["WeighInNotify"]


@ft.control("WeighInNotify")
class WeighInNotify(ft.Service):
    """Schedules and shows local notifications on Android. Add one to the page, then call its methods."""

    async def requestPermission(self) -> bool:
        """Asks the user to allow notifications (needed on Android 13+). Returns True if allowed."""
        return await self._invoke_method(method_name="requestPermission")

    async def showNow(self, title: str, body: str) -> bool:
        """Shows a notification immediately (quick test that notifications work at all)."""
        return await self._invoke_method(method_name="showNow", arguments={"title": title, "body": body})

    async def scheduleInSeconds(self, seconds: int, title: str, body: str) -> str:
        """Shows a one-off notification after `seconds`, even if the app is closed. Returns the planned time."""
        return await self._invoke_method(
            method_name="scheduleInSeconds",
            arguments={"seconds": seconds, "title": title, "body": body},
        )

    async def scheduleWeekly(self, isoWeekday: int, hour: int, minute: int, title: str, body: str) -> str:
        """Repeats a notification every week. isoWeekday: 1 = Monday … 7 = Sunday (Friday = 5).
        Survives app restarts, phone reboots and app updates. Returns the next planned time."""
        return await self._invoke_method(
            method_name="scheduleWeekly",
            arguments={"isoWeekday": isoWeekday, "hour": hour, "minute": minute, "title": title, "body": body},
        )

    async def cancelWeekly(self) -> bool:
        """Stops the weekly notification."""
        return await self._invoke_method(method_name="cancelWeekly")

    async def scheduleDaily(self, hour: int, minute: int, title: str, body: str) -> str:
        """Repeats a notification every day at hour:minute (its own slot, apart from the weekly one).
        Survives app restarts, phone reboots and app updates. Returns the next planned time."""
        return await self._invoke_method(
            method_name="scheduleDaily", arguments={"hour": hour, "minute": minute, "title": title, "body": body})

    async def cancelDaily(self) -> bool:
        """Stops the daily notification."""
        return await self._invoke_method(method_name="cancelDaily")

    async def getStatus(self) -> dict:
        """Returns permission state, exact-alarm ability and the next planned weekly time (for debugging)."""
        return await self._invoke_method(method_name="getStatus")
