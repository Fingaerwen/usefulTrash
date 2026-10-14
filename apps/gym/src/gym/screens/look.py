"""The look (plan 12c, G1 + LK1.1): dark mode follows the phone; the accent is white in dark mode and
black in light mode, so the app is black and white either way. Medium-sized tap targets."""

import flet as ft

tapSize = 44  # medium tap targets, in logical pixels
gap = 8


def lightTheme() -> ft.Theme:
    return ft.Theme(color_scheme=ft.ColorScheme(
        primary=ft.Colors.BLACK, on_primary=ft.Colors.WHITE, secondary=ft.Colors.BLACK, on_secondary=ft.Colors.WHITE,
        surface=ft.Colors.WHITE, on_surface=ft.Colors.BLACK, outline=ft.Colors.GREY_500))


def darkTheme() -> ft.Theme:
    return ft.Theme(color_scheme=ft.ColorScheme(
        primary=ft.Colors.WHITE, on_primary=ft.Colors.BLACK, secondary=ft.Colors.WHITE, on_secondary=ft.Colors.BLACK,
        surface=ft.Colors.BLACK, on_surface=ft.Colors.WHITE, outline=ft.Colors.GREY_600))


def quiet(text: str, size: int = 13) -> ft.Text:
    """Small grey text, for details that shouldn't shout (like "3 waiting", SC1.1)."""
    return ft.Text(text, size=size, color=ft.Colors.GREY_500)


def title(text: str) -> ft.Text:
    return ft.Text(text, size=18, weight=ft.FontWeight.BOLD)
