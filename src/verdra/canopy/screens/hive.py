# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Accounts screen: list, add wizard, launch panel, multi-instance, subplaces, name display.

Until its spec is built, the screen shows M-SOON-01.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from verdra.canopy.leaves.empty import EmptyState, soon


class AccountsScreen(QWidget):
    """The Accounts screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty = EmptyState(
            "users",
            QCoreApplication.translate("Sidebar", "Accounts"),
            soon(),
            parent=self,
        )
        QVBoxLayout(self).addWidget(self.empty)
