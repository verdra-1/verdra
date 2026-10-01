# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the colour-literal gate."""

from tools.check_colours import HEX_COLOUR, is_allowed

# Built at runtime so this file itself passes the gate.
H = "#"


def test_finds_hex_colours() -> None:
    colours = [H + "17705F", H + "fff", H + "0D3A31CC", H + "abcd"]
    line = "color: {}; background: {}; border: {}; x = '{}'".format(*colours)
    found = [match.group(0) for match in HEX_COLOUR.finditer(line)]
    assert found == colours


def test_ignores_non_colours() -> None:
    for text in [
        "# comment",
        "issue " + H + "12345",
        "&" + H + "1234;",
        H + "ghijkl",
        "url#fragment",
    ]:
        assert not HEX_COLOUR.search(text), text


def test_token_file_and_generated_svgs_are_allowed() -> None:
    assert is_allowed("src/verdra/assets/brand/tokens.json")
    assert is_allowed("src/verdra/assets/brand/symbol.svg")
    assert not is_allowed("src/verdra/canopy/crown/theme.py")
