# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Paints a replacement as a specimen row: before/after thumbnails, the asset ID and its target,
and a Live/Draft/Off pill (D3 screen 2).

The thumbnails are placeholders: Verdra has no rendered preview of an asset yet, so a row shows an
empty before/after frame rather than imply a preview it can't draw (real previews are Editor 2.0
Part B). The asset ID is the primary line and the target is the caption, which may shorten in the
middle with the full text on hover and copyable (law 2); the pill never stands on colour alone, it
always carries its word (plan 7.1, decision 0027 §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from verdra.canopy.crown import theme
from verdra.canopy.leaves.elide import elide_path

#: Item data roles the delegate reads (the caption is the display role, so its law-2 elision is
#: the view's business and the gallery lists it apart).
NAME = Qt.ItemDataRole.UserRole + 10
STATE = Qt.ItemDataRole.UserRole + 11
KIND = Qt.ItemDataRole.UserRole + 12
RID = Qt.ItemDataRole.UserRole + 13

THUMB = 44
_ARROW = "→"


class Pill(Enum):
    """Whether a replacement is serving now, only saved, or turned off."""

    LIVE = "live"
    DRAFT = "draft"
    OFF = "off"


# (fill token, ink token, whether to draw the leading dot)
_PILL_LOOK = {
    Pill.LIVE: ("success-tint", "success-ink", True),
    Pill.DRAFT: ("surface-sunken", "ink-muted", False),
    Pill.OFF: ("surface-sunken", "ink-muted", False),
}


@dataclass(frozen=True)
class _Ink:
    """The painter and the tokens for the current theme, passed around while painting a row."""

    painter: QPainter
    tokens: Any
    mode: theme.Mode


def pill_word(state: Pill) -> str:
    """Return the pill's word (never shown by colour alone)."""
    from PySide6.QtCore import QCoreApplication  # noqa: PLC0415

    words = {
        Pill.LIVE: QCoreApplication.translate("Replacements", "Live"),
        Pill.DRAFT: QCoreApplication.translate("Replacements", "Draft"),
        Pill.OFF: QCoreApplication.translate("Replacements", "Off"),
    }
    return words[state]


class RowDelegate(QStyledItemDelegate):
    """Paints each replacement row: before/after thumbnails, asset ID, target, and the pill."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        tokens = theme.Tokens.load()
        self._pad = tokens.length("space-4")
        self._gap = tokens.length("space-4")
        self._vpad = tokens.length("space-3")
        self._line_gap = tokens.length("space-1")

    # --- Geometry ---------------------------------------------------------------------------

    def _tokens(self) -> tuple[Any, theme.Mode]:
        current = theme.Theme.instance()
        if current is not None:
            return current.tokens, current.mode
        return theme.Tokens.load(), "light"

    def _pill_width(self, option: QStyleOptionViewItem, state: Pill) -> int:
        metrics = option.fontMetrics
        _fill, _ink, dot = _PILL_LOOK[state]
        word = metrics.horizontalAdvance(pill_word(state))
        return word + 2 * self._pad + (14 if dot else 0)

    def sizeHint(  # noqa: N802 - Qt API
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        shown = QStyleOptionViewItem(option)
        self.initStyleOption(shown, index)
        metrics = shown.fontMetrics
        state = _state(index)
        # The row fills the viewport width; only the fixed parts and the asset ID (not free-length,
        # law 1) are reserved, so the row never forces a horizontal scrollbar for a long caption.
        # The caption (free-length) shortens in the painted text area instead (law 2).
        name = metrics.horizontalAdvance(str(index.data(NAME) or ""))
        width = (
            self._pad
            + THUMB
            + self._gap
            + metrics.horizontalAdvance(_ARROW)
            + self._gap
            + THUMB
            + self._gap
            + name
            + self._gap
            + self._pill_width(shown, state)
            + self._pad
        )
        return QSize(width, THUMB + 2 * self._vpad)

    # --- Painting ---------------------------------------------------------------------------

    def paint(  # noqa: N802 - Qt API
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        shown = QStyleOptionViewItem(option)
        self.initStyleOption(shown, index)
        tokens, mode = self._tokens()
        ink = _Ink(painter, tokens, mode)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = shown.rect
        self._paint_background(ink, shown, rect)

        kind = str(index.data(KIND) or "")
        x = rect.left() + self._pad
        mid = rect.center().y()
        self._thumb(ink, QRect(x, mid - THUMB // 2, THUMB, THUMB), empty=False)
        x += THUMB + self._gap
        painter.setPen(tokens.color("ink-muted", mode))
        arrow_w = shown.fontMetrics.horizontalAdvance(_ARROW)
        painter.drawText(
            QRect(x, rect.top(), arrow_w, rect.height()),
            Qt.AlignmentFlag.AlignVCenter,
            _ARROW,
        )
        x += arrow_w + self._gap
        # Remove shows nothing in game, so its "after" frame is empty surface, not a sunken thumb.
        self._thumb(ink, QRect(x, mid - THUMB // 2, THUMB, THUMB), empty=kind == "remove")
        x += THUMB + self._gap

        state = _state(index)
        pill_w = self._pill_width(shown, state)
        pill_rect = QRect(rect.right() - self._pad - pill_w, mid - 11, pill_w, 22)
        self._pill(ink, pill_rect, state)

        grow = QRect(x, rect.top(), pill_rect.left() - self._gap - x, rect.height())
        self._text(ink, grow, index, shown.fontMetrics)
        painter.restore()

    def _paint_background(self, ink: _Ink, option: QStyleOptionViewItem, rect: QRect) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            ink.painter.fillRect(rect, ink.tokens.color("primary-tint", ink.mode))
        if option.state & QStyle.StateFlag.State_HasFocus:
            pen = QPen(ink.tokens.color("focus-ring", ink.mode), ink.tokens.length("focus-width"))
            ink.painter.setPen(pen)
            ink.painter.setBrush(Qt.BrushStyle.NoBrush)
            ink.painter.drawRect(QRectF(rect).adjusted(1, 1, -1, -1))

    def _thumb(self, ink: _Ink, box: QRect, *, empty: bool) -> None:
        fill = "surface" if empty else "surface-sunken"
        ink.painter.setPen(QPen(ink.tokens.color("divider", ink.mode), 1))
        ink.painter.setBrush(ink.tokens.color(fill, ink.mode))
        radius = ink.tokens.length("radius-s")
        ink.painter.drawRoundedRect(QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    def _text(
        self, ink: _Ink, area: QRect, index: QModelIndex | QPersistentModelIndex, metrics: Any
    ) -> None:
        if area.width() <= 0:
            return
        painter = ink.painter
        name = str(index.data(NAME) or "")
        caption = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        line = metrics.height()
        top = area.center().y() - line - self._line_gap // 2
        painter.setPen(ink.tokens.color("ink", ink.mode))
        bold = painter.font()
        bold.setBold(True)
        painter.setFont(bold)
        painter.drawText(
            QRect(area.left(), top, area.width(), line),
            Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(name, Qt.TextElideMode.ElideRight, area.width()),
        )
        plain = painter.font()
        plain.setBold(False)
        painter.setFont(plain)
        painter.setPen(ink.tokens.color("ink-muted", ink.mode))
        painter.drawText(
            QRect(area.left(), top + line + self._line_gap, area.width(), line),
            Qt.AlignmentFlag.AlignVCenter,
            elide_path(caption, metrics, area.width()),
        )

    def _pill(self, ink: _Ink, box: QRect, state: Pill) -> None:
        painter = ink.painter
        fill, text_ink, dot = _PILL_LOOK[state]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink.tokens.color(fill, ink.mode))
        painter.drawRoundedRect(QRectF(box), box.height() / 2, box.height() / 2)
        left = box.left() + self._pad
        if dot:
            size = 8
            painter.setBrush(ink.tokens.color("success", ink.mode))
            painter.drawEllipse(left, box.center().y() - size // 2, size, size)
            left += size + 6
        painter.setPen(ink.tokens.color(text_ink, ink.mode))
        painter.drawText(
            QRect(left, box.top(), box.right() - left, box.height()),
            Qt.AlignmentFlag.AlignVCenter,
            pill_word(state),
        )


def _state(index: QModelIndex | QPersistentModelIndex) -> Pill:
    value = str(index.data(STATE) or Pill.DRAFT.value)
    return Pill(value) if value in {p.value for p in Pill} else Pill.DRAFT
