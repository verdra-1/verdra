# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Traffic screen (Advanced mode only).

This version shows which release brings the screen; its spec is built in a later milestone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState


class TrafficScreen(QWidget):
    """The Traffic screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "activity",
            self.tr("Traffic arrives with Verdra 0.9."),
            self.tr(
                "The live request table, its details and HAR export are built in a later version."
            ),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
