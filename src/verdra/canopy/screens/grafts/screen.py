# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Profiles list, replacements table, toolbar.

Until replacement profiles exist (spec S-20, M2) the screen shows its empty state (M-EMPTY-01)
with both actions disabled and a tooltip saying why.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState, soon


class ReplacementsScreen(QWidget):
    """The Replacements screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        not_yet = soon()
        self.empty = EmptyState(
            "graft",
            QCoreApplication.translate("M-EMPTY-01", "Nothing planted yet."),
            QCoreApplication.translate(
                "M-EMPTY-01", "Add your first replacement or start from a preset."
            ),
            [
                (QCoreApplication.translate("M-EMPTY-01", "Add replacement"), lambda: None),
                (QCoreApplication.translate("M-EMPTY-01", "Browse presets"), lambda: None),
            ],
            self,
        )
        for button in self.empty.buttons:
            button.setEnabled(False)
            button.setToolTip(not_yet)
        QVBoxLayout(self).addWidget(self.empty)
