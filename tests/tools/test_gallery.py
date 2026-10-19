# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/gallery.py: the pseudo-language and the law 1 check (design laws, decision 0027)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from tools import gallery


def test_short_strings_are_doubled_and_long_ones_grow_by_40_percent() -> None:
    assert gallery.pseudo("Apply now") == "Ápplý ñöw Ápplý ñöw"
    long = "Roblox is already running without Verdra."
    made = gallery.pseudo(long)
    assert len(made) >= len(long) * 1.4
    assert made.startswith(long.translate(gallery._ACCENTED))  # noqa: SLF001


@pytest.mark.parametrize(
    "text", ["Saved {count} of {total}", "Applied %n replacements", "<b>Bold</b> &amp; more"]
)
def test_placeholders_and_markup_survive(text: str) -> None:
    made = gallery.pseudo(text)
    for keep in ("{count}", "{total}", "%n", "<b>", "</b>", "&amp;"):
        if keep in text:
            assert keep in made


def test_the_pseudo_language_reaches_every_translated_string(qapp: QApplication) -> None:
    with gallery._pseudo_language(qapp, on=True):  # noqa: SLF001
        assert QCoreApplication.translate("M-APPLY-07", "Try again") == "Trý ágáîñ Trý ágáîñ"
    assert QCoreApplication.translate("M-APPLY-07", "Try again") == "Try again"


def findings(widget: QWidget) -> list[tuple[str, str]]:
    return [(f.kind, f.text) for f in gallery.cut_off(widget, "test", "scene")]


def test_a_squeezed_button_a_clipped_label_and_placeholder_are_found(qtbot: QtBot) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    row = QHBoxLayout(root)
    button = QPushButton("Close Roblox and continue", root)
    label = QLabel("A label far too long for the room it has", root)
    edit = QLineEdit(root)
    edit.setPlaceholderText("New profile name, as long as it gets")
    for widget in (button, label, edit):
        widget.setFixedWidth(40)
        row.addWidget(widget)
    root.show()
    qtbot.waitExposed(root)
    assert findings(root) == [
        ("button", "Close Roblox and continue"),
        ("label", "A label far too long for the room it has"),
        ("placeholder", "New profile name, as long as it gets"),
    ]


def test_text_with_room_and_wrapped_labels_with_height_pass(qtbot: QtBot) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    row = QHBoxLayout(root)
    row.addWidget(QPushButton("OK", root))
    wrapped = QLabel("A long sentence that wraps onto as many lines as it needs to.", root)
    wrapped.setWordWrap(True)
    row.addWidget(wrapped)
    root.resize(300, 200)
    root.show()
    qtbot.waitExposed(root)
    assert findings(root) == []


def test_a_wrapped_label_without_the_height_it_needs_is_found(qtbot: QtBot) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    wrapped = QLabel("A long sentence that wraps onto as many lines as it needs to. " * 3, root)
    wrapped.setWordWrap(True)
    wrapped.setGeometry(0, 0, 120, 20)
    root.resize(120, 20)
    root.show()
    qtbot.waitExposed(root)
    assert [kind for kind, _text in findings(root)] == ["wrapped label"]


def test_the_report_keeps_table_cells_apart_from_law_1() -> None:
    report = gallery.Report()
    report.findings = [
        gallery.Finding("c", "s", "cell", "QTableView", r"C:\Users\…\a.png", 400, 88),
        gallery.Finding("c", "s", "button", "QPushButton", "Close Roblox", 188, 181),
    ]
    assert [f.kind for f in report.law_one()] == ["button"]
    assert "1 findings break law 1; 1 table cells are shortened" in gallery.summary(report)
