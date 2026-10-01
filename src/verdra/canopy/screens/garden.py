# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tweaks screen: file tweaks, FastFlags, frame-rate cap.

This version shows which release brings the screen; its spec is built in a later milestone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState


class TweaksScreen(QWidget):
    """The Tweaks screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "tweaks",
            self.tr("Tweaks arrive with Verdra 0.3."),
            self.tr("File tweaks, FastFlags and the frame-rate cap are built in a later version."),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
