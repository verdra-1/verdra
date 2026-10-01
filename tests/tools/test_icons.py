# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the icon generator (Master plan 4.4 and 4.6)."""

from pathlib import Path

import pytest

from tools import icons


def test_committed_svgs_are_up_to_date() -> None:
    for name, text in icons.svg_files().items():
        assert (icons.BRAND / name).read_text(encoding="utf-8") == text, name


def test_every_variant_from_4_4_exists() -> None:
    names = icons.svg_files().keys()
    for name in [
        "symbol.svg",
        "symbol-reversed.svg",
        "symbol-mono-dark.svg",
        "symbol-mono-light.svg",
        "app-icon.svg",
        "wordmark.svg",
    ]:
        assert name in names
    for state in icons.TRAY_STATES:
        assert {f"tray-{state}-light.svg", f"tray-{state}-template.svg"} <= names


def test_symbol_uses_brand_tokens() -> None:
    colours = icons.load_colours()
    symbol = icons.svg_files()["symbol.svg"]
    assert colours["brand-canopy"]["light"] in symbol
    assert colours["brand-verdigris"]["light"] in symbol


@pytest.mark.usefixtures("qapp")
def test_raster_set_has_every_size(tmp_path: Path) -> None:
    from PIL import Image

    icons.raster_files(icons.svg_files(), tmp_path)
    with Image.open(tmp_path / "windows" / "verdra.ico") as ico:
        assert set(ico.info["sizes"]) == {(s, s) for s in icons.WINDOWS_ICO}
    for size in icons.LINUX_HICOLOR:
        path = tmp_path / "linux" / "hicolor" / f"{size}x{size}" / "apps"
        (png,) = path.glob("*.png")
        with Image.open(png) as image:
            assert image.size == (size, size)
    assert (tmp_path / "macos" / "verdra.icns").stat().st_size > 0
    for size in icons.WINDOWS_TILES:
        assert (tmp_path / "windows" / f"tile-{size}.png").is_file()
    with Image.open(tmp_path / "tray" / "macos" / "RoutingTemplate@2x.png") as image:
        assert image.size == (36, 36)
