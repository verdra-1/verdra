# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Settings screen, including System changes and Reset everything.

This version shows which release brings the screen; its spec is built in a later milestone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState


class SettingsScreen(QWidget):
    """The Settings screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "settings",
            self.tr("Settings"),
            self.tr("The settings groups arrive with the next build step."),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
