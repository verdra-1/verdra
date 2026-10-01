# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Risk warning, explanation and destructive confirmation dialogs (7.8).

Master plan 7.8 and 4.3: buttons name the action and repeat the dialog's verb, never "OK" or
"Yes". A risk warning names the feature, explains the specific risk in two sentences, and turns
the feature on only after "I understand the risk" is ticked; Cancel is its default button.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Risk, RiskBadge

log = logging.getLogger(__name__)

WIDTH = 460


class _Dialog(QDialog):
    """Layout shared by the three dialogs: title, body, optional checkbox, two buttons."""

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setModal(True)
        self.setFixedWidth(WIDTH)
        tokens = theme.Tokens.load()
        self.layout_ = QVBoxLayout(self)
        padding = tokens.length("space-8")
        self.layout_.setContentsMargins(padding, padding, padding, padding)
        self.layout_.setSpacing(tokens.length("space-4"))
        self.title = QLabel(title, self)
        self.title.setWordWrap(True)
        theme.set_text_style(self.title, "title-m")
        self.layout_.addWidget(self.title)
        self.body = QLabel(body, self)
        self.body.setWordWrap(True)
        self.layout_.addWidget(self.body)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(tokens.length("space-2"))
        self.buttons.addStretch()
        self.cancel = QPushButton(QCoreApplication.translate("Dialogs", "Cancel"), self)
        self.cancel.clicked.connect(self.reject)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        """Write the dialog to Activity when it appears (Reference R5)."""
        super().showEvent(event)
        if not event.spontaneous():
            body = self.body.text() if self.body.isVisibleTo(self) else ""
            log.info("%s", f"{self.title.text()} {body}".strip())

    def _finish(self, confirm: QPushButton, *, cancel_first: bool) -> None:
        self.confirm = confirm
        confirm.clicked.connect(self.accept)
        self.buttons.addWidget(self.cancel)
        self.buttons.addWidget(confirm)
        self.layout_.addLayout(self.buttons)
        default = self.cancel if cancel_first else confirm
        default.setDefault(True)
        default.setFocus(Qt.FocusReason.OtherFocusReason)


class RiskWarning(_Dialog):
    """The Moderation-risk warning: tick "I understand the risk", then "Turn on" (M-RISK-01)."""

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(title, body, parent)
        self.layout_.insertWidget(
            1, RiskBadge(Risk.MODERATION, self), alignment=Qt.AlignmentFlag.AlignLeft
        )
        self.understood = QCheckBox(
            QCoreApplication.translate("M-RISK-01", "I understand the risk"), self
        )
        self.layout_.addWidget(self.understood)
        turn_on = QPushButton(QCoreApplication.translate("M-RISK-01", "Turn on"), self)
        turn_on.setProperty("primary", True)
        turn_on.setEnabled(False)
        self.understood.toggled.connect(turn_on.setEnabled)
        self._finish(turn_on, cancel_first=True)


class Explanation(_Dialog):
    """The Client-behaviour or Account-sensitive explanation before first use.

    Account-sensitive features also need a checkbox before "Continue" is enabled.
    """

    def __init__(
        self,
        title: str,
        body: str,
        *,
        confirm_text: str | None = None,
        account_sensitive: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, body, parent)
        risk = Risk.ACCOUNT_SENSITIVE if account_sensitive else Risk.CLIENT_BEHAVIOR
        self.layout_.insertWidget(1, RiskBadge(risk, self), alignment=Qt.AlignmentFlag.AlignLeft)
        go = QPushButton(confirm_text or QCoreApplication.translate("Dialogs", "Continue"), self)
        go.setProperty("primary", True)
        self.understood: QCheckBox | None = None
        if account_sensitive:
            self.understood = QCheckBox(QCoreApplication.translate("Dialogs", "I understand"), self)
            self.layout_.addWidget(self.understood)
            go.setEnabled(False)
            self.understood.toggled.connect(go.setEnabled)
        self._finish(go, cancel_first=account_sensitive)


class DestructiveConfirmation(_Dialog):
    """A question that names the object, with a button that repeats the verb ("Delete")."""

    def __init__(
        self, question: str, verb: str, body: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(question, body, parent)
        if not body:
            self.body.hide()
        self._finish(QPushButton(verb, self), cancel_first=True)
