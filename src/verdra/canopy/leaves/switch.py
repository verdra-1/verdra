# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Pill switch with the leaf glyph on the thumb when on.

The switch keeps the standard pill shape so people recognise it at once; position and colour
carry its meaning, and the small leaf on the thumb is decoration only (brand system, "UI
language"). The thumb moves with the `quick` motion token, or jumps under reduced motion.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from verdra.canopy.crown import theme

TRACK_WIDTH, TRACK_HEIGHT = 36, 20
THUMB_MARGIN = 3
LEAF_SIZE = 10


class Switch(QAbstractButton):
    """An on/off switch. Give it an accessible name; its label usually sits beside it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self.toggled.connect(self._move)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the switch's size, with room for the focus ring."""
        return QSize(TRACK_WIDTH + 6, TRACK_HEIGHT + 6)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        """Set the state without animating (used when loading values)."""
        super().setChecked(checked)
        self._animation.stop()
        self._set_position(1.0 if checked else 0.0)

    def _move(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        current = theme.Theme.instance()
        self._animation.stop()
        if current is None or current.reduce_motion:
            self._set_position(target)
            return
        self._animation.setDuration(current.tokens.duration("quick"))
        self._animation.setEasingCurve(current.tokens.easing("quick"))
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Draw track, thumb and focus ring from tokens."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        enabled = self.isEnabled()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(3, 3, TRACK_WIDTH, TRACK_HEIGHT)
        radius = TRACK_HEIGHT / 2
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tokens.color("primary" if enabled else "ink-disabled", mode))
        else:
            border = "border-strong" if enabled else "divider"
            painter.setPen(QPen(tokens.color(border, mode), 1))
            painter.setBrush(tokens.color("surface-sunken", mode))
        painter.drawRoundedRect(track, radius, radius)
        diameter = TRACK_HEIGHT - 2 * THUMB_MARGIN
        travel = TRACK_WIDTH - 2 * THUMB_MARGIN - diameter
        thumb = QRectF(
            track.left() + THUMB_MARGIN + travel * self._position,
            track.top() + THUMB_MARGIN,
            diameter,
            diameter,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        on_color = tokens.color("on-primary", mode)
        off_color = tokens.color("border-strong" if enabled else "divider", mode)
        painter.setBrush(on_color if self.isChecked() else off_color)
        painter.drawEllipse(thumb)
        if self.isChecked() and self._position > 0.9:
            leaf = theme.icon_pixmap(
                "leaf", tokens.color("primary", mode), LEAF_SIZE, self.devicePixelRatioF()
            )
            center = thumb.center()
            painter.drawPixmap(
                int(center.x() - LEAF_SIZE / 2), int(center.y() - LEAF_SIZE / 2), leaf
            )
        if self.hasFocus():
            painter.setPen(QPen(tokens.color("focus-ring", mode), tokens.length("focus-width")))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            ring = track.adjusted(-2, -2, 2, 2)
            painter.drawRoundedRect(ring, ring.height() / 2, ring.height() / 2)
        painter.end()
