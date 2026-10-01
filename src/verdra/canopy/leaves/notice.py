# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Inline notices: info, success, warning, danger.

A notice stays until what it reports is resolved (message catalogue, kind "Notice"). It always
carries an icon and words, never colour alone (Master plan 5.4), and is written to Activity when
shown.
"""

from __future__ import annotations

import logging
from enum import Enum

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from verdra.canopy.crown import theme

log = logging.getLogger(__name__)


class Tone(Enum):
    """A notice's tone: (icon, icon token, text token, fill token)."""

    INFO = ("info", "ink-muted", "ink", "surface-sunken")
    SUCCESS = ("circle-check", "success-ink", "success-ink", "success-tint")
    WARNING = ("triangle-alert", "warning-ink", "warning-ink", "warning-tint")
    DANGER = ("circle-x", "danger-ink", "danger-ink", "danger-tint")


class Notice(QFrame):
    """An inline notice with an icon and a sentence."""

    def __init__(
        self,
        text: str,
        tone: Tone = Tone.INFO,
        parent: QWidget | None = None,
        *,
        dismissible: bool = False,
    ) -> None:
        """Show `text`; with `dismissible`, a "Dismiss" button hides the notice for good.

        Use `dismissible` only for notices about something that is already over (a restored
        settings file); a notice about a state that lasts stays until the state ends.
        """
        super().__init__(parent)
        self.tone = tone
        self.setAccessibleName(text)
        tokens = theme.Tokens.load()
        layout = QHBoxLayout(self)
        padding = tokens.length("space-3")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-2"))
        self.icon = QLabel(self)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.icon)
        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label, 1)
        self.dismiss: QPushButton | None = None
        if dismissible:
            self.dismiss = QPushButton(QCoreApplication.translate("Notice", "Dismiss"), self)
            self.dismiss.setProperty("quiet", "true")
            self.dismiss.setAccessibleName(QCoreApplication.translate("Notice", "Dismiss"))
            self.dismiss.clicked.connect(self._dismissed)
            layout.addWidget(self.dismiss, 0, Qt.AlignmentFlag.AlignTop)
        current = theme.Theme.instance()
        if current is not None:
            current.changed.connect(self._restyle)
        self._restyle()
        level = {Tone.DANGER: logging.ERROR, Tone.WARNING: logging.WARNING}.get(tone, logging.INFO)
        log.log(level, "%s", text)

    def _dismissed(self) -> None:
        self.hide()
        self.deleteLater()

    def _restyle(self) -> None:
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        icon_name, icon_token, text_token, fill_token = self.tone.value
        fill = theme.css_color(tokens.color(fill_token, mode))
        ink = theme.css_color(tokens.color(text_token, mode))
        radius = tokens.length("radius-m")
        frame = f"Notice {{ background: {fill}; border-radius: {radius}px; }}"
        self.setStyleSheet(f"{frame} QLabel {{ color: {ink}; }}")
        self.icon.setPixmap(
            theme.icon_pixmap(
                icon_name, tokens.color(icon_token, mode), 20, self.devicePixelRatioF()
            )
        )
