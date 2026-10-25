"""The look (plan 12c, G1, LK1.1, LK1.2, LK1.3): black and shades of black and grey, with red woven into the
background. Dark mode follows the phone: black underneath, charcoal cards with a blood-red undertone, lighter
shades for what's raised or picked, white for what matters. Light mode is the mirror: white underneath,
light cards, black. The red stays behind the content (LK1.3): a glow and sharp diagonal streaks behind every
screen, cards fading from a red corner, the picked tab, progress tracks, the fill under a chart and the edge
of the tab bar. Text, ticks and the main buttons are never red. Everything takes its shade from the theme's
colour roles below, so one screen looks right in both modes.

Only characters the built-in font has are written on screen (no ✓ ▾ ↑ ✎): icons stand in for them, because
the PC view ships without fallback fonts and would draw boxes (LK1.2).
"""

import flet as ft

from usefulShared.look import (  # the suite's pieces, used by Talos's screens through here
    accent,
    accentEdge,
    big,
    card,
    chartFade,
    chevron,
    dot,
    faint,
    field,
    filling,
    gap,
    grow,
    hairline,
    header,
    heading,
    iconButton,
    indicator,
    label,
    listCard,
    listRow,
    mainButton,
    makeTheme,
    markFill,
    pagePadding,
    pill,
    quiet,
    radius,
    screen,
    segments,
    softButton,
    statTile,
    streak,
    tapSize,
    title,
    track,
)

redEdge = accentEdge  # the sharp red line along the tab bar (LK1.3)

# The shades, darkest first in dark mode (lightest first in light mode). Each is a theme colour role, so
# controls use them by name (ft.Colors.SURFACE_CONTAINER_LOW and so on) and get the right one for the mode.
# Under the black and white, every shade leans a little towards red (LK1.3).
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
lightShades = {
    "surface": "#FFFFFF",
    "surface_container_lowest": "#FDFAFA",
    "surface_container_low": "#F5EEEE",
    "surface_container": "#F0E7E7",
    "surface_container_high": "#EADFDF",
    "surface_container_highest": "#DFD0D1",
    "outline_variant": "#EBDCDD",
    "outline": "#9A9A9A",
    "on_surface_variant": "#5E5E5E",
    "on_surface": "#0A0A0A",
    "primary": "#000000",
    "on_primary": "#FFFFFF",
}
# The reds (LK1.3), in the theme's tertiary roles, which nothing else uses: the red itself (streaks, glows,
# the rest timer's bar), deep red (the picked tab, raised cards, progress tracks), a card's red corner, and
# the glow's brighter red.
darkReds = {"tertiary": "#E3242B", "on_tertiary": "#000000", "tertiary_container": "#4A0D13",
            "on_tertiary_container": "#FFDADB", "tertiary_fixed": "#2A0C10", "tertiary_fixed_dim": "#FF2633"}
lightReds = {"tertiary": "#C1121F", "on_tertiary": "#FFFFFF", "tertiary_container": "#F7DCDF",
             "on_tertiary_container": "#410509", "tertiary_fixed": "#FBEFF0", "tertiary_fixed_dim": "#F08C95"}


def _theme(shades: dict[str, str]) -> ft.Theme:
    return makeTheme(shades, darkReds if shades is darkShades else lightReds)


def lightTheme() -> ft.Theme:
    return _theme(lightShades)


def darkTheme() -> ft.Theme:
    return _theme(darkShades)


def backdrop(content: ft.Control) -> ft.Control:
    """The screen's background: black, with red behind everything: a glow over the top, a fainter one low on
    the screen, a sharp-edged blade with a crisp line across the top corner, and two thin slashes near the
    bottom. Nothing in it can be tapped; the content sits on top."""
    glow = ft.Colors.TERTIARY_FIXED_DIM
    layers: list[ft.Control] = [
        ft.Container(bgcolor=ft.Colors.SURFACE, **filling),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(-0.6, -1.1), radius=1.25,
            colors=[accent(0.34, glow), accent(0.12, glow), accent(0.0, glow)], stops=[0.0, 0.4, 1.0])),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(1.15, 1.05), radius=0.95, colors=[accent(0.16, glow), accent(0.0, glow)])),
        # Long enough that their ends stay off even a wide PC window; centred 200 px in from the right edge.
        streak(2800, 220, [accent(0.0, glow), accent(0.5, glow), accent(0.12, glow), accent(0.0, glow)],
               [0.0, 0.015, 0.5, 1.0], top=-100, right=-1200),
        streak(2800, 2.5, [accent(0.0), accent(0.95), accent(0.25)], [0.4, 0.55, 0.7], across=False,
               top=150, right=-1200),
        streak(520, 2, [accent(0.0), accent(0.55), accent(0.0)], [0.0, 0.5, 1.0], across=False,
               bottom=190, left=-150),
        streak(380, 1.5, [accent(0.0), accent(0.4), accent(0.0)], [0.0, 0.5, 1.0], across=False,
               bottom=168, left=-110),
    ]
    return ft.Stack([*layers, ft.Container(content, **filling)], expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)
