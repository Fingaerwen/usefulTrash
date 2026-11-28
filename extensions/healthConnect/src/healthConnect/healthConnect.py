"""Python side of the healthConnect extension (plan HC1.1).

Each method sends a named request to the Dart side (src/flutter/health_connect), which forwards it to the Kotlin
plugin running on Android. Talon only reads: steps, active calories and total calories (active and resting)."""

import flet as ft

__all__ = ["HealthConnect"]

callTimeoutSec = 30  # reading a month of days takes well under this
askTimeoutSec = 600  # Health Connect's own screen waits for you to choose


@ft.control("HealthConnect")
class HealthConnect(ft.Service):
    """Reads Android Health Connect. Add one to the page's services, then call its methods."""

    async def status(self) -> str:
        """"available", "needsUpdate" (Health Connect wants an update first) or "unavailable"."""
        return await self._invoke_method(method_name="status", timeout=callTimeoutSec)

    async def hasPermissions(self) -> bool:
        """True when Talon may read steps and both kinds of calories."""
        return await self._invoke_method(method_name="hasPermissions", timeout=callTimeoutSec)

    async def requestPermissions(self) -> bool:
        """Opens Health Connect's screen asking for the three permissions. True when all three are allowed."""
        return await self._invoke_method(method_name="requestPermissions", timeout=askTimeoutSec)

    async def readDays(self, fromIso: str, toIso: str) -> list[dict]:
        """Each local day from fromIso to toIso (both included) as {"date", "steps", "activeKcal", "totalKcal"},
        Health Connect's totals for the day, None for what it has nothing of. Days with nothing at all may be left
        out."""
        return await self._invoke_method(method_name="readDays", arguments={"from": fromIso, "to": toIso},
                                         timeout=callTimeoutSec)
