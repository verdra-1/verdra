# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Traffic screen (Advanced mode only).

Until its spec is built, the screen shows M-SOON-01.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState, soon


class TrafficScreen(QWidget):
    """The Traffic screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "activity",
            QCoreApplication.translate("Sidebar", "Traffic"),
            soon(),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
