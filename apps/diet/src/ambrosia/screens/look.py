"""Ambrosia's look (apps/diet/docs/plan.md AM7.1, AM9): the suite's black and shades (usefulShared.look), and the
soft half of the suite's mirrored opposites (AM9.1): round corners, a light pink that carries the glows and soft
flowing lines, and one thing sharp and lethal, gold katanas. It's Talon's backdrop mirrored and softened:
light-pink glows top right and low left, soft curves where Talon has its crisp line and slashes, and the goddess
of harmony faint behind the lower left, facing left towards Talon, with a drawn katana resting over her shoulder
and another laid across the top of every screen (AM9.3, AM9.4). Cards are see-through with a blur, fading from a
pink top-right corner. Dark only (AM9.5). Text, ticks and the main buttons are never gold or pink.
"""

import math
from functools import partial

import flet as ft

from usefulShared import look as suite
from usefulShared.look import (  # the suite's pieces, used by Ambrosia's screens through here
    Form,
    accent,
    big,
    chartFade,
    chevron,
    dot,
    faint,
    filling,
    gap,
    grow,
    hairline,
    header,
    heading,
    iconButton,
    indicator,
    label,
    listRow,
    makeTheme,
    pagePadding,
    quiet,
    screen,
    tapSize,
    title,
    track,
)

# Ambrosia's shapes (AM9.1): all four corners well rounded, the card's pink from the top right
form = Form(cut=False, corner=24, small=20, button=26, fadeFrom=ft.Alignment.TOP_RIGHT, topEdge=False)
card = partial(suite.card, form=form)
listCard = partial(suite.listCard, form=form)
statTile = partial(suite.statTile, form=form)
pill = partial(suite.pill, form=form)
segments = partial(suite.segments, form=form)
mainButton = partial(suite.mainButton, form=form)
softButton = partial(suite.softButton, form=form)
field = partial(suite.field, form=form)
markFill = partial(suite.markFill, form=form)
indicatorShape = suite.indicatorShape(form=form)

# The shades, darkest first, each leaning a little towards pink under the black and white.
darkShades = {
    "surface": "#000000",
    "surface_container_lowest": "#0A0609",
    "surface_container_low": "#1C1019",  # cards
    "surface_container": "#21131D",
    "surface_container_high": "#2D1828",  # fields, chips, raised parts in a card
    "surface_container_highest": "#3D2036",  # what's picked: a segment
    "outline_variant": "#341C2E",  # hairlines between rows
    "outline": "#6B6B6B",
    "on_surface_variant": "#A6A6A6",
    "on_surface": "#F5F5F5",
    "primary": "#FFFFFF",
    "on_primary": "#000000",
}
# Gold and pink (AM9.2), in the theme's tertiary roles: gold itself (the katanas' colour, the edge along the tab
# bar), its pale shine (on_tertiary_fixed: the edge's bright point), a soft pink (the picked tab, raised cards,
# tracks), a card's pink corner, and the glows' light pink.
darkAccents = {"tertiary": "#FFC72C", "on_tertiary": "#000000", "on_tertiary_fixed": "#FFF4B8",
               "tertiary_container": "#7A3A62", "on_tertiary_container": "#FFE3F3",
               "tertiary_fixed": "#45223D", "tertiary_fixed_dim": "#FFB0DA"}

goddessImage = "goddess.webp"  # in src/assets, made by tools/makeArt.py from apps/diet/art/goddess.svg
katanaImage = "katana.webp"  # apps/diet/art/katana.svg, lying flat, the hilt on the left
curvesTopImage, curvesBottomImage = "curvesTop.webp", "curvesBottom.webp"


def darkTheme() -> ft.Theme:
    """The one theme: Ambrosia is dark only (AM9.5)."""
    return makeTheme(darkShades, darkAccents)


def goldEdge(vertical: bool = False) -> ft.Container:
    """A razor-thin gold line along the tab bar's top (or the PC view's rail's side), with a pale shine at its
    brightest point, mirrored from Talon's red edge (65% along instead of 35%)."""
    gold, shine = ft.Colors.TERTIARY, ft.Colors.ON_TERTIARY_FIXED
    gradient = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER if vertical else ft.Alignment.CENTER_LEFT,
                                 end=ft.Alignment.BOTTOM_CENTER if vertical else ft.Alignment.CENTER_RIGHT,
                                 colors=[accent(0.12, gold), accent(0.9, gold), accent(1.0, shine), accent(0.9, gold),
                                         accent(0.12, gold)], stops=[0.0, 0.55, 0.65, 0.75, 1.0])
    return ft.Container(width=1.5 if vertical else None, height=None if vertical else 1.5, gradient=gradient)


def headroom(wide: bool) -> int:
    """Room above every screen's content for the katana laid across the top, so it never crosses the title."""
    return 60 if wide else 34


def katana(width: float, angleDegrees: float, **place) -> ft.Image:
    """A drawn katana, lying at an angle around its hilt's end (AM9.4)."""
    return ft.Image(src=katanaImage, width=width, height=width * 0.06, fit=ft.BoxFit.FILL,
                    rotate=ft.Rotate(math.radians(angleDegrees), alignment=ft.Alignment.CENTER_LEFT), **place)


def goddess(height: float, opacity: float, left: float, bottom: float) -> list[ft.Control]:
    """The goddess (AM9.3) and the katana resting over her shoulder, placed together: the katana's hilt at her
    front and its blade over her back shoulder, rising behind her to the right (the drawing is 600 by 900)."""
    scale = height / 900
    width = 783 * scale
    return [ft.Image(src=goddessImage, height=height, opacity=opacity, left=left, bottom=bottom),
            katana(width, -30, left=left + 117 * scale, bottom=bottom + 290 * scale - width * 0.03)]


def backdrop(content: ft.Control, wide: bool = False) -> ft.Control:
    """The screen's background: black, a light-pink glow over the top right and another low on the left, soft
    curves at the top right and low on the right, the goddess with her katana faint behind the lower left, and a
    second katana laid across the top, larger in the PC view (wide), clear of its rail. Nothing in it can be
    tapped; the content sits on top."""
    pink = ft.Colors.TERTIARY_FIXED_DIM
    layers: list[ft.Control] = [
        ft.Container(bgcolor=ft.Colors.SURFACE, **filling),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(0.6, -1.1), radius=1.3,
            colors=[accent(0.55, pink), accent(0.2, pink), accent(0.0, pink)], stops=[0.0, 0.42, 1.0])),
        # Washes are pink: gold spread thin over black turns brown, so gold stays sharp (the katanas, the edge).
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(-1.1, 0.95), radius=1.05, colors=[accent(0.26, pink), accent(0.0, pink)])),
        ft.Image(src=curvesTopImage, width=300, height=220, right=-30, top=-20),
        ft.Image(src=curvesBottomImage, width=260, height=130, right=-30, bottom=104),
        *(goddess(640, 0.7, 58, -40) if wide else goddess(540, 0.6, -40, 70)),
        katana(700, 1, left=38, top=-8) if wide else katana(480, 2, left=-70, top=-6),
    ]
    return ft.Stack([*layers, ft.Container(content, **filling)], expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)


def appMark(size: int = 72) -> ft.Container:
    """Ambrosia's sign: a goblet (the food of the gods was drunk too) in a circle of deep pink fading to grey."""
    return ft.Container(ft.Icon(ft.Icons.LOCAL_BAR, size=size * 0.48, color=ft.Colors.TERTIARY), width=size,
                        height=size, border_radius=size / 2, gradient=markFill(), alignment=ft.Alignment.CENTER)
