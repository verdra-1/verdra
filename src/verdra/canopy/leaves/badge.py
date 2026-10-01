# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Risk badges (four levels) and status pills (four states).

Master plan 5.5 and 7.1. Status is never shown by colour alone: a pill always carries an icon and
a word, and a badge always carries its label.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from verdra.canopy.crown import theme


class Status(Enum):
    """Routing status as the header and tray show it."""

    IDLE = "idle"
    ROUTING = "routing"
    DEGRADED = "degraded"
    ERROR = "error"

    def label(self) -> str:
        """Return the status word."""
        words = {
            Status.IDLE: QCoreApplication.translate("Status", "Idle"),
            Status.ROUTING: QCoreApplication.translate("Status", "Routing"),
            Status.DEGRADED: QCoreApplication.translate("Status", "Degraded"),
            Status.ERROR: QCoreApplication.translate("Status", "Error"),
        }
        return words[self]


# (icon, color token for icon and text, fill token)
_STATUS_LOOK = {
    Status.IDLE: ("circle-alert", "ink-muted", "surface-sunken"),
    Status.ROUTING: ("circle-check", "success-ink", "success-tint"),
    Status.DEGRADED: ("triangle-alert", "warning-ink", "warning-tint"),
    Status.ERROR: ("circle-x", "danger-ink", "danger-tint"),
}


class Risk(Enum):
    """The four risk levels (Master plan 2 and 5.5)."""

    COSMETIC = "cosmetic"
    CLIENT_BEHAVIOR = "client_behavior"
    ACCOUNT_SENSITIVE = "account_sensitive"
    MODERATION = "moderation"

    def label(self) -> str:
        """Return the badge label (M-RISK-02)."""
        words = {
            Risk.COSMETIC: QCoreApplication.translate("M-RISK-02", "Cosmetic"),
            Risk.CLIENT_BEHAVIOR: QCoreApplication.translate("M-RISK-02", "Client behavior"),
            Risk.ACCOUNT_SENSITIVE: QCoreApplication.translate("M-RISK-02", "Account-sensitive"),
            Risk.MODERATION: QCoreApplication.translate("M-RISK-02", "Moderation risk"),
        }
        return words[self]


# (text token, fill token, border token or None)
_RISK_LOOK = {
    Risk.COSMETIC: ("ink", "primary-tint", None),
    Risk.CLIENT_BEHAVIOR: ("ink", "surface-sunken", "border-strong"),
    Risk.ACCOUNT_SENSITIVE: ("warning-ink", "warning-tint", None),
    Risk.MODERATION: ("danger-ink", "danger-tint", None),
}


class StatusPill(QWidget):
    """A rounded pill with the status icon and word; a click opens its popover.

    Signals:
        clicked(): The pill was clicked or activated with the keyboard.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = Status.IDLE
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        theme.set_text_style(self, "body-strong")
        self.set_status(Status.IDLE)

    @property
    def status(self) -> Status:
        """Return the status shown."""
        return self._status

    def set_status(self, status: Status) -> None:
        """Show a status."""
        self._status = status
        label = QCoreApplication.translate("StatusPill", "Routing status: {status}").format(
            status=status.label()
        )
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the pill's natural size."""
        width = self.fontMetrics().horizontalAdvance(self._status.label())
        return QSize(width + 16 + 8 + 24, 28)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        """Treat a left-button release inside the pill as activation, like a button."""
        inside = self.rect().contains(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and inside:
            self.clicked.emit()

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Activate with Space or Enter, like a button."""
        key = getattr(event, "key", lambda: None)()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Draw the pill from tokens."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        icon_name, ink, fill = _STATUS_LOOK[self._status]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tokens.color(fill, mode))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        pixmap = theme.icon_pixmap(icon_name, tokens.color(ink, mode), 16, self.devicePixelRatioF())
        painter.drawPixmap(int(rect.left()) + 10, int(rect.center().y()) - 8, pixmap)
        painter.setPen(tokens.color(ink, mode))
        text_rect = rect.adjusted(10 + 16 + 6, 0, -10, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self._status.label())
        if self.hasFocus():
            pen = QPen(tokens.color("focus-ring", mode), tokens.length("focus-width"))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(outer, outer.height() / 2, outer.height() / 2)
        painter.end()


class RiskBadge(QWidget):
    """A risk badge: the label in `label` style, uppercase, 2 × 6 px padding, radius-s."""

    def __init__(self, risk: Risk, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.risk = risk
        theme.set_text_style(self, "label")
        self.setAccessibleName(
            QCoreApplication.translate("RiskBadge", "Risk: {level}").format(level=risk.label())
        )
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the badge's natural size."""
        metrics = self.fontMetrics()
        return QSize(
            metrics.horizontalAdvance(self.risk.label().upper()) + 12, metrics.height() + 4
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Draw the badge from tokens."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        ink, fill, border = _RISK_LOOK[self.risk]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(tokens.color(fill, mode))
        painter.setPen(QPen(tokens.color(border, mode), 1) if border else Qt.PenStyle.NoPen)
        radius = tokens.length("radius-s")
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(tokens.color(ink, mode))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.risk.label())
        painter.end()
