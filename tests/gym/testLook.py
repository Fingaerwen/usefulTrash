"""The look (LK1.1 to LK1.5): black, white and greys with red woven into the background, dark only, corners cut,
and the screen test kit's checks for what Flutter refuses to draw (its grey box) and what the PC view's font can't
write."""

import dataclasses

import flet as ft
import pytest
from screenTestKit import layoutProblems, undrawable

from gym.screens.look import card, darkReds, darkShades, darkTheme, form, mainButton, pill

textRoles = ("outline", "on_surface_variant", "on_surface", "primary", "on_primary")  # never red (LK1.3)


def rgb(shade: str) -> tuple[int, int, int]:
    return int(shade[1:3], 16), int(shade[3:5], 16), int(shade[5:7], 16)


def testShadesAreGreysLeaningTowardsRed():
    """Black with shades of black and grey (LK1.2), each leaning a little towards red (LK1.3): never more red
    than a tint. Text, ticks and the main buttons stay pure greys."""
    for role, shade in darkShades.items():
        red, green, blue = rgb(shade)
        if role in textRoles or role == "surface":
            assert red == green == blue, (role, shade)
        else:
            leansRed = red >= max(green, blue) and red - min(green, blue) <= 24 and abs(green - blue) <= 4
            assert leansRed, (role, shade)
    assert darkShades["surface"] == "#000000"
    assert darkTheme().color_scheme.primary == "#FFFFFF"


def testTheRedsLiveInTheirOwnRoles():
    """The reds are only in the tertiary roles, which nothing else uses (LK1.3), and they are reds."""
    theme = darkTheme()
    roles = {field.name for field in dataclasses.fields(theme.color_scheme)}
    assert set(darkReds) <= {name for name in roles if name.startswith(("tertiary", "on_tertiary"))}
    for role, shade in darkReds.items():
        if role == "on_tertiary":
            continue  # black on red
        red, green, blue = rgb(shade)
        assert red > green and red > blue, (role, shade)
        assert getattr(theme.color_scheme, role) == shade


def testCornersAreCutAndCardsSeeThrough():
    """Talon's half of the mirrored opposites (LK1.4): cards, chips and buttons have two corners cut (top left,
    bottom right), and a card is see-through with a blur, so the knight behind shows faintly."""
    panel = card(ft.Text("Lat pulldown"))
    assert isinstance(panel.shape, ft.BeveledRectangleBorder)
    assert (panel.shape.radius.top_left, panel.shape.radius.top_right) == (form.corner, 0)
    assert panel.content.blur and panel.content.border.top.width == 1  # the blur, and the thin red top edge
    assert isinstance(pill("3M").shape, ft.BeveledRectangleBorder)
    assert isinstance(mainButton("Save", None).style.shape, ft.BeveledRectangleBorder)
    assert card(ft.Text("Done"), hollow=True).content.blur is None  # done exercises recede, no blur


@pytest.mark.parametrize("child", [
    ft.Dropdown(expand=True),  # 0.3-alpha's Charts tab: a grey box on the phone
    ft.Text("kg", expand=True),  # 0.3-alpha's Weight tab
    ft.Button("Save", expand=False),  # an explicit False is flexible too
])
def testAnythingFlexibleInAWrappingRowIsRefused(child):
    assert layoutProblems(ft.Row([child, ft.Text("3M")], wrap=True))


def testExpandWhereThereIsNoHeightLimitIsRefused():
    assert layoutProblems(ft.Column([ft.Container(expand=True)], scroll=ft.ScrollMode.AUTO))
    assert layoutProblems(ft.Column([ft.Column([ft.Container(expand=True)])], scroll=ft.ScrollMode.AUTO))
    assert layoutProblems(ft.Column([ft.Row([ft.Text("a")], vertical_alignment=ft.CrossAxisAlignment.STRETCH)],
                                    scroll=ft.ScrollMode.AUTO))
    assert not layoutProblems(ft.Column([ft.Row([ft.Text("a", expand=True), mainButton("Save", None)])],
                                        scroll=ft.ScrollMode.AUTO))  # sideways is fine
    assert not layoutProblems(ft.Column([ft.Container(ft.Column([ft.Container(expand=True)]), height=100)],
                                        scroll=ft.ScrollMode.AUTO))  # a height limits it again


def testOnlyWhatTheFontHasIsWritten():
    assert undrawable(ft.Text("Mo ✓")) == {"✓"}
    assert undrawable(ft.Text("4×8 @ 82.5 kg · 25 to 30 kg/side  −0.4 · “cue” – 30°")) == set()
    assert undrawable(ft.PopupMenuItem(content="▾ sets")) == {"▾"}
