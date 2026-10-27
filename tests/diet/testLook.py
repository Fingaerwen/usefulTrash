"""Ambrosia's look (AM7.1, AM9): black and shades leaning towards pink, gold and pink only in their own roles,
text, ticks and buttons pure grey, dark only, corners round."""

import dataclasses

import flet as ft

from ambrosia.screens.look import card, darkAccents, darkShades, darkTheme, form, mainButton, pill

textRoles = ("outline", "on_surface_variant", "on_surface", "primary", "on_primary")  # never gold or pink


def rgb(shade: str) -> tuple[int, int, int]:
    return int(shade[1:3], 16), int(shade[3:5], 16), int(shade[5:7], 16)


def testShadesAreBlackAndGreysLeaningTowardsPink():
    for role, shade in darkShades.items():
        red, green, blue = rgb(shade)
        if role in textRoles or role == "surface":
            assert red == green == blue, (role, shade)
        else:  # pink: red first, then blue, a tint only
            assert red >= blue >= green and red - green <= 40, (role, shade)
    assert darkShades["surface"] == "#000000"


def testGoldAndPinkLiveInTheirOwnRoles():
    theme = darkTheme()
    roles = {field.name for field in dataclasses.fields(theme.color_scheme)}
    assert set(darkAccents) <= {name for name in roles if "tertiary" in name}
    for role, shade in darkAccents.items():
        assert getattr(theme.color_scheme, role) == shade
    gold = rgb(darkAccents["tertiary"])
    assert gold[0] > gold[1] > gold[2], "gold: red, then green, little blue"
    for role in ("tertiary_container", "tertiary_fixed", "tertiary_fixed_dim"):
        red, green, blue = rgb(darkAccents[role])
        assert red > green and blue > green, (role, "pink: red and blue over green")


def testCornersAreRoundAndCardsSeeThrough():
    """Ambrosia's half of the mirrored opposites (AM9.1): every corner well rounded, a card fading from its top
    right and see-through with a blur, so the goddess behind shows faintly."""
    panel = card(ft.Text("Breakfast"))
    assert isinstance(panel.shape, ft.RoundedRectangleBorder) and panel.shape.radius == form.corner
    assert panel.content.blur and panel.content.gradient.begin == ft.Alignment.TOP_RIGHT
    assert panel.content.border is None  # no top edge: that's Talon's
    assert isinstance(pill("3M").shape, ft.RoundedRectangleBorder)
    assert isinstance(mainButton("Save", None).style.shape, ft.RoundedRectangleBorder)
