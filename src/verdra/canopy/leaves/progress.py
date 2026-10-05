# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Progress bar with leading leaf, arc spinner.

Master plan "UI language": progress is a straight, rounded bar whose fill grows with the `grow`
easing; for operations over two seconds a small leaf rides its leading edge. Indeterminate waits
under two seconds use a plain arc spinner. With reduced motion, the fill jumps and the spinner
holds still.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from verdra.canopy.crown import theme

BAR_HEIGHT = 6
LEAF_SIZE = 12
SPINNER_SIZE = 16


class ProgressBar(QWidget):
    """A determinate (0 to 100) or indeterminate (None) progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value: int | None = 0
        self._shown = 0.0
        self.show_leaf = False
        self._animation = QPropertyAnimation(self, b"shown", self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(self.tr("Progress"))

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the bar's natural size, leaving room for the leaf."""
        return QSize(200, LEAF_SIZE)

    def value(self) -> int | None:
        """Return the progress, or None when indeterminate."""
        return self._value

    def set_value(self, value: int | None) -> None:
        """Show progress from 0 to 100, or None for indeterminate."""
        self._value = value
        self.setAccessibleDescription("" if value is None else self.tr("{n}%").format(n=value))
        current = theme.Theme.instance()
        target = float(value or 0)
        self._animation.stop()
        if value is None or current is None or current.reduce_motion:
            self._set_shown(target)
            return
        self._animation.setDuration(current.tokens.duration("grow"))
        self._animation.setEasingCurve(current.tokens.easing("grow"))
        self._animation.setStartValue(self._shown)
        self._animation.setEndValue(target)
        self._animation.start()

    def _get_shown(self) -> float:
        return self._shown

    def _set_shown(self, value: float) -> None:
        self._shown = value
        self.update()

    shown = Property(float, _get_shown, _set_shown)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Draw track, fill and (for long operations) the leading leaf."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - BAR_HEIGHT) / 2
        track = QRectF(0, top, self.width(), BAR_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tokens.color("surface-sunken", mode))
        painter.drawRoundedRect(track, BAR_HEIGHT / 2, BAR_HEIGHT / 2)
        if self._value is not None:
            fill = QRectF(track)
            fill.setWidth(track.width() * self._shown / 100)
            painter.setBrush(tokens.color("primary", mode))
            painter.drawRoundedRect(fill, BAR_HEIGHT / 2, BAR_HEIGHT / 2)
            if self.show_leaf and self._shown > 0:
                leaf = theme.icon_pixmap(
                    "leaf", tokens.color("primary", mode), LEAF_SIZE, self.devicePixelRatioF()
                )
                x = max(0.0, min(fill.right() - LEAF_SIZE / 2, self.width() - LEAF_SIZE))
                painter.drawPixmap(int(x), int((self.height() - LEAF_SIZE) / 2), leaf)
        painter.end()


class Spinner(QWidget):
    """A plain arc spinner for waits under two seconds."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._turn)
        self.setFixedSize(SPINNER_SIZE, SPINNER_SIZE)
        self.setAccessibleName(self.tr("Working"))

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Turn only while visible and while motion is allowed."""
        current = theme.Theme.instance()
        if current is None or not current.reduce_motion:
            self._timer.start()

    def hideEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Stop turning when hidden, so an idle window uses no CPU."""
        self._timer.stop()

    def _turn(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Draw a quarter arc in primary."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(tokens.color("primary", mode), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.drawArc(rect, -self._angle * 16, 270 * 16)
        painter.end()
