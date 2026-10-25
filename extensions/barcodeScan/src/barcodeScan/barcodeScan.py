"""Python side of the barcodeScan extension.

Each method sends a named request to the Dart side (src/flutter/barcode_scan), which forwards it to the
Kotlin plugin running on Android. Every answer is a dict with "status": "ok" (with "barcode" and
"format"), "cancelled", or "error" (with "errorType" and "message")."""

import flet as ft

__all__ = ["BarcodeScan"]


@ft.control("BarcodeScan")
class BarcodeScan(ft.Service):
    """Scans one food barcode (EAN-13, EAN-8, UPC-A, UPC-E). Add one to the page, then call a method."""

    async def scanGoogle(self) -> dict:
        """Google's code scanner, inside Google Play services: no camera permission for the app, Google's own
        scanner screen. Google's library sends Google usage metrics (device, app, timings; no images or codes)."""
        return await self._invoke_method(method_name="scanGoogle")

    async def scanOpen(self) -> dict:
        """ZXing (open source): the scanning happens in the app itself, nothing goes over the network.
        Android asks once for the camera."""
        return await self._invoke_method(method_name="scanOpen")
