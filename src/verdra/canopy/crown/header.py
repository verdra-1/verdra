# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Screen title, status pill and its popover, profile selector, Apply now button.

Master plan 7.1. The header is 56 px tall. Until routing exists (M1) the pill shows Idle and its
popover explains it (M-STATUS-03); until replacements exist (M2) the profile selector and
"Apply now" are disabled with a tooltip saying why (plan 5.4, rule 5).
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Status, StatusPill
from verdra.canopy.leaves.empty import soon

POPOVER_WIDTH = 300


class StatusPopover(QFrame):
    """The popover under the status pill: the reason and at most one fix button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("popover", True)
        self.setFixedWidth(POPOVER_WIDTH)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        padding = tokens.length("space-4")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-2"))
        self.title = QLabel(self)
        theme.set_text_style(self.title, "body-strong")
        layout.addWidget(self.title)
        self.reason = QLabel(self)
        self.reason.setWordWrap(True)
        self.reason.setProperty("muted", True)
        layout.addWidget(self.reason)
        self.fix = QPushButton(self)
        layout.addWidget(self.fix, alignment=Qt.AlignmentFlag.AlignLeft)
        self.show_status(Status.IDLE)

    def show_status(self, status: Status) -> None:
        """Fill the popover for a status."""
        if status is Status.IDLE:
            # M-STATUS-03: "Idle. Routing is off." Button "Start routing".
            self.title.setText(status.label())
            self.reason.setText(QCoreApplication.translate("M-STATUS-03", "Routing is off."))
            self.fix.setText(QCoreApplication.translate("M-STATUS-03", "Start routing"))
            self.fix.setEnabled(False)
            self.fix.setToolTip(soon())
        self.fix.setAccessibleName(self.fix.text())


class Header(QFrame):
    """The window header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        tokens = theme.Tokens.load()
        self.setFixedHeight(tokens.length("header-height"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.length("space-6"), 0, tokens.length("space-6"), 0)
        layout.setSpacing(tokens.length("space-3"))

        self.title = QLabel(self)
        theme.set_text_style(self.title, "title-l")
        layout.addWidget(self.title)
        layout.addStretch()

        self.pill = StatusPill(self)
        self.pill.clicked.connect(self.open_popover)
        layout.addWidget(self.pill)
        self.popover = StatusPopover(self)

        not_yet = soon()
        self.profiles = QComboBox(self)
        self.profiles.setMinimumWidth(180)
        self.profiles.setPlaceholderText(self.tr("No profiles"))
        self.profiles.setAccessibleName(self.tr("Active profile"))
        self.profiles.setEnabled(False)
        self.profiles.setToolTip(not_yet)
        layout.addWidget(self.profiles)

        self.apply_now = QPushButton(self.tr("Apply now"), self)
        self.apply_now.setProperty("primary", True)
        self.apply_now.setAccessibleName(self.tr("Apply now"))
        self.apply_now.setEnabled(False)
        self.apply_now.setToolTip(not_yet)
        layout.addWidget(self.apply_now)

    def set_title(self, title: str) -> None:
        """Show the current screen's title."""
        self.title.setText(title)

    def set_status(self, status: Status) -> None:
        """Show a routing status in the pill and its popover."""
        self.pill.set_status(status)
        self.popover.show_status(status)

    def open_popover(self) -> None:
        """Open the status popover under the pill."""
        anchor = self.pill.mapToGlobal(
            QPoint(self.pill.width() - POPOVER_WIDTH, self.pill.height() + 4)
        )
        self.popover.move(anchor)
        self.popover.show()
        self.popover.fix.setFocus()
