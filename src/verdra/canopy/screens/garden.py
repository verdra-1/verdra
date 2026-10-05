# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Tweaks screen: file tweaks, FastFlags, frame-rate cap.

Until its spec is built, the screen shows M-SOON-01.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState, soon


class TweaksScreen(QWidget):
    """The Tweaks screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "tweaks",
            QCoreApplication.translate("Sidebar", "Tweaks"),
            soon(),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
