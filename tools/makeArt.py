"""Renders the apps' art from SVG to transparent WebP (docs/plan.md LK1.4, apps/diet/docs/plan.md AM9): Talon's
knight, Ambrosia's goddess, her katana and her soft curves, into each app's src/assets, and copies for the start
page into site/images. The SVGs are drawn for the apps (no outside art). Rendered by headless Chromium, because
Flutter's SVG support lacks masks, at 1.5x (2x for the thin curves) for sharp phone screens.

Usage (on the PC, from the repo root, with a Python that has Playwright and its Chromium):
  <python> tools/makeArt.py
"""

import asyncio
import io
import re
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

repoRoot = Path(__file__).resolve().parents[1]
gymArt, dietArt = repoRoot / "apps" / "gym" / "art", repoRoot / "apps" / "diet" / "art"
gymAssets, dietAssets = repoRoot / "apps" / "gym" / "src" / "assets", repoRoot / "apps" / "diet" / "src" / "assets"
siteImages = repoRoot / "site" / "images"

# (the drawing, its scale, where the image goes)
pieces = (
    (gymArt / "talon.svg", 1.5, (gymAssets / "talon.webp", siteImages / "talon.webp")),
    (dietArt / "goddess.svg", 1.5, (dietAssets / "goddess.webp", siteImages / "goddess.webp")),
    (dietArt / "katana.svg", 1.5, (dietAssets / "katana.webp", siteImages / "katana.webp")),
    (dietArt / "curvesTop.svg", 2, (dietAssets / "curvesTop.webp",)),
    (dietArt / "curvesBottom.svg", 2, (dietAssets / "curvesBottom.webp",)),
)


def size(svg: str) -> tuple[int, int]:
    """The drawing's width and height, from its svg element."""
    width = re.search(r'<svg[^>]*\bwidth="(\d+)"', svg)
    height = re.search(r'<svg[^>]*\bheight="(\d+)"', svg)
    if not (width and height):
        raise ValueError("Each drawing needs width and height on its svg element.")
    return int(width.group(1)), int(height.group(1))


async def render(svg: str, scale: float) -> bytes:
    width, height = size(svg)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        await page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
        png = await page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()
    return png


def main() -> None:
    for drawing, scale, outputs in pieces:
        image = Image.open(io.BytesIO(asyncio.run(render(drawing.read_text(), scale)))).convert("RGBA")
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            image.save(output, "WEBP", quality=82, method=6)
            kilobytes = output.stat().st_size / 1024
            print(f"{output.relative_to(repoRoot)}: {image.width}x{image.height}, {kilobytes:.0f} KB")


if __name__ == "__main__":
    main()
