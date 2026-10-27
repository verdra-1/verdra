# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The header wraps to a taller second row at large text so nothing is cut (D1 blocker 4, law 1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tools import gallery
from verdra.canopy.crown.header import Header

KINDS = ("label", "button", "combo", "placeholder")


@pytest.fixture
def big_font(qapp: QApplication) -> Iterator[None]:
    """About 220 % text, where the title and controls no longer fit one row in a narrow window."""
    original = qapp.font()
    large = QFont(original)
    large.setPointSize(22)
    qapp.setFont(large)
    yield
    qapp.setFont(original)


def clipped(header: Header) -> list[str]:
    return [f.text for f in gallery.cut_off(header, "test", "header") if f.kind in KINDS]


def shown(qtbot: QtBot, header: Header, width: int) -> Header:
    qtbot.addWidget(header)
    header.show()
    qtbot.waitExposed(header)
    header.resize(width, header.height())
    for _ in range(3):
        QApplication.processEvents()
    return header


def test_wide_window_keeps_one_row(qtbot: QtBot, big_font: None) -> None:
    header = Header()
    header.set_title("Replacements")
    shown(qtbot, header, 1200)
    assert header._two_row is False
    assert clipped(header) == []


def test_narrow_window_wraps_to_a_taller_header(qtbot: QtBot, big_font: None) -> None:
    header = Header()
    header.set_title("Replacements")
    one_row = Header()
    one_row.set_title("Replacements")
    shown(qtbot, one_row, 1200)
    # The window pins the header narrower than the title and status light need side by side.
    qtbot.addWidget(header)
    header.setFixedWidth(300)
    header.show()
    qtbot.waitExposed(header)
    for _ in range(3):
        QApplication.processEvents()
    assert header._two_row is True
    assert header.height() > one_row.height()  # it grew taller for the second row
    assert clipped(header) == []  # title and controls both fit now


def test_normal_text_is_a_single_row(qtbot: QtBot) -> None:
    header = Header()
    header.set_title("Replacements")
    shown(qtbot, header, 1200)
    assert header._two_row is False
    assert clipped(header) == []
