"""The look (plan 12c, LK1.1 to LK1.5): black and shades of black and grey, with red woven into the background,
and Talon as the hard half of the suite's mirrored opposites (LK1.4): corners cut, a winged knight in crimson
power armour behind every screen, faint, lower right, facing right towards Ambrosia. Dark only (LK1.5): black
underneath, see-through charcoal cards with a blood-red undertone and a blur, lighter shades for what's raised
or picked, white for what matters. The red stays behind the content (LK1.3): a glow and sharp diagonal streaks,
cards fading from a red top-left corner with a thin red top edge, the picked tab, progress tracks, the fill under
a chart and the edge of the tab bar. Text, ticks and the main buttons are never red. Everything takes its shade
from the theme's colour roles below.

Only characters the built-in font has are written on screen (no ✓ ▾ ↑ ✎): icons stand in for them, because
the PC view ships without fallback fonts and would draw boxes (LK1.2).
"""

from functools import partial

import flet as ft

from usefulShared import look as suite
from usefulShared.look import (  # the suite's pieces, used by Talon's screens through here
    Form,
    accent,
    accentEdge,
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
    streak,
    tapSize,
    title,
    track,
)

# Talon's shapes (LK1.4): two corners cut, the card's red from the top left, a thin red line along each card's top
form = Form(cut=True, corner=14, small=7, button=10, fadeFrom=ft.Alignment.TOP_LEFT, topEdge=True)
card = partial(suite.card, form=form)
listCard = partial(suite.listCard, form=form)
statTile = partial(suite.statTile, form=form)
pill = partial(suite.pill, form=form)
segments = partial(suite.segments, form=form)
mainButton = partial(suite.mainButton, form=form)
softButton = partial(suite.softButton, form=form)
field = partial(suite.field, form=form)
markFill = partial(suite.markFill, form=form)
shaped = partial(suite.shaped, form=form)
indicatorShape = suite.indicatorShape(form=form)
knightImage = "talon.webp"  # in src/assets, made by tools/makeArt.py from apps/gym/art/talon.svg

redEdge = accentEdge  # the sharp red line along the tab bar (LK1.3)

# The shades, darkest first. Each is a theme colour role, so controls use them by name
# (ft.Colors.SURFACE_CONTAINER_LOW and so on). Under the black and white, every shade leans a little towards red
# (LK1.3).
darkShades = {
    "surface": "#000000",  # underneath everything
    "surface_container_lowest": "#090506",
    "surface_container_low": "#170D0F",  # cards
    "surface_container": "#1D1113",
    "surface_container_high": "#281719",  # fields, chips, raised parts in a card
    "surface_container_highest": "#351E21",  # what's picked: a segment
    "outline_variant": "#2D1A1C",  # hairlines between rows
    "outline": "#6B6B6B",  # faint text and idle icons
    "on_surface_variant": "#A6A6A6",  # secondary text
    "on_surface": "#F5F5F5",  # text
    "primary": "#FFFFFF",  # what matters: ticks, the main button, chart lines
    "on_primary": "#000000",
}
# The reds (LK1.3), in the theme's tertiary roles, which nothing else uses: the red itself (streaks, glows,
# the rest timer's bar), deep red (the picked tab, raised cards, progress tracks), a card's red corner, and
# the glow's brighter red.
darkReds = {"tertiary": "#E3242B", "on_tertiary": "#000000", "tertiary_container": "#4A0D13",
            "on_tertiary_container": "#FFDADB", "tertiary_fixed": "#2A0C10", "tertiary_fixed_dim": "#FF2633"}


def darkTheme() -> ft.Theme:
    """The one theme: Talon is dark only (LK1.5)."""
    return makeTheme(darkShades, darkReds)


def backdrop(content: ft.Control, wide: bool = False) -> ft.Control:
    """The screen's background: black, with red behind everything: a glow over the top, a fainter one low on
    the screen, a sharp-edged blade with a crisp line across the top corner, two thin slashes near the bottom,
    and the knight, faint, lower right (LK1.4), larger in the PC view (wide). Nothing in it can be tapped. The
    content sits on top."""
    glow = ft.Colors.TERTIARY_FIXED_DIM
    layers: list[ft.Control] = [
        ft.Container(bgcolor=ft.Colors.SURFACE, **filling),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(-0.6, -1.1), radius=1.25,
            colors=[accent(0.34, glow), accent(0.12, glow), accent(0.0, glow)], stops=[0.0, 0.4, 1.0])),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(1.15, 1.05), radius=0.95, colors=[accent(0.16, glow), accent(0.0, glow)])),
        # Long enough that their ends stay off even a wide PC window. Centred 200 px in from the right edge.
        streak(2800, 220, [accent(0.0, glow), accent(0.5, glow), accent(0.12, glow), accent(0.0, glow)],
               [0.0, 0.015, 0.5, 1.0], top=-100, right=-1200),
        streak(2800, 2.5, [accent(0.0), accent(0.95), accent(0.25)], [0.4, 0.55, 0.7], across=False,
               top=150, right=-1200),
        streak(520, 2, [accent(0.0), accent(0.55), accent(0.0)], [0.0, 0.5, 1.0], across=False,
               bottom=190, left=-150),
        streak(380, 1.5, [accent(0.0), accent(0.4), accent(0.0)], [0.0, 0.5, 1.0], across=False,
               bottom=168, left=-110),
        # The knight (LK1.4): drawn for the app, apps/gym/art/talon.svg, facing right towards Ambrosia
        ft.Image(src=knightImage, height=640, opacity=0.7, right=-20, bottom=-40) if wide else
        ft.Image(src=knightImage, height=560, opacity=0.8, right=-40, bottom=60),
    ]
    return ft.Stack([*layers, ft.Container(content, **filling)], expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)
