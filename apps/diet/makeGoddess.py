"""Renders Ambrosia's goddess (plan AM7.3) from apps/diet/art/goddess.svg to src/assets/goddess.webp, the image
behind every screen. The SVG is drawn for the app (no outside art): a stylized anime-style profile in pink and
gold. Rendered by headless Chromium (Flutter's SVG support lacks masks), at 1.5× for a sharp phone screen.

Usage (on the PC, from the repo root, with a Python that has Playwright and its Chromium):
  <python> apps/diet/makeGoddess.py
"""

import asyncio
import io
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

folder = Path(__file__).resolve().parent
svgPath = folder / "art" / "goddess.svg"
outputPath = folder / "src" / "assets" / "goddess.webp"
width, height, scale = 600, 900, 1.5


async def render() -> bytes:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        await page.set_content(f"<html><body style='margin:0'>{svgPath.read_text()}</body></html>")
        png = await page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()
    return png


if __name__ == "__main__":
    image = Image.open(io.BytesIO(asyncio.run(render()))).convert("RGBA")
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    image.save(outputPath, "WEBP", quality=80, method=6)
    print(f"{outputPath.name}: {image.width}×{image.height}, {outputPath.stat().st_size / 1024:.0f} KB")
