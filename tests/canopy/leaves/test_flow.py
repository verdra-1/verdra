# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The flow layout wraps its items instead of clipping them (law 1, D1 #16)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from verdra.canopy.leaves.flow import FlowLayout


def _host(qtbot: QtBot, count: int) -> tuple[QWidget, FlowLayout, list[QPushButton]]:
    host = QWidget()
    qtbot.addWidget(host)
    flow = FlowLayout(host, spacing=8)
    buttons = [QPushButton("A toolbar button", host) for _ in range(count)]
    for button in buttons:
        flow.addWidget(button)
    host.show()
    qtbot.waitExposed(host)
    return host, flow, buttons


def test_items_sit_on_one_line_when_there_is_room(qtbot: QtBot) -> None:
    host, _flow, buttons = _host(qtbot, 3)
    host.resize(2000, 200)
    QApplication.processEvents()
    tops = {b.y() for b in buttons}
    assert len(tops) == 1  # all on the same line
    # Each button keeps its own natural width (nothing is shrunk below its hint).
    for button in buttons:
        assert button.width() >= button.sizeHint().width()


def test_items_wrap_to_more_lines_when_narrow(qtbot: QtBot) -> None:
    host, flow, buttons = _host(qtbot, 4)
    one = buttons[0].sizeHint().width()
    host.resize(one + 20, 400)  # room for one button per line
    QApplication.processEvents()
    tops = sorted({b.y() for b in buttons})
    assert len(tops) >= 3  # it wrapped onto several lines rather than clipping
    # The layout asks for the taller height it needs at this width (heightForWidth).
    assert flow.heightForWidth(one + 20) > flow.heightForWidth(2000)
    # No button is narrower than its natural width: a label is never cut (law 1).
    for button in buttons:
        assert button.width() >= button.sizeHint().width()
