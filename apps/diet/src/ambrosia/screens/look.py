"""Ambrosia's look (apps/diet/docs/plan.md AM7.1, AM7.3): the suite's black and shades (usefulShared.look) with
bold, sharp, flashy gold and light pink, all behind the content. Dark mode follows the phone: black underneath,
cards with a pink undertone fading from a pink corner, metallic-gold streaks with a pale shine and anime-style
sparkles, light-pink glows, and a goddess drawn in anime style, large and faint behind the lower right (a
placeholder you may replace, AM7.3). Light mode mirrors it. Text, ticks and the main buttons are never gold or
pink.
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

# The shades, darkest first in dark mode; under the black and white each leans towards pink.
darkShades = {
    "surface": "#000000",
    "surface_container_lowest": "#0A0609",
    "surface_container_low": "#1A0F17",  # cards
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
lightShades = {
    "surface": "#FFFFFF",
    "surface_container_lowest": "#FFFAFD",
    "surface_container_low": "#FBEEF6",
    "surface_container": "#F7E6F1",
    "surface_container_high": "#F2DDEB",
    "surface_container_highest": "#E9CDE0",
    "outline_variant": "#F2DCEA",
    "outline": "#9A9A9A",
    "on_surface_variant": "#5E5E5E",
    "on_surface": "#0A0A0A",
    "primary": "#000000",
    "on_primary": "#FFFFFF",
}
# Gold and pink (AM7.1, AM7.3), in the theme's tertiary roles: gold itself (streaks, lines, bars, the goblet),
# its pale shine (on_tertiary_fixed: the bright edge of a streak, the sparkles), pink (the picked tab, raised
# cards, tracks), a card's pink corner, and the glows' light pink.
darkAccents = {"tertiary": "#FFC72C", "on_tertiary": "#000000", "on_tertiary_fixed": "#FFF4B8",
               "tertiary_container": "#86285F", "on_tertiary_container": "#FFE3F3",
               "tertiary_fixed": "#40152F", "tertiary_fixed_dim": "#FF8AD0"}
lightAccents = {"tertiary": "#D69A00", "on_tertiary": "#FFFFFF", "on_tertiary_fixed": "#FFD54A",
                "tertiary_container": "#FFCDEA", "on_tertiary_container": "#4A0D2F",
                "tertiary_fixed": "#FFEAF6", "tertiary_fixed_dim": "#FF9BD6"}

goldEdge = accentEdge  # the sharp gold line along the tab bar
goddessImage = "goddess.webp"  # in src/assets, made by apps/diet/makeGoddess.py


def lightTheme() -> ft.Theme:
    return makeTheme(lightShades, lightAccents)


def darkTheme() -> ft.Theme:
    return makeTheme(darkShades, darkAccents)


def sparkle(size: float, **place) -> ft.Container:
    """An anime-style twinkle: a four-point star of thin gold rays fading out, around a bright core."""
    shine = ft.Colors.ON_TERTIARY_FIXED
    ray = 1.6
    core = size * 0.22
    return ft.Container(ft.Stack([
        ft.Container(width=size, height=ray, top=(size - ray) / 2, gradient=ft.LinearGradient(
            colors=[accent(0.0, shine), accent(1.0, shine), accent(0.0, shine)])),
        ft.Container(width=ray, height=size, left=(size - ray) / 2, gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
            colors=[accent(0.0, shine), accent(1.0, shine), accent(0.0, shine)])),
        ft.Container(width=core, height=core, left=(size - core) / 2, top=(size - core) / 2, border_radius=core / 2,
                     bgcolor=shine, shadow=ft.BoxShadow(blur_radius=size * 0.4, color=accent(0.9))),
    ], width=size, height=size), width=size, height=size, **place)


def backdrop(content: ft.Control) -> ft.Control:
    """The screen's background: black, a light-pink glow over the top and another low on the right, a sharp
    metallic-gold blade with a pale shine on its edge and a double crisp line across the top corner, sparkles
    around it, and thin pink and gold slashes near the bottom. Nothing in it can be tapped; the content sits on
    top."""
    pink, gold, shine = ft.Colors.TERTIARY_FIXED_DIM, ft.Colors.TERTIARY, ft.Colors.ON_TERTIARY_FIXED
    layers: list[ft.Control] = [
        ft.Container(bgcolor=ft.Colors.SURFACE, **filling),
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(-0.7, -1.1), radius=1.3,
            colors=[accent(0.52, pink), accent(0.18, pink), accent(0.0, pink)], stops=[0.0, 0.42, 1.0])),
        # Washes are pink: gold spread thin over black turns brown, so gold stays sharp (lines, edges, sparkles).
        ft.Container(**filling, gradient=ft.RadialGradient(
            center=ft.Alignment(1.1, 0.95), radius=1.05, colors=[accent(0.22, pink), accent(0.0, pink)])),
        # Long enough that their ends stay off even a wide PC window; centred 200 px in from the right edge.
        streak(2800, 210, [accent(0.0, shine), accent(0.95, shine), accent(0.7, gold), accent(0.16, gold),
                           accent(0.0, gold)], [0.0, 0.012, 0.05, 0.2, 0.42], top=-95, right=-1200),
        streak(2800, 3.5, [accent(0.0, shine), accent(1.0, shine), accent(0.4, gold)], [0.38, 0.55, 0.72],
               across=False, top=150, right=-1200),
        streak(2800, 1.5, [accent(0.0, gold), accent(0.9, gold), accent(0.0, gold)], [0.4, 0.58, 0.75],
               across=False, top=162, right=-1200),
        # The goddess (AM7.3): drawn for the app, apps/diet/art/goddess.svg; large and faint, lower right.
        ft.Image(src=goddessImage, height=560, fit=ft.BoxFit.CONTAIN, opacity=0.5, right=-50, bottom=36),
        sparkle(32, top=54, right=114), sparkle(16, top=28, right=44), sparkle(22, top=126, right=20),
        sparkle(12, top=96, right=178),
        streak(520, 2, [accent(0.0, pink), accent(0.85, pink), accent(0.0, pink)], [0.0, 0.5, 1.0], across=False,
               bottom=190, left=-150),
        streak(380, 1.5, [accent(0.0, gold), accent(0.8, gold), accent(0.0, gold)], [0.0, 0.5, 1.0], across=False,
               bottom=168, left=-110),
        sparkle(20, bottom=212, left=94),
    ]
    return ft.Stack([*layers, ft.Container(content, **filling)], expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)


def appMark(size: int = 72) -> ft.Container:
    """Ambrosia's sign: a goblet (the food of the gods was drunk too) in a circle of deep pink fading to grey."""
    return ft.Container(ft.Icon(ft.Icons.LOCAL_BAR, size=size * 0.48, color=ft.Colors.TERTIARY), width=size,
                        height=size, border_radius=size / 2, gradient=markFill(), alignment=ft.Alignment.CENTER)
