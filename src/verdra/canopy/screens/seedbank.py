# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Library screen.

Until asset capture exists (spec S-30, M3) the screen shows its empty state (M-EMPTY-02) with
"Launch Roblox" disabled and a tooltip saying why.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState


class LibraryScreen(QWidget):
    """The Library screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "seed",
            QCoreApplication.translate("M-EMPTY-02", "Your library is empty."),
            QCoreApplication.translate(
                "M-EMPTY-02",
                "Launch Roblox through Verdra and assets will appear here as they load.",
            ),
            [(QCoreApplication.translate("M-EMPTY-02", "Launch Roblox"), lambda: None)],
            self,
        )
        for button in self.empty.buttons:
            button.setEnabled(False)
            button.setToolTip(
                self.tr(
                    "Launching Roblox arrives with Verdra 0.1. It isn't available in this version."
                )
            )
        QVBoxLayout(self).addWidget(self.empty)
