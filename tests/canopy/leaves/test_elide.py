# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Design law 2: paths and links shorten in the middle, keeping the file name whole."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from verdra.canopy.leaves.elide import PathItemDelegate, elide_path

WINDOWS_PATH = r"C:\Users\Player\Pictures\Verdra tests\verdra-test-1600x900.png"
LINK = "https://example.com/textures/brick-wall-weathered-2048.png"


def test_text_that_fits_is_returned_whole(qapp: QApplication) -> None:
    font = QFontMetrics(qapp.font())
    assert elide_path(WINDOWS_PATH, font, 100_000) == WINDOWS_PATH


def test_a_path_keeps_its_file_name_and_elides_the_middle(qapp: QApplication) -> None:
    font = QFontMetrics(qapp.font())
    name = "verdra-test-1600x900.png"
    width = font.horizontalAdvance(name) + 80  # room for the name and a little of the folders
    shown = elide_path(WINDOWS_PATH, font, width)
    assert "…" in shown  # it was shortened
    assert shown.endswith(name)  # the file name is kept whole
    assert shown.startswith("C:")  # and the start is kept, so the middle is what's dropped
    assert font.horizontalAdvance(shown) <= width


def test_a_link_keeps_its_last_segment(qapp: QApplication) -> None:
    font = QFontMetrics(qapp.font())
    name = "brick-wall-weathered-2048.png"
    width = font.horizontalAdvance(name) + 40
    shown = elide_path(LINK, font, width)
    assert shown.endswith(name)
    assert "…" in shown


def test_without_a_separator_it_falls_back_to_a_middle_elide(qapp: QApplication) -> None:
    font = QFontMetrics(qapp.font())
    text = "an asset name with no path separators at all in it"
    shown = elide_path(text, font, font.horizontalAdvance(text) // 2)
    assert shown.startswith("an") and shown.endswith("it") and "…" in shown


def test_when_even_the_file_name_cannot_fit_the_text_is_still_middle_elided(
    qapp: QApplication,
) -> None:
    font = QFontMetrics(qapp.font())
    # Too narrow for the file name alone: law 2 still shortens in the middle (keeps both ends),
    # never at the end alone.
    shown = elide_path(WINDOWS_PATH, font, 40)
    assert shown.startswith("C") and "…" in shown
    assert font.horizontalAdvance(shown) <= 40


def test_the_delegate_paints_a_narrow_cell_without_error(qapp: QApplication) -> None:
    """The delegate shortens and draws a long path in a cell narrower than it (law 2)."""
    table = QTableWidget(1, 1)
    table.setItemDelegateForColumn(0, PathItemDelegate(table))
    table.setItem(0, 0, QTableWidgetItem(WINDOWS_PATH))
    index = table.model().index(0, 0)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # far narrower than the path
    pixmap = QPixmap(120, 24)
    painter = QPainter(pixmap)
    table.itemDelegateForColumn(0).paint(painter, option, index)
    painter.end()
    assert not pixmap.isNull()
    table.deleteLater()
