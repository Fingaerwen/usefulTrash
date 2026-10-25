"""The look (LK1.1, LK1.2, LK1.3): black, white and greys with red woven into the background; and the screen
test kit's checks for what Flutter refuses to draw (its grey box) and what the PC view's font can't write."""

import dataclasses

import flet as ft
import pytest
from screenTestKit import layoutProblems, undrawable

from gym.screens.look import darkReds, darkShades, darkTheme, lightReds, lightShades, lightTheme, mainButton

textRoles = ("outline", "on_surface_variant", "on_surface", "primary", "on_primary")  # never red (LK1.3)


def rgb(shade: str) -> tuple[int, int, int]:
    return int(shade[1:3], 16), int(shade[3:5], 16), int(shade[5:7], 16)


def testShadesAreGreysLeaningTowardsRed():
    """Black with shades of black and grey (LK1.2), each leaning a little towards red (LK1.3): never more red
    than a tint. Text, ticks and the main buttons stay pure greys."""
    assert darkShades.keys() == lightShades.keys()
    for shades in (darkShades, lightShades):
        for role, shade in shades.items():
            red, green, blue = rgb(shade)
            if role in textRoles or role == "surface":
                assert red == green == blue, (role, shade)
            else:
                leansRed = red >= max(green, blue) and red - min(green, blue) <= 24 and abs(green - blue) <= 4
                assert leansRed, (role, shade)
    assert (darkShades["surface"], lightShades["surface"]) == ("#000000", "#FFFFFF")  # black, mirrored in light
    assert darkTheme().color_scheme.primary == "#FFFFFF" and lightTheme().color_scheme.primary == "#000000"


def testTheRedsLiveInTheirOwnRoles():
    """The reds are only in the tertiary roles, which nothing else uses (LK1.3), and they are reds."""
    for reds, theme in ((darkReds, darkTheme()), (lightReds, lightTheme())):
        roles = {field.name for field in dataclasses.fields(theme.color_scheme)}
        assert set(reds) <= {name for name in roles if name.startswith(("tertiary", "on_tertiary"))}
        for role, shade in reds.items():
            if role == "on_tertiary":
                continue  # black or white on red
            red, green, blue = rgb(shade)
            assert red > green and red > blue, (role, shade)
            assert getattr(theme.color_scheme, role) == shade


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
