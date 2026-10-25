# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The sidebar grows so a nav label is never cut off at larger text (D1 blocker 4, law 1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tools import gallery
from verdra.canopy.crown.sidebar import Sidebar


@pytest.fixture
def big_font(qapp: QApplication) -> Iterator[None]:
    """About 260 % text, where "Replacements" no longer fits the 220 px design width."""
    original = qapp.font()
    large = QFont(original)
    large.setPointSize(26)
    qapp.setFont(large)
    yield
    qapp.setFont(original)


def shown(qtbot: QtBot, bar: Sidebar) -> Sidebar:
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    layout = bar.layout()
    assert layout is not None
    layout.activate()
    QApplication.processEvents()
    return bar


def test_the_expanded_sidebar_fits_its_labels_at_large_text(qtbot: QtBot, big_font: None) -> None:
    bar = shown(qtbot, Sidebar())
    assert not bar.collapsed
    assert bar.width() > bar._base_width  # it grew past the design width
    clipped = [f.text for f in gallery.cut_off(bar, "test", "sidebar") if f.kind == "button"]
    assert clipped == []


def test_collapsing_still_goes_to_the_icon_width(qtbot: QtBot, big_font: None) -> None:
    bar = shown(qtbot, Sidebar())
    bar.set_collapsed(True)
    assert bar.width() == bar.collapsed_width  # icons only, whatever the text size
    bar.set_collapsed(False)
    assert bar.width() == bar.expanded_width > bar._base_width


def test_small_text_keeps_the_design_width(qtbot: QtBot, qapp: QApplication) -> None:
    """When the labels fit, the sidebar keeps its design width and never shrinks below it."""
    original = qapp.font()
    small = QFont(original)
    small.setPointSize(6)  # labels fit comfortably within the 220 px design width
    qapp.setFont(small)
    try:
        bar = shown(qtbot, Sidebar())
        assert bar.width() == bar._base_width
    finally:
        qapp.setFont(original)
