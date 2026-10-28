# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The specimen row delegate: the pill words, and a size hint tall enough for a thumbnail."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QStyleOptionViewItem
from pytestqt.qtbot import QtBot

from verdra.canopy.screens.grafts import specimen
from verdra.canopy.screens.grafts.specimen import KIND, NAME, STATE, Pill, RowDelegate


def test_each_pill_has_its_own_word(qapp: QApplication) -> None:
    # Status is never shown by colour alone: every pill carries its word (0027 §4).
    assert specimen.pill_word(Pill.LIVE) == "Live"
    assert specimen.pill_word(Pill.DRAFT) == "Draft"
    assert specimen.pill_word(Pill.OFF) == "Off"


def test_the_row_is_tall_enough_for_a_thumbnail(qtbot: QtBot) -> None:
    view = QListWidget()
    qtbot.addWidget(view)
    delegate = RowDelegate(view)
    view.setItemDelegate(delegate)
    item = QListWidgetItem("Local file — top.png", view)
    item.setData(NAME, "15553230204")
    item.setData(KIND, "file")
    item.setData(STATE, Pill.LIVE.value)
    option = QStyleOptionViewItem()
    option.initFrom(view)
    index = view.model().index(0, 0)
    hint = delegate.sizeHint(option, index)
    assert hint.height() >= specimen.THUMB  # the before/after thumbnails fit the row
    assert hint.width() > specimen.THUMB * 2  # two thumbnails, the arrow, text and the pill


def test_an_unknown_state_falls_back_to_draft(qtbot: QtBot) -> None:
    view = QListWidget()
    qtbot.addWidget(view)
    item = QListWidgetItem("x", view)
    item.setData(STATE, "nonsense")
    index = view.model().index(0, 0)
    assert specimen._state(index) is Pill.DRAFT
    item.setData(STATE, None)
    assert specimen._state(index) is Pill.DRAFT
    item.setData(Qt.ItemDataRole.UserRole + 11, Pill.OFF.value)
    assert specimen._state(index) is Pill.OFF
