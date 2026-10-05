# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Empty states with illustration, heading, sentence and up to two buttons.

Master plan 7.2 and 7.3: an empty screen invites the first action. The first button is the
screen's primary action; a second one, if any, is secondary.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from verdra.canopy.crown import theme

ILLUSTRATION_SIZE = 48
SENTENCE_WIDTH = 420


def soon() -> str:
    """Return M-SOON-01, shown for screens and controls that aren't built yet.

    It never promises a version (Reference R5).
    """
    return QCoreApplication.translate(
        "M-SOON-01", "This part of Verdra isn't built yet. It will arrive in a later version."
    )


class Sentence(QLabel):
    """A wrapped label of a fixed width that is always tall enough for its text.

    A centred layout item gets its size hint, not its height for the width, so a wrapped label
    in one is cut off as soon as the text size grows (plan 12.5). This label sets its own
    minimum height again whenever its font, style or text changes.
    """

    def __init__(self, text: str, width: int, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setFixedWidth(width)
        self.fit()

    def fit(self) -> None:
        """Make the label exactly as tall as its wrapped text."""
        self.setMinimumHeight(self.heightForWidth(self.width()))

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        """Change the text and fit the height to it (Qt API)."""
        super().setText(text)
        self.fit()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        """Fit the height again after a font or style change (Qt API)."""
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.fit()


class EmptyState(QWidget):
    """A centred icon, heading, sentence and up to two buttons."""

    def __init__(
        self,
        icon_name: str,
        heading: str,
        sentence: str,
        buttons: list[tuple[str, Callable[[], None]]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(tokens.length("space-2"))

        self.illustration = QLabel(self)
        self.illustration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.illustration.setFixedSize(QSize(ILLUSTRATION_SIZE, ILLUSTRATION_SIZE))
        layout.addWidget(self.illustration, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(tokens.length("space-2"))

        self.heading = QLabel(heading, self)
        theme.set_text_style(self.heading, "title-m")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.heading)

        self.sentence = Sentence(sentence, SENTENCE_WIDTH, self)
        self.sentence.setProperty("muted", True)
        self.sentence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sentence, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.buttons: list[QPushButton] = []
        if buttons:
            row = QHBoxLayout()
            row.setSpacing(tokens.length("space-2"))
            row.addStretch()
            for index, (text, action) in enumerate(buttons[:2]):
                button = QPushButton(text, self)
                button.setProperty("primary", index == 0)
                button.clicked.connect(action)
                row.addWidget(button)
                self.buttons.append(button)
            row.addStretch()
            layout.addSpacing(tokens.length("space-2"))
            layout.addLayout(row)

        current = theme.Theme.instance()
        if current is not None:
            current.changed.connect(self._repaint_illustration)
        self._repaint_illustration()

    def _repaint_illustration(self) -> None:
        current = theme.Theme.instance()
        color = (
            current.color("ink-muted")
            if current
            else theme.Tokens.load().color("ink-muted", "light")
        )
        self.illustration.setPixmap(
            theme.icon_pixmap(self._icon_name, color, ILLUSTRATION_SIZE, self.devicePixelRatioF())
        )
