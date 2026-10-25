# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Risk warning, explanation and destructive confirmation dialogs (7.8).

Master plan 7.8 and 4.3: buttons name the action and repeat the dialog's verb, never "OK" or
"Yes". A risk warning names the feature, explains the specific risk in two sentences, and turns
the feature on only after "I understand the risk" is ticked; Cancel is its default button.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

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
        tokens = theme.Tokens.load()
        self._padding = tokens.length("space-8")
        self._spacing = tokens.length("space-2")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(self._padding, self._padding, self._padding, self._padding)
        self.layout_.setSpacing(tokens.length("space-4"))
        self.title = QLabel(title, self)
        self.title.setWordWrap(True)
        theme.set_text_style(self.title, "title-m")
        self.layout_.addWidget(self.title)
        self.body = QLabel(body, self)
        self.body.setWordWrap(True)
        self.layout_.addWidget(self.body)
        #: The action buttons, left to right as they appear in one row (law 1: never clipped).
        self._action_buttons: list[QPushButton] = []
        self.cancel = QPushButton(QCoreApplication.translate("Dialogs", "Cancel"), self)
        self.cancel.clicked.connect(self.reject)
        # Detailed logging only: Activity shows a dialog when it appears; this line says how it
        # was answered (Stage 2 on Windows showed M-SHELL-02 twice and couldn't tell why).
        # A bound method, not a lambda: a lambda holding `self` would keep the dialog alive.
        self.finished.connect(self._log_answer)

    def _log_answer(self, result: int) -> None:
        answer = "with its action" if result == QDialog.DialogCode.Accepted else "with Cancel"
        log.debug("Dialog answered %s: %s", answer, self.windowTitle())

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        """Write the dialog to Activity when it appears (Reference R5)."""
        super().showEvent(event)
        if not event.spontaneous():
            body = self.body.text() if self.body.isVisibleTo(self) else ""
            log.info("%s", f"{self.title.text()} {body}".strip())

    def _finish(
        self,
        confirm: QPushButton,
        *,
        cancel_first: bool,
        accepts: bool = True,
        extra: Sequence[QPushButton] = (),
    ) -> None:
        self.confirm = confirm
        if accepts:  # Choice accepts through `_chosen`; twice gave two "Dialog answered" lines
            confirm.clicked.connect(self.accept)
        self._lay_out_buttons(
            [self.cancel, *extra, confirm], self.cancel if cancel_first else confirm
        )

    def _lay_out_buttons(self, buttons: list[QPushButton], default: QPushButton) -> None:
        """Place the action buttons so none is ever cut off (law 1, D1 blocker 1).

        One row, right-aligned, while the buttons fit the content width; otherwise stacked full
        width, most important first. A single button wider than the content widens the dialog
        instead of clipping. The choice is made once from the buttons' size hints (the text scale
        is fixed while a dialog is open), so it holds at every scale.
        """
        self._action_buttons = buttons
        default.setDefault(True)
        default.setFocus(Qt.FocusReason.OtherFocusReason)
        hints = [button.sizeHint().width() for button in buttons]
        content = WIDTH - 2 * self._padding
        if sum(hints) + self._spacing * (len(buttons) - 1) <= content:
            row = QHBoxLayout()
            row.setSpacing(self._spacing)
            row.addStretch()
            for button in buttons:
                row.addWidget(button)
            self.layout_.addLayout(row)
            self.setFixedWidth(WIDTH)
            return
        column = QVBoxLayout()
        column.setSpacing(self._spacing)
        for button in self._stacked_order(buttons):
            column.addWidget(button)
        self.layout_.addLayout(column)
        self.setFixedWidth(max(WIDTH, max(hints) + 2 * self._padding))

    def _stacked_order(self, buttons: list[QPushButton]) -> list[QPushButton]:
        """Stacked, most important first: the primary action, then the rest, then Cancel last."""
        primary = getattr(self, "confirm", None)
        head = [primary] if primary in buttons else []
        tail = [self.cancel] if self.cancel in buttons else []
        middle = [button for button in buttons if button not in (primary, self.cancel)]
        return head + middle + tail


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


class Choice(_Dialog):
    """A question with two actions besides Cancel: `choice` is "primary", "secondary" or ""."""

    def __init__(
        self,
        question: str,
        body: str,
        primary: str,
        secondary: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(question, body, parent)
        self.choice = ""
        go = QPushButton(primary, self)
        go.setProperty("primary", True)
        go.clicked.connect(lambda: self._chosen("primary"))
        self.secondary = QPushButton(secondary, self)
        self.secondary.clicked.connect(lambda: self._chosen("secondary"))
        # The primary may close something, so Choice accepts through `_chosen`, not accept().
        self._finish(go, cancel_first=True, accepts=False, extra=[self.secondary])

    def _chosen(self, which: str) -> None:
        self.choice = which
        self.accept()


class Information(_Dialog):
    """A short explanation with one "Close" button (help, steps to follow)."""

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(title, body, parent)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.cancel.setText(QCoreApplication.translate("Dialogs", "Close"))
        self._lay_out_buttons([self.cancel], self.cancel)
