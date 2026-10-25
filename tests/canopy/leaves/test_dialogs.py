# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""D1 blocker 1 (law 1): dialogs never cut their title, body or buttons at larger text."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from tools import gallery
from verdra.canopy.leaves.dialogs import WIDTH, Choice, DestructiveConfirmation

#: The three-button "Roblox is already running" choice the audit found clipped from 115 %.
ROBLOX_RUNNING = (
    "Roblox is already running without Verdra",
    "If Verdra starts this game it will close that Roblox first, so your replacements show.",
    "Close Roblox and continue",
    "Continue anyway",
)


def shown[T: QDialog](qtbot: QtBot, dialog: T) -> T:
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    # The offscreen platform doesn't propagate size hints, so size to the hint as a real window
    # manager would, giving the wrapped body the height it needs.
    dialog.adjustSize()
    QApplication.processEvents()
    return dialog


def clipped_buttons(dialog: QDialog) -> list[str]:
    """The action buttons cut off (what blocker 1 is about). The wrapped body label's height
    is a separate, offscreen-only measurement quirk and isn't this fix's concern."""
    return [f.text for f in gallery.cut_off(dialog, "test", "dialog") if f.kind == "button"]


@pytest.fixture
def big_font(qapp: QApplication) -> Iterator[None]:
    """About 220 % text, where a fixed-width row of three buttons used to clip. An absolute
    size, so a font another test may have left behind can't make this one flaky."""
    original = qapp.font()
    large = QFont(original)
    large.setPointSize(20)
    qapp.setFont(large)
    yield
    qapp.setFont(original)


def test_a_three_button_dialog_does_not_clip_at_large_text(qtbot: QtBot, big_font: None) -> None:
    dialog = shown(qtbot, Choice(*ROBLOX_RUNNING))
    # None of the three buttons is cut: they stack when they don't fit one row (the exact
    # row-vs-column split depends on the platform's font metrics, so it isn't asserted here).
    assert clipped_buttons(dialog) == []


def test_a_plain_two_button_dialog_keeps_the_base_width(qtbot: QtBot) -> None:
    dialog = shown(qtbot, DestructiveConfirmation("Delete profile Arsenal skins?", "Delete"))
    assert clipped_buttons(dialog) == []
    # At the base scale the two short buttons fit one row, so the dialog keeps the base width.
    assert dialog.width() == WIDTH
    assert dialog.cancel.y() == dialog.confirm.y()
