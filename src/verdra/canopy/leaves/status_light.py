# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The header's status light: the status leaf and its word (0027 §3-4, interface mapping of S-14).

The whole leaf is the status mark, never a toggle. The four routing states (spec S-14) map to the
five interface words by whether the user has something to do:

- Routing -> **Working**            (the leaf solid teal, breathing in the window)
- Idle    -> **Off**                (routing is not on)
- Degraded, with a fix to offer -> **Needs you**
- Degraded, nothing for the user to do -> **Waiting for the game**
- Error   -> **Stopped**

The word is always shown beside the leaf, so status never rests on colour alone. The 5-second
"show a change only after it lasts 5 s" rule (0027 §5) is held by the shell, so the header and the
tray always agree (spec S-14 rule 1); every change is logged at once in roots.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from verdra.canopy.crown import theme
from verdra.canopy.leaves.status_leaf import LeafState, StatusLeaf

LEAF_SIZE = 20


class StatusWord(Enum):
    """The five interface status words (0027 §3). Each carries the leaf state it shows."""

    WORKING = LeafState.WORKING
    WAITING = LeafState.WAITING
    NEEDS_YOU = LeafState.NEEDS_YOU
    STOPPED = LeafState.STOPPED
    OFF = LeafState.OFF

    @property
    def leaf(self) -> LeafState:
        """Return the leaf state for this word."""
        return self.value

    def label(self) -> str:
        """Return the word in the interface language."""
        words = {
            StatusWord.WORKING: QCoreApplication.translate("Status", "Working"),
            StatusWord.WAITING: QCoreApplication.translate("M-STATUS-10", "Waiting for the game"),
            StatusWord.NEEDS_YOU: QCoreApplication.translate("Status", "Needs you"),
            StatusWord.STOPPED: QCoreApplication.translate("Status", "Stopped"),
            StatusWord.OFF: QCoreApplication.translate("Status", "Off"),
        }
        return words[self]


def word_for(state: str, *, has_fix: bool) -> StatusWord:
    """Map a routing state (spec S-14) to its interface word (0027 §3).

    `has_fix` is whether the popover offers the user a fix for this status; a degraded status with
    a fix reads "Needs you", one with nothing for the user to do reads "Waiting for the game".
    """
    if state == "routing":
        return StatusWord.WORKING
    if state == "error":
        return StatusWord.STOPPED
    if state == "degraded":
        return StatusWord.NEEDS_YOU if has_fix else StatusWord.WAITING
    return StatusWord.OFF  # idle: routing is not on


class StatusLight(QWidget):
    """The status pill: the leaf and its word. A click or Space/Enter opens the popover.

    Signals:
        clicked(): The light was activated with the mouse or keyboard.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusLight")
        self._word = StatusWord.OFF
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        tokens = theme.Tokens.load()
        row = QHBoxLayout(self)
        row.setContentsMargins(
            tokens.length("space-3"),
            tokens.length("space-1"),
            tokens.length("space-3"),
            tokens.length("space-1"),
        )
        row.setSpacing(tokens.length("space-2"))
        self.leaf = StatusLeaf(LEAF_SIZE, self)
        row.addWidget(self.leaf)
        self.word = QLabel(self)
        theme.set_text_style(self.word, "body-strong")
        row.addWidget(self.word)
        self.set_word(StatusWord.OFF)

    @property
    def status_word(self) -> StatusWord:
        """Return the word shown."""
        return self._word

    def set_word(self, word: StatusWord) -> None:
        """Show a status word and its leaf."""
        self._word = word
        self.leaf.set_state(word.leaf)
        self.word.setText(word.label())
        label = QCoreApplication.translate("StatusLight", "Routing status: {status}").format(
            status=word.label()
        )
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the pill's natural size from its contents (law 1: it grows with the text)."""
        layout = self.layout()
        return layout.totalSizeHint() if layout is not None else super().sizeHint()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        """A left-button release inside the pill activates it, like a button."""
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        """Space or Enter activates it, like a button."""
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)
