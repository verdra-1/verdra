# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The custom icon set of Master plan 6.8, each with its hand-tuned 16 px variant (finding L3)."""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from verdra.canopy.crown import theme

CUSTOM = Path(theme.ASSETS) / "icons" / "custom"
#: Plan 6.8: the sidebar's custom icons and the other custom icons.
PLAN_ICONS = ["graft", "seed", "tweaks", "leaf", "node", "vine", "seedling"]


@pytest.mark.parametrize("name", PLAN_ICONS)
def test_each_custom_icon_has_a_hand_tuned_16_px_variant(name: str) -> None:
    for path, grid, stroke in (
        (CUSTOM / f"{name}.svg", 24, "2"),
        (CUSTOM / "16" / f"{name}.svg", 16, "1.5"),
    ):
        text = path.read_text(encoding="utf-8")
        assert f'viewBox="0 0 {grid} {grid}"' in text, path
        assert f'stroke-width="{stroke}"' in text, path
        assert 'stroke="currentColor"' in text and not re.search(r"#[0-9A-Fa-f]{3,6}", text), path
        assert QSvgRenderer(QByteArray(text.encode("utf-8"))).isValid(), path


def test_small_sizes_use_the_16_px_variant(qapp: QApplication) -> None:
    ink = theme.Tokens.load().color("ink", "light")
    small = theme.icon_pixmap("leaf", ink, 16).toImage()
    from_24 = QSvgRenderer(QByteArray((CUSTOM / "leaf.svg").read_bytes()))
    assert from_24.isValid()
    assert theme._icon_source("leaf", True) == (CUSTOM / "16" / "leaf.svg").read_text(
        encoding="utf-8"
    )  # noqa: SLF001
    assert theme._icon_source("leaf", False) == (CUSTOM / "leaf.svg").read_text(encoding="utf-8")  # noqa: SLF001
    assert not small.isNull()
