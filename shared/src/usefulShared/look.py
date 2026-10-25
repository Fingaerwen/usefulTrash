"""The suite's look (plan 12c, LK1.2, LK1.3; Ambrosia's AM7.1): black and shades of black and grey, with each
app's own colour woven into the background, behind the content. Every piece here takes its colours from the
theme's roles, so one screen looks right in dark and light mode and in either app: each app sets the values
(its shades, and its colour in the tertiary roles: makeTheme) and draws its own backdrop (gym/screens/look.py,
ambrosia/screens/look.py). Text, ticks and the main buttons are never the app's colour.

Only characters the built-in font has are written on screen (no ✓ ▾ ↑ ✎): icons stand in for them, because
the PC view ships without fallback fonts and would draw boxes (LK1.2).
"""

import math

import flet as ft

tapSize = 48  # tap targets, in logical pixels
gap = 12  # between the parts of a screen
radius = 16  # cards
pagePadding = 16  # the screen's side margins


def makeTheme(shades: dict[str, str], accents: dict[str, str]) -> ft.Theme:
    """A theme from an app's shades and its colour (in the tertiary roles, which nothing else uses)."""
    scheme = ft.ColorScheme(
        **shades, **accents,
        secondary=shades["primary"], on_secondary=shades["on_primary"],
        primary_container=shades["surface_container_highest"], on_primary_container=shades["on_surface"],
        secondary_container=shades["surface_container_highest"], on_secondary_container=shades["on_surface"],
        error=shades["on_surface"], on_error=shades["surface"],
        inverse_surface=shades["on_surface"], on_inverse_surface=shades["surface"],
        surface_tint=shades["surface"], shadow="#000000", scrim="#000000",
    )
    return ft.Theme(color_scheme=scheme, scaffold_bgcolor=shades["surface"], canvas_color=shades["surface"],
                    card_bgcolor=shades["surface_container_low"], divider_color=shades["outline_variant"],
                    use_material3=True)


filling = {"left": 0, "top": 0, "right": 0, "bottom": 0}  # a backdrop layer filling the whole stack


# --- Text ------------------------------------------------------------------------------------------

def quiet(text: str, size: int = 13, **options) -> ft.Text:
    """Secondary text, for details that shouldn't shout (like "3 waiting", SC1.1)."""
    return ft.Text(text, size=size, color=ft.Colors.ON_SURFACE_VARIANT, **options)


def faint(text: str, size: int = 12, **options) -> ft.Text:
    """The faintest text: hints and legends."""
    return ft.Text(text, size=size, color=ft.Colors.OUTLINE, **options)


def title(text: str) -> ft.Text:
    """A screen's name, big."""
    return ft.Text(text, size=26, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)


def heading(text: str, **options) -> ft.Text:
    """A card's or a part's name."""
    return ft.Text(text, size=16, weight=ft.FontWeight.W_600, **options)


def label(text: str) -> ft.Text:
    """A small capital label over a number or a part: "WORKOUTS", "HISTORY"."""
    return ft.Text(text.upper(), size=11, weight=ft.FontWeight.W_600, color=ft.Colors.OUTLINE,
                   style=ft.TextStyle(letter_spacing=1.1))


def big(text: str, size: int = 24) -> ft.Text:
    """A number that's the point of its tile."""
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD)


# --- Surfaces ------------------------------------------------------------------------------------

def card(content: ft.Control, padding: int | ft.Padding = 16, on_click=None, tooltip: str | None = None,
         hollow: bool = False, raised: bool = False, **options) -> ft.Container:
    """A rounded panel, fading from a corner of the app's colour into its charcoal (LK1.3). Hollow ones (only an
    outline) recede: done exercises. Raised ones stand out, from the deep accent: banners and the rest timer."""
    fill, border, behind = None, None, None
    if hollow:  # a faint wash of the background, so the streaks behind it stay quiet
        border, behind = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), ft.Colors.with_opacity(0.6, ft.Colors.SURFACE)
    elif raised:
        fill = _fade(ft.Colors.TERTIARY_CONTAINER, ft.Colors.SURFACE_CONTAINER_HIGH, 0.85)
    else:
        fill = _fade(ft.Colors.TERTIARY_FIXED, ft.Colors.SURFACE_CONTAINER_LOW, 0.55)
    return ft.Container(content, bgcolor=behind, gradient=fill, border=border, border_radius=radius, padding=padding,
                        ink=on_click is not None, on_click=on_click, tooltip=tooltip, **options)


def _fade(corner: str, rest: str, reach: float) -> ft.LinearGradient:
    """From a red top-left corner into a shade, diagonally, done at `reach` of the way across."""
    return ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=[corner, rest],
                             stops=[0.0, reach])


# --- The app's colour in the background (LK1.3, AM7.1) ---------------------------------------------------------------

indicator = ft.Colors.TERTIARY_CONTAINER  # the picked tab's marker, in the tab bar and the PC view's rail
track = ft.Colors.TERTIARY_CONTAINER  # a progress bar's empty part
chartFade = [ft.Colors.with_opacity(0.42, ft.Colors.TERTIARY), ft.Colors.with_opacity(0.0, ft.Colors.TERTIARY)]
slashAngle = -math.radians(24)  # every streak and edge runs at this angle, like one cut


def accent(opacity: float, color: str = ft.Colors.TERTIARY) -> str:
    """The app's colour (or another of its roles) at an opacity."""
    return ft.Colors.with_opacity(opacity, color)


def streak(width: float, height: float, colors: list[str], stops: list[float], across: bool = True,
            **place) -> ft.Container:
    """One diagonal streak: a long thin band at slashAngle, its gradient across it (a hard edge where it starts
    strong) or along it (fading at its ends)."""
    begin, end = ((ft.Alignment.TOP_CENTER, ft.Alignment.BOTTOM_CENTER) if across
                  else (ft.Alignment.CENTER_LEFT, ft.Alignment.CENTER_RIGHT))
    return ft.Container(width=width, height=height, rotate=ft.Rotate(slashAngle),
                        gradient=ft.LinearGradient(begin=begin, end=end, colors=colors, stops=stops), **place)


def accentEdge(vertical: bool = False) -> ft.Container:
    """A sharp line of the app's colour along the tab bar's top (or the PC view's rail's side), brightest in
    the middle."""
    gradient = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER if vertical else ft.Alignment.CENTER_LEFT,
                                 end=ft.Alignment.BOTTOM_CENTER if vertical else ft.Alignment.CENTER_RIGHT,
                                 colors=[accent(0.15), accent(0.9), accent(0.15)], stops=[0.0, 0.35, 1.0])
    return ft.Container(width=2 if vertical else None, height=None if vertical else 2, gradient=gradient)


def markFill() -> ft.LinearGradient:
    """The app sign's circle: the deep accent into its grey."""
    return _fade(ft.Colors.TERTIARY_CONTAINER, ft.Colors.SURFACE_CONTAINER_HIGH, 1.0)


def hairline() -> ft.Divider:
    return ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT)


def listCard(rows: list[ft.Control]) -> ft.Container:
    """Rows in one card with hairlines between them (each row brings its own padding)."""
    parts: list[ft.Control] = []
    for index, row in enumerate(rows):
        if index:
            parts.append(hairline())
        parts.append(row)
    return card(ft.Column(parts, spacing=0), padding=0, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def listRow(content: ft.Control, on_click=None, tooltip: str | None = None, padding: ft.Padding | None = None,
            **options) -> ft.Container:
    """One row in a list card: padded, tappable when it opens something."""
    return ft.Container(content, padding=padding or ft.Padding.symmetric(horizontal=16, vertical=12),
                        ink=on_click is not None, on_click=on_click, tooltip=tooltip, **options)


def chevron() -> ft.Icon:
    return ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.OUTLINE, size=20)


def dot(size: int = 6, color: str = ft.Colors.OUTLINE) -> ft.Container:
    return ft.Container(width=size, height=size, bgcolor=color, border_radius=size / 2)


# --- Controls ------------------------------------------------------------------------------------

def grow(expand: bool) -> bool | None:
    """expand as a control takes it: True, or left unset. An explicit False still wraps the control as flexible
    on the Flutter side, which a wrapping row refuses (it draws Flutter's grey error box)."""
    return True if expand else None


def pill(text: str, selected: bool = False, on_click=None, tooltip: str | None = None,
         icon: ft.IconData | None = None) -> ft.Container:
    """A small rounded chip; picked ones are filled."""
    color = ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE
    words = ft.Text(text, size=13, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500, color=color)
    content = ft.Row([ft.Icon(icon, size=16, color=color), words], spacing=6, tight=True) if icon else words
    return ft.Container(content, bgcolor=ft.Colors.PRIMARY if selected else ft.Colors.SURFACE_CONTAINER_HIGH,
                        border_radius=20, padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        ink=on_click is not None, on_click=on_click, tooltip=tooltip)


def segments(options: list[tuple[str, str]], selected: str, choose) -> ft.Row:
    """Choices side by side (3M · 1Y · All, Days · Months · All time); the picked one is filled."""
    return ft.Row([pill(text, key == selected, on_click=lambda e, key=key: choose(key), tooltip=f"Show {text}")
                   for key, text in options], spacing=6, wrap=True)


def _buttonStyle(background: str, foreground: str) -> ft.ButtonStyle:
    return ft.ButtonStyle(bgcolor=background, color=foreground, elevation=0,
                          shape=ft.RoundedRectangleBorder(radius=14),
                          padding=ft.Padding.symmetric(horizontal=20, vertical=14),
                          text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600))


def mainButton(text: str, on_click, icon: ft.IconData | None = None, disabled: bool = False,
               tooltip: str | None = None, expand: bool = False) -> ft.Button:
    """The one button a screen is about (Finish workout, Save, Sign in): filled white in dark mode."""
    return ft.Button(text, icon=icon, on_click=on_click, disabled=disabled, tooltip=tooltip, height=tapSize + 4,
                     expand=grow(expand), style=_buttonStyle(ft.Colors.PRIMARY, ft.Colors.ON_PRIMARY))


def softButton(text: str, on_click, icon: ft.IconData | None = None, disabled: bool = False,
               tooltip: str | None = None, expand: bool = False) -> ft.Button:
    """A second button, grey."""
    return ft.Button(text, icon=icon, on_click=on_click, disabled=disabled, tooltip=tooltip, height=tapSize,
                     expand=grow(expand), style=_buttonStyle(ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE))


def field(fieldLabel: str, value: str, on_change, width: float | None = None, expand: bool = False,
          number: bool = True, size: int = 16) -> ft.TextField:
    """A text field: a filled grey box with rounded corners, outlined while typing."""
    return ft.TextField(label=fieldLabel, value=value, on_change=on_change, width=width, expand=grow(expand),
                        keyboard_type=ft.KeyboardType.NUMBER if number else ft.KeyboardType.TEXT,
                        filled=True, fill_color=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=12,
                        border=ft.OutlineInputBorder(border_radius=12), border_color=ft.Colors.TRANSPARENT,
                        focused_border_color=ft.Colors.OUTLINE, text_size=size,
                        label_style=ft.TextStyle(color=ft.Colors.ON_SURFACE_VARIANT),
                        cursor_color=ft.Colors.PRIMARY)


def iconButton(icon: ft.IconData, tooltip: str, on_click, disabled: bool = False, size: int = 22,
               color: str | None = None) -> ft.IconButton:
    return ft.IconButton(icon, tooltip=tooltip, on_click=on_click, disabled=disabled, icon_size=size,
                         icon_color=color, width=tapSize, height=tapSize)


def header(titleText: str, subtitle: ft.Control | str | None = None, leading: ft.Control | None = None,
           trailing: list[ft.Control] | None = None) -> ft.Row:
    """A screen's top: an optional back button, the name big with a line under it, buttons on the right."""
    words: list[ft.Control] = [title(titleText)]
    if subtitle:
        words.append(quiet(subtitle, size=14) if isinstance(subtitle, str) else subtitle)
    parts: list[ft.Control] = [leading] if leading is not None else []
    parts += [ft.Column(words, spacing=2, expand=True), *(trailing or [])]
    return ft.Row(parts, vertical_alignment=ft.CrossAxisAlignment.START, spacing=4)


def statTile(name: str, value: str, detail: str | None = None, icon: ft.IconData | None = None,
             expand: bool = True, size: int = 22) -> ft.Container:
    """A number with its label over it and a detail under it (the Week tab's tiles, an exercise's PRs). Put it in
    a row: it takes its share of the row's width."""
    parts: list[ft.Control] = [label(name), big(value, size)]
    if detail:
        line = quiet(detail, size=12)
        parts.append(ft.Row([ft.Icon(icon, size=14, color=ft.Colors.ON_SURFACE_VARIANT), line], spacing=4, tight=True)
                     if icon else line)
    return card(ft.Column(parts, spacing=4), padding=14, expand=grow(expand))


def screen(parts: list[ft.Control]) -> ft.Column:
    """A tab's content: scrolls, with room at the bottom."""
    return ft.Column([*parts, ft.Container(height=8)], spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True,
                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
