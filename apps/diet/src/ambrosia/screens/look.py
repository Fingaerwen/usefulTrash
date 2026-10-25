"""Ambrosia's look (apps/diet/docs/plan.md AM7.1): the suite's black and shades (usefulShared.look) with bold,
sharp gold and pink gradients over a goddess, all behind the content. Dark mode follows the phone: black
underneath, cards with a deep-pink undertone fading from a pink corner, gold streaks and lines, hot-pink glows,
and a marble goddess in pink and gold (a Hellenistic head, the Met's Open Access, CC0; apps/diet/makeGoddess.py)
large and faint behind the lower right. Light mode mirrors it. Text, ticks and the main buttons are never gold
or pink.
"""

import flet as ft

from usefulShared.look import (  # the suite's pieces, used by Ambrosia's screens through here
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

goddessImage = "goddess.webp"  # in src/assets

# The shades, darkest first in dark mode; under the black and white each leans a little towards pink.
darkShades = {
    "surface": "#000000",
    "surface_container_lowest": "#090607",
    "surface_container_low": "#170F13",  # cards
    "surface_container": "#1D1318",
    "surface_container_high": "#29181F",  # fields, chips, raised parts in a card
    "surface_container_highest": "#37202A",  # what's picked: a segment
    "outline_variant": "#2F1B24",  # hairlines between rows
    "outline": "#6B6B6B",
    "on_surface_variant": "#A6A6A6",
    "on_surface": "#F5F5F5",
    "primary": "#FFFFFF",
    "on_primary": "#000000",
}
lightShades = {
    "surface": "#FFFFFF",
    "surface_container_lowest": "#FDFAFB",
    "surface_container_low": "#F6EEF2",
    "surface_container": "#F1E7EC",
    "surface_container_high": "#EBDFE5",
    "surface_container_highest": "#E0D0D8",
    "outline_variant": "#ECDCE4",
    "outline": "#9A9A9A",
    "on_surface_variant": "#5E5E5E",
    "on_surface": "#0A0A0A",
    "primary": "#000000",
    "on_primary": "#FFFFFF",
}
# Gold and pink (AM7.1), in the theme's tertiary roles: gold itself (streaks, lines, bars), deep pink (the
# picked tab, raised cards, tracks), a card's pink corner, and the glows' hot pink.
darkAccents = {"tertiary": "#F2B530", "on_tertiary": "#000000", "tertiary_container": "#4E1235",
               "on_tertiary_container": "#FFD9EC", "tertiary_fixed": "#2C0E1F", "tertiary_fixed_dim": "#FF3FA4"}
lightAccents = {"tertiary": "#A8740F", "on_tertiary": "#FFFFFF", "tertiary_container": "#F8DCEB",
                "on_tertiary_container": "#4A0D2F", "tertiary_fixed": "#FCEFF5", "tertiary_fixed_dim": "#F3A0CC"}

goldEdge = accentEdge  # the sharp gold line along the tab bar


def lightTheme() -> ft.Theme:
    return makeTheme(lightShades, lightAccents)


def darkTheme() -> ft.Theme:
    return makeTheme(darkShades, darkAccents)


def backdrop(content: ft.Control) -> ft.Control:
    """The screen's background: black, a hot-pink glow over the top and a gold one low on the right, the goddess
    large and faint behind the lower right, a sharp gold blade with a crisp line across the top corner, and two
    thin gold slashes near the bottom. Nothing in it can be tapped; the content sits on top."""
    pink, gold = ft.Colors.TERTIARY_FIXED_DIM, ft.Colors.TERTIARY
    layers: list[ft.Control] = [
        ft.Container(bgcolor=ft.Colors.SURFACE, **filling),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(-0.7, -1.1), radius=1.3,
            colors=[accent(0.32, pink), accent(0.11, pink), accent(0.0, pink)], stops=[0.0, 0.42, 1.0])),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(1.1, 0.9), radius=1.0, colors=[accent(0.16, gold), accent(0.0, gold)])),
        ft.Image(src=goddessImage, height=600, fit=ft.BoxFit.CONTAIN, opacity=0.3, right=-70, bottom=40),
        # Long enough that their ends stay off even a wide PC window; centred 200 px in from the right edge.
        streak(2800, 200, [accent(0.0, gold), accent(0.42, gold), accent(0.08, gold), accent(0.0, gold)],
               [0.0, 0.015, 0.5, 1.0], top=-90, right=-1200),
        streak(2800, 2.5, [accent(0.0, gold), accent(0.95, gold), accent(0.25, gold)], [0.4, 0.55, 0.7],
               across=False, top=150, right=-1200),
        streak(520, 2, [accent(0.0, pink), accent(0.7, pink), accent(0.0, pink)], [0.0, 0.5, 1.0], across=False,
               bottom=190, left=-150),
        streak(380, 1.5, [accent(0.0, gold), accent(0.55, gold), accent(0.0, gold)], [0.0, 0.5, 1.0], across=False,
               bottom=168, left=-110),
    ]
    return ft.Stack([*layers, ft.Container(content, **filling)], expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)


def appMark(size: int = 72) -> ft.Container:
    """Ambrosia's sign: a goblet (the food of the gods was drunk too) in a circle of deep pink fading to grey."""
    return ft.Container(ft.Icon(ft.Icons.LOCAL_BAR, size=size * 0.48, color=ft.Colors.TERTIARY), width=size,
                        height=size, border_radius=size / 2, gradient=markFill(), alignment=ft.Alignment.CENTER)
