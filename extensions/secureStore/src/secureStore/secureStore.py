"""Python side of the secureStore extension.

Each method sends a named request to the Dart side (src/flutter/secure_store), which forwards it to the
Kotlin plugin. Values are encrypted on Android with a key that never leaves Android Keystore (plan T1.1).
This module never prints, logs or caches values."""

import flet as ft

__all__ = ["SecureStore"]

callTimeoutSec = 30  # every Android path replies; this only guards against a reply that never arrives


@ft.control("SecureStore")
class SecureStore(ft.Service):
    """Encrypted key-value storage for small secrets. Create one (services register themselves with the page).
    Item names: letters, digits, "_" and "-", up to 64 characters."""

    async def save(self, name: str, value: str) -> dict:
        """Encrypts and saves value under name, replacing what was there.
        Returns {"status": "ok"} or {"status": "error", "errorType": ..., "message": ...}."""
        return await self._invoke_method(
            method_name="save", arguments={"name": name, "value": value}, timeout=callTimeoutSec
        )

    async def load(self, name: str) -> dict:
        """Returns {"status": "ok", "value": ...}, {"status": "missing"},
        {"status": "unreadable", "message": ...} (can't be decrypted, e.g. the key was lost; the item is deleted)
        or {"status": "error", ...}."""
        return await self._invoke_method(method_name="load", arguments={"name": name}, timeout=callTimeoutSec)

    async def delete(self, name: str) -> dict:
        """Deletes the item (fine if it doesn't exist). Returns {"status": "ok"} or an error."""
        return await self._invoke_method(method_name="delete", arguments={"name": name}, timeout=callTimeoutSec)

    async def info(self) -> dict:
        """Where the key lives (e.g. "secure hardware (TEE)" or "StrongBox chip") and how many items are stored."""
        return await self._invoke_method(method_name="info", timeout=callTimeoutSec)
