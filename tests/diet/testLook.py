"""Ambrosia's look (AM7.1, AM7.3): black and shades leaning towards pink, gold and pink only in their own roles,
text, ticks and buttons pure grey."""

import dataclasses

from ambrosia.screens.look import darkAccents, darkShades, darkTheme, lightAccents, lightShades, lightTheme

textRoles = ("outline", "on_surface_variant", "on_surface", "primary", "on_primary")  # never gold or pink


def rgb(shade: str) -> tuple[int, int, int]:
    return int(shade[1:3], 16), int(shade[3:5], 16), int(shade[5:7], 16)


def testShadesAreBlackAndGreysLeaningTowardsPink():
    assert darkShades.keys() == lightShades.keys()
    for shades in (darkShades, lightShades):
        for role, shade in shades.items():
            red, green, blue = rgb(shade)
            if role in textRoles or role == "surface":
                assert red == green == blue, (role, shade)
            else:  # pink: red first, then blue, a tint only
                assert red >= blue >= green and red - green <= 40, (role, shade)
    assert (darkShades["surface"], lightShades["surface"]) == ("#000000", "#FFFFFF")


def testGoldAndPinkLiveInTheirOwnRoles():
    for accents, theme in ((darkAccents, darkTheme()), (lightAccents, lightTheme())):
        roles = {field.name for field in dataclasses.fields(theme.color_scheme)}
        assert set(accents) <= {name for name in roles if "tertiary" in name}
        for role, shade in accents.items():
            assert getattr(theme.color_scheme, role) == shade
        gold = rgb(accents["tertiary"])
        assert gold[0] > gold[1] > gold[2], "gold: red, then green, little blue"
        for role in ("tertiary_container", "tertiary_fixed", "tertiary_fixed_dim"):
            red, green, blue = rgb(accents[role])
            assert red > green and blue > green, (role, "pink: red and blue over green")
