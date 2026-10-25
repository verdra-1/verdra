# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Middle-elides a path or link in a table column, keeping the file name (law 2).

Paths, links, asset names and log messages may shorten, and only in the middle, keeping the file
name ("C:\\Users\\…\\verdra-test-1600x900.png"), with the full text on hover and copyable
(docs/design/laws.md). `elide_path` does the shortening; `PathItemDelegate` paints a table column
with it and leaves the rest of the cell to the style.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)


def elide_path(text: str, metrics: QFontMetrics, width: int) -> str:
    """Return `text` shortened to `width`, keeping the last path or link segment whole.

    The part after the final "/" or "\\" (the file name) is kept whole and the rest is elided in
    the middle, so "C:\\Users\\Player\\Pictures\\verdra-test-1600x900.png" becomes
    "C:\\Users\\…\\verdra-test-1600x900.png". When even the file name alone doesn't fit, the whole
    text is elided in the middle instead (law 2 still: shorten in the middle, never the end).
    """
    if width <= 0 or metrics.horizontalAdvance(text) <= width:
        return text
    separator = max(text.rfind("/"), text.rfind("\\"))
    if separator <= 0:  # no path to speak of: middle-elide the whole thing
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, width)
    head, tail = text[:separator], text[separator:]  # tail keeps the separator and the file name
    tail_width = metrics.horizontalAdvance(tail)
    if tail_width >= width:  # the file name itself is too long to keep whole
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, width)
    return metrics.elidedText(head, Qt.TextElideMode.ElideMiddle, width - tail_width) + tail


class PathItemDelegate(QStyledItemDelegate):
    """Paints a table column's text with `elide_path` (law 2), the rest left to the style."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        shown = QStyleOptionViewItem(option)
        self.initStyleOption(shown, index)
        widget = shown.widget
        style = widget.style() if widget is not None else QApplication.style()
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, shown, widget)
        shown.text = elide_path(shown.text, shown.fontMetrics, text_rect.width())
        # The text is elided already; stop the style from eliding it a second time (at the end).
        shown.textElideMode = Qt.TextElideMode.ElideNone
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, shown, painter, widget)
