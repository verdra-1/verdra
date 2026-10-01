# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the colour-literal gate."""

import pytest
from tools.check_colors import HEX_COLOR, PATTERNS, is_allowed

# Built at runtime so this file itself passes the gate.
H = "#"


def test_finds_hex_colors() -> None:
    colors = [H + "17705F", H + "fff", H + "0D3A31CC", H + "abcd"]
    line = "color: {}; background: {}; border: {}; x = '{}'".format(*colors)
    found = [match.group(0) for match in HEX_COLOR.finditer(line)]
    assert found == colors


def test_ignores_non_colors() -> None:
    for text in [
        "# comment",
        "issue " + H + "12345",
        "&" + H + "1234;",
        H + "ghijkl",
        "url#fragment",
    ]:
        assert not HEX_COLOR.search(text), text


def test_token_file_and_generated_svgs_are_allowed() -> None:
    assert is_allowed("src/verdra/assets/brand/tokens.json")
    assert is_allowed("src/verdra/assets/brand/symbol.svg")
    assert not is_allowed("src/verdra/canopy/crown/theme.py")


@pytest.mark.parametrize(
    "line",
    [
        'RED = "rgb(255, 0, 0)"',
        "QColor(255, 0, 0)",
        'QColor("red")',
        "painter.setPen(Qt.GlobalColor.red)",
        "brush = Qt.darkGray",
        "QLabel { color: red; }",
        "QWidget { background-color: White }",
        "hsl(120, 50%, 50%)",
        "hwb(120 10% 20%)",
        "lab(52% 40 60)",
        "lch(52% 72 56)",
        "oklab(0.6 0.1 0.1)",
        "oklch(0.7 0.15 150)",
        "color(srgb 1 0 0)",
        "QColor.fromRgb(255, 0, 0)",
        "QColor.fromRgbF(1.0, 0, 0)",
        "QColor.fromHsv(0, 255, 255)",
        'QColor.fromString("red")',
        "colour.setRgb(255, 0, 0)",
        'colour.setNamedColor("red")',
        "QColorConstants.Svg.red",
        "QColorConstants.Red",
        '<path fill="red" d="M0 0"/>',
        "<circle stroke='navy'/>",
        '<stop stop-color="gold"/>',
        "svg { fill: crimson; }",
    ],
)
def test_finds_other_color_literals(line: str) -> None:
    """Finding L1: colours written without hex digits are colour literals too."""
    assert any(pattern.search(line) for pattern in PATTERNS), line


@pytest.mark.parametrize(
    "line",
    [
        "pixmap.fill(Qt.GlobalColor.transparent)",
        'return f"rgba({colour.red()}, {colour.green()}, {colour.blue()}, {colour.alpha()})"',
        "QPushButton { background: {surface}; color: {ink}; border: none; }",
        "QColor(tokens.colour(name))",
        "the colour red-green pairing (plan 5.4)",
        "border-radius: {radius-m}px;",
        "QColor.fromString(tokens.colour(name))",
        "colour.setAlphaF(0.5)",
        '<path fill="none" stroke="currentColor"/>',
        'f\'<path fill="{ink}" d="{LEFT_LEAF}"/>\'',
        "the label's color: it follows the theme",
    ],
)
def test_ignores_tokens_and_words(line: str) -> None:
    assert not any(pattern.search(line) for pattern in PATTERNS), line
