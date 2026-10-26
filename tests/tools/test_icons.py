# SPDX-FileCopyrightText: 2026 q0f7
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
    colors = icons.load_colors()
    symbol = icons.svg_files()["symbol.svg"]
    assert colors["brand-canopy"]["light"] in symbol
    assert colors["brand-verdigris"]["light"] in symbol


def test_the_wordmark_has_no_node_dot_but_the_symbol_keeps_its_node() -> None:
    files = icons.svg_files()
    # Decision 0027 item 8: the node dot over the final "a" is removed from the wordmark and the
    # lockups everywhere. The symbol's own node (between the two leaves) stays.
    assert "<circle" not in files["wordmark.svg"]
    assert "<circle" not in files["wordmark-reversed.svg"]
    assert files["symbol.svg"].count("<circle") == 1
    # The lockup's only circle is the symbol's node, not a wordmark dot.
    assert files["lockup-horizontal.svg"].count("<circle") == 1


def test_the_status_leaf_has_every_state_in_both_themes() -> None:
    files = icons.svg_files()
    for state in icons.STATUS_LEAF_STATES:
        for theme in ("light", "dark"):
            assert f"leaf-{state}-{theme}.svg" in files


def test_each_status_leaf_state_reads_by_shape_not_only_colour() -> None:
    # Decision 0027 item 4: each state has its own shape so it reads in grayscale and contrast.
    files = icons.svg_files()
    working = files["leaf-working-light.svg"]
    waiting = files["leaf-waiting-light.svg"]
    off = files["leaf-off-light.svg"]
    needs_you = files["leaf-needs-you-light.svg"]
    stopped = files["leaf-stopped-light.svg"]
    # Working is solid (filled, no outline stroke); off is a hollow outline (stroked, no fill).
    assert 'fill="none"' not in working
    assert 'fill="none"' in off and "url(#lower-half)" not in off
    # Waiting is an outline with the lower half filled (a hard-edged vertical gradient).
    assert "url(#lower-half)" in waiting and 'fill="none"' in waiting
    # Needs-you and stopped add a bottom-right badge disc the others don't have.
    assert needs_you.count("<circle") > working.count("<circle")
    assert stopped.count("<circle") > working.count("<circle")


def test_the_status_leaf_colours_come_from_tokens() -> None:
    colors = icons.load_colors()
    files = icons.svg_files()
    assert colors["success"]["light"] in files["leaf-working-light.svg"]
    assert colors["warning"]["dark"] in files["leaf-needs-you-dark.svg"]
    assert colors["danger"]["light"] in files["leaf-stopped-light.svg"]
    assert colors["ink-muted"]["light"] in files["leaf-off-light.svg"]


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
