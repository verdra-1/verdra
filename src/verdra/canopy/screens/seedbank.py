# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Library screen.

Until asset capture exists (spec S-30, M3) the screen shows its empty state (M-EMPTY-02). Its
"Launch Roblox" starts Roblox through Verdra (spec S-12) when the window passes `on_launch`;
without it the button is disabled with a tooltip saying why.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState, soon


class LibraryScreen(QWidget):
    """The Library screen."""

    def __init__(
        self, parent: QWidget | None = None, on_launch: Callable[[], None] | None = None
    ) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "seed",
            QCoreApplication.translate("M-EMPTY-02", "Your library is empty."),
            QCoreApplication.translate(
                "M-EMPTY-02",
                "Launch Roblox through Verdra and assets will appear here as they load.",
            ),
            [
                (
                    QCoreApplication.translate("M-EMPTY-02", "Launch Roblox"),
                    on_launch or (lambda: None),
                )
            ],
            self,
        )
        if on_launch is None:
            for button in self.empty.buttons:
                button.setEnabled(False)
                button.setToolTip(soon())
        QVBoxLayout(self).addWidget(self.empty)
