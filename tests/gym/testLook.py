"""The look (LK1.1, LK1.2): only black, white and greys; and the screen test kit's checks for what Flutter
refuses to draw (its grey box) and what the PC view's font can't write."""

import flet as ft
import pytest
from screenTestKit import layoutProblems, undrawable

from gym.screens.look import darkShades, darkTheme, lightShades, lightTheme, mainButton


def testBothThemesAreBlackWhiteAndGreysOnly():
    """You chose black with shades of black and grey (LK1.2): every shade has equal red, green and blue."""
    assert darkShades.keys() == lightShades.keys()
    for shade in [*darkShades.values(), *lightShades.values()]:
        red, green, blue = shade[1:3], shade[3:5], shade[5:7]
        assert red == green == blue, shade
    assert (darkShades["surface"], lightShades["surface"]) == ("#000000", "#FFFFFF")  # black, mirrored in light
    assert darkTheme().color_scheme.primary == "#FFFFFF" and lightTheme().color_scheme.primary == "#000000"


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
