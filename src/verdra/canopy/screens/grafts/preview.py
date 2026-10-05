# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Preview changes dialog.

Spec S-23: every original asset the enabled profiles change, grouped by type, with the winning
replacement, the profile it comes from, and every conflicting replacement it overrides; the
totals (M-PREV-01) at the top. It shows `trunk.branches.grafts.preview`, computed from the same
snapshot the proxy uses.
"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdra.trunk.branches import grafts


class PreviewText(QObject):
    """M-PREV-01 and the labels, with their plural forms."""

    def totals(self, changes: int, conflicts: int) -> str:
        return (
            self.tr("%n assets will change;", "M-PREV-01", changes)
            + " "
            + self.tr("%n conflicts.", "M-PREV-01", conflicts)
        )

    def target(self, graft: object) -> str:
        kind = getattr(graft, "kind", "")
        value = getattr(graft, "value", "")
        if kind == "remove":
            return self.tr("Removed")
        if kind == "asset_id":
            return self.tr("Asset {id}").format(id=value)
        return str(value)


class PreviewDialog(QDialog):
    """The Preview changes dialog."""

    def __init__(self, preview: grafts.Preview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        text = PreviewText(self)
        self.setWindowTitle(self.tr("Preview changes"))
        column = QVBoxLayout(self)
        self.totals = QLabel(text.totals(preview.changes, preview.conflicts), self)
        column.addWidget(self.totals)
        self.tree = QTreeWidget(self)
        self.tree.setAccessibleName(self.tr("Changes"))
        self.tree.setHeaderLabels(
            [self.tr("Original"), self.tr("Replace with"), self.tr("From profile")]
        )
        for kind, rows in preview.groups.items():
            group = QTreeWidgetItem(self.tree, [kind or self.tr("Other")])
            group.setFirstColumnSpanned(True)
            for row in rows:
                winner = row.winner
                original = str(winner.original) + (f" · {winner.slot}" if winner.slot else "")
                item = QTreeWidgetItem(group, [original, text.target(winner), winner.profile])
                for lost in row.overridden:
                    QTreeWidgetItem(
                        item,
                        [
                            self.tr("Overridden"),
                            text.target(lost),
                            lost.profile,
                        ],
                    )
        self.tree.expandAll()
        column.addWidget(self.tree, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)
        self.resize(640, 420)
