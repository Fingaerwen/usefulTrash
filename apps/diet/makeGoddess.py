"""Makes Ambrosia's goddess (plan AM7.1): the background figure behind every screen, src/assets/goddess.webp.

From the Metropolitan Museum of Art's photo of a "Marble head of a goddess" (Hellenistic, 2nd–1st century BCE,
object 256431, https://www.metmuseum.org/art/collection/search/256431), public domain under the Met's Open
Access policy (CC0): its dark backdrop and pale floor are cut away by brightness and a soft oval around the
head and neck, then it's coloured from deep pink through pink to gold and saved as a WebP with transparency.

Usage (on the PC, from the repo root; the photo is the object's primaryImage, downloaded separately):
  python3 -I apps/diet/makeGoddess.py <DP328155.jpg>
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

outputPath = Path(__file__).resolve().parent / "src" / "assets" / "goddess.webp"
height = 900  # pixels, before cropping to the head and neck
# Brightness to colour: deep pink in the shadows, pink, then gold on the lit stone.
colourStops = [(0, (40, 6, 26)), (90, (150, 22, 90)), (160, (255, 79, 163)), (215, (245, 196, 81)),
               (255, (255, 236, 180))]


def colourAt(brightness: int) -> tuple[int, int, int]:
    for (low, lowColour), (high, highColour) in zip(colourStops, colourStops[1:]):
        if brightness <= high:
            share = (brightness - low) / (high - low)
            return tuple(round(a + (b - a) * share) for a, b in zip(lowColour, highColour))
    return colourStops[-1][1]


def makeGoddess(photoPath: Path) -> Image.Image:
    photo = Image.open(photoPath).convert("L")
    photo = photo.resize((round(photo.width * height / photo.height), height), Image.LANCZOS)
    light = ImageOps.autocontrast(photo, cutoff=1).filter(ImageFilter.GaussianBlur(0.9))
    # The backdrop is dark grey: anything darker than the stone fades out, softly.
    alpha = light.point(lambda v: 0 if v < 70 else 255 if v > 125 else int((v - 70) / 55 * 255))
    alpha = alpha.filter(ImageFilter.GaussianBlur(2))
    # Only the head and neck: a soft oval around them, so the pale floor and the stand fade out.
    width = alpha.width
    centreX, centreY, radiusX, radiusY = 0.49 * width, 0.40 * height, 0.29 * width, 0.405 * height
    oval = Image.new("L", (width, height))
    oval.putdata([max(0, min(255, int((1 - (((x - centreX) / radiusX) ** 2 + ((y - centreY) / radiusY) ** 2) ** 0.5)
                                      / 0.12 * 255)))
                  for y in range(height) for x in range(width)])
    alpha = ImageChops.multiply(alpha, oval)
    table = [colourAt(value) for value in range(256)]
    coloured = Image.merge("RGB", [light.point([colour[channel] for colour in table]) for channel in range(3)])
    coloured.putalpha(alpha)
    return coloured.crop(alpha.point(lambda v: 255 if v > 20 else 0).getbbox())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    goddess = makeGoddess(Path(sys.argv[1]))
    goddess.save(outputPath, "WEBP", quality=70, method=6)
    print(f"{outputPath.name}: {goddess.width}×{goddess.height}, {outputPath.stat().st_size / 1024:.0f} KB")
