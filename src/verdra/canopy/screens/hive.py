# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Accounts screen: list, add wizard, launch panel, multi-instance, subplaces, name display.

This version shows which release brings the screen; its spec is built in a later milestone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState


class AccountsScreen(QWidget):
    """The Accounts screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "users",
            self.tr("Accounts arrive with Verdra 0.4."),
            self.tr(
                "Saved accounts, launching with an account and subplaces come in a later version."
            ),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
