# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Empty states with illustration, heading, sentence and up to two buttons.

Master plan 7.2 and 7.3: an empty screen invites the first action. The first button is the
screen's primary action; a second one, if any, is secondary.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from verdra.canopy.crown import theme

ILLUSTRATION_SIZE = 48
SENTENCE_WIDTH = 420


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

        self.sentence = QLabel(sentence, self)
        self.sentence.setProperty("muted", True)
        self.sentence.setWordWrap(True)
        self.sentence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sentence.setFixedWidth(SENTENCE_WIDTH)
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
        colour = (
            current.colour("ink-muted")
            if current
            else theme.Tokens.load().colour("ink-muted", "light")
        )
        self.illustration.setPixmap(
            theme.icon_pixmap(self._icon_name, colour, ILLUSTRATION_SIZE, self.devicePixelRatioF())
        )
