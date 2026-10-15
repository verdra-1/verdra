# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Review & apply dialog.

Spec S-27: one last look at every change before it reaches the game. One line per change from
`trunk.branches.grafts.Grafts.pending_changes`, each with a checkbox; the checked ones are applied,
the others keep waiting. A Problem line is skipped and offers "Fix", which opens its row. The
restart checkbox follows Roblox's state; the dialog is the restart question, so M-LAUNCH-03 isn't
asked again. A picture line shows a 64 × 64 thumbnail of what the proxy will serve, made on a
worker (`Grafts.pictures`), and says when the texture is scaled (M-REVIEW-10); other lines show
their family's icon.
"""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QCoreApplication, QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.trunk.branches import grafts

#: The columns: the checkbox with the badge, the picture or family icon, the change, and Fix
#: for a Problem line.
BADGE, PICTURE, DETAIL, FIX = range(4)
#: The thumbnail's longest side (S-27, phase A).
THUMBNAIL = 64
#: The family icon shown where there is no picture.
FAMILY_ICON = {"Image": "image", "Mesh": "box", "Audio": "music"}


class Roblox(StrEnum):
    """What runs when the review opens, for the restart checkbox (M-REVIEW-04)."""

    OURS = "ours"  # a Player Verdra started: it can restart
    NONE = "none"  # nothing: the changes reach the next start
    OTHERS = "others"  # only a Player Verdra didn't start, which is never closed (S-12 rule 4)


class ReviewText(QObject):
    """The review's texts with a count, with their plural forms (S-27)."""

    def summary(self, count: int, skipped: int, *, restart: bool) -> str:
        if restart:
            text = self.tr(
                "%n changes. Roblox needs a restart to load them; unsaved progress in your game "
                "may be lost.",
                "M-REVIEW-02",
                count,
            )
        else:
            text = self.tr(
                "%n changes. They reach the game the next time Roblox starts.",
                "M-REVIEW-02",
                count,
            )
        if skipped:
            later = self.tr("%n will be skipped.", "M-REVIEW-11", skipped)
            text = f"{text} {later}"
        return text

    def apply(self, count: int) -> str:
        if not count:
            return self.tr("Apply", "M-REVIEW-05")
        return self.tr("Apply %n changes", "M-REVIEW-05", count)

    def applied(self, count: int, *, restarting: bool) -> str:
        if restarting:
            return self.tr("%n changes applied. Roblox is restarting.", "M-REVIEW-06", count)
        return self.tr(
            "%n changes applied. They reach the game the next time Roblox starts.",
            "M-REVIEW-06",
            count,
        )


def badge(kind: str) -> str:
    """A line's badge (M-REVIEW-03)."""
    names = {
        "new": QCoreApplication.translate("M-REVIEW-03", "New"),
        "changed": QCoreApplication.translate("M-REVIEW-03", "Changed"),
        "winner": QCoreApplication.translate("M-REVIEW-03", "Changed"),
        "order": QCoreApplication.translate("M-REVIEW-03", "Changed"),
        "off": QCoreApplication.translate("M-REVIEW-03", "Turning off"),
        "on": QCoreApplication.translate("M-REVIEW-03", "Turning on"),
        "deleted": QCoreApplication.translate("M-REVIEW-03", "Deleted"),
        "profile_deleted": QCoreApplication.translate("M-REVIEW-03", "Deleted"),
        "profile_on": QCoreApplication.translate("M-REVIEW-03", "Profile on"),
        "profile_off": QCoreApplication.translate("M-REVIEW-03", "Profile off"),
        "problem": QCoreApplication.translate("M-REVIEW-03", "Problem"),
        "waiting": QCoreApplication.translate("M-REVIEW-03", "Waiting"),
    }
    return names[kind]


class ReviewDialog(QDialog):
    """The Review & apply dialog (M-REVIEW-01).

    After `exec` returns Accepted, `chosen()` gives the checked changes' keys and `restart` says
    whether to restart Roblox.

    Signals:
        fix(str): "Fix" on a Problem line: the replacement to open.
    """

    fix = Signal(str)

    def __init__(
        self,
        changes: list[grafts.Change],
        roblox: Roblox,
        parent: QWidget | None = None,
        *,
        only: list[str] | None = None,
        busy: bool = False,
    ) -> None:
        super().__init__(parent)
        self.changes = changes
        self.text = ReviewText(self)
        title = QCoreApplication.translate("M-REVIEW-01", "Review changes before applying")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setMinimumWidth(560)
        column = QVBoxLayout(self)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        column.addWidget(self.summary)
        self.table = self._make_table(only)
        column.addWidget(self.table, 1)
        self.restart_box = self._make_restart(roblox)
        column.addWidget(self.restart_box)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        back = QPushButton(QCoreApplication.translate("M-REVIEW-05", "Back to editing"), self)
        back.clicked.connect(self.reject)
        self.apply_button = QPushButton(self)
        self.apply_button.setProperty("primary", True)
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.accept)
        buttons.addWidget(back)
        buttons.addWidget(self.apply_button)
        column.addLayout(buttons)
        #: S-24 rule 6 (M-APPLY-07): Roblox is still restarting after the last apply.
        self.busy = busy
        QShortcut(QKeySequence("Ctrl+Return"), self, self._apply_if_enabled)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self._apply_if_enabled)
        self.table.itemChanged.connect(self._checked)
        self.restart_box.toggled.connect(lambda _on: self._update())
        self._update()

    @property
    def restart(self) -> bool:
        """Whether to restart Roblox after applying."""
        return self.restart_box.isEnabled() and self.restart_box.isChecked()

    @property
    def count(self) -> int:
        """How many checked changes will be applied (Problem lines are skipped)."""
        return self._counts()[0]

    def chosen(self) -> list[str]:
        """The checked changes' keys, each once."""
        keys: list[str] = []
        for row, change in enumerate(self.changes):
            item = self.table.item(row, BADGE)
            checked = item is not None and item.checkState() == Qt.CheckState.Checked
            if checked and change.key not in keys:
                keys.append(change.key)
        return keys

    def _make_table(self, only: list[str] | None) -> QTableWidget:
        table = QTableWidget(len(self.changes), 4, self)
        table.setIconSize(QSize(THUMBNAIL, THUMBNAIL))
        table.setAccessibleName(QCoreApplication.translate("M-REVIEW-01", "Changes"))
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setWordWrap(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(BADGE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(PICTURE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(DETAIL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(FIX, QHeaderView.ResizeMode.ResizeToContents)
        for row, change in enumerate(self.changes):
            mark = QTableWidgetItem(badge(change.kind))
            mark.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            picked = only is None or change.key in only
            mark.setCheckState(Qt.CheckState.Checked if picked else Qt.CheckState.Unchecked)
            mark.setData(Qt.ItemDataRole.AccessibleTextRole, f"{mark.text()}. {change.detail}")
            table.setItem(row, BADGE, mark)
            picture = QTableWidgetItem()
            picture.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if change.family in FAMILY_ICON:
                picture.setIcon(theme.icon(FAMILY_ICON[change.family], size=32))
            table.setItem(row, PICTURE, picture)
            detail = QTableWidgetItem(change.detail)
            detail.setToolTip(change.detail)
            table.setItem(row, DETAIL, detail)
            if change.kind == "problem":
                fix = QPushButton(QCoreApplication.translate("M-REVIEW-03", "Fix"), table)
                fix.setAccessibleName(
                    f"{QCoreApplication.translate('M-REVIEW-03', 'Fix')}: {change.detail}"
                )
                fix.clicked.connect(lambda _c=False, r=change.replacement_id: self._fix(r))
                table.setCellWidget(row, FIX, fix)
        table.resizeRowsToContents()
        return table

    def show_pictures(self, pictures: dict[str, grafts.ReviewPicture]) -> None:
        """Put each picture line's thumbnail in place of its icon, and say when the texture is
        scaled (M-REVIEW-10); called when the worker is done (S-27)."""
        for row, change in enumerate(self.changes):
            found = pictures.get(change.replacement_id)
            cell, detail = self.table.item(row, PICTURE), self.table.item(row, DETAIL)
            if found is None or cell is None or detail is None:
                continue
            image = QImage.fromData(found.png)
            if image.isNull():
                continue
            small = image.scaled(
                THUMBNAIL,
                THUMBNAIL,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cell.setIcon(QIcon(QPixmap.fromImage(small)))
            if found.scaled:
                width, height = found.served
                scaled = QCoreApplication.translate("M-REVIEW-10", "Scaled to {w} × {h}.").format(
                    w=width, h=height
                )
                detail.setText(f"{change.detail} {scaled}")
                detail.setToolTip(detail.text())
        self.table.resizeRowsToContents()

    def _make_restart(self, roblox: Roblox) -> QCheckBox:
        box = QCheckBox(
            QCoreApplication.translate("M-REVIEW-04", "Restart Roblox after applying"), self
        )
        box.setChecked(roblox is Roblox.OURS)
        box.setEnabled(roblox is Roblox.OURS)
        if roblox is Roblox.NONE:
            box.setToolTip(
                QCoreApplication.translate(
                    "M-REVIEW-04",
                    "Roblox isn't running. The changes reach the game the next time it starts.",
                )
            )
        elif roblox is Roblox.OTHERS:
            box.setToolTip(
                QCoreApplication.translate(
                    "M-CACHE-03",
                    "A Roblox Player that Verdra didn't start is running, so Verdra didn't move "
                    "Roblox's saved assets aside. Close it, then click Review & apply again.",
                )
            )
        return box

    def _checked(self, item: QTableWidgetItem) -> None:
        """Lines from the profile order share one key: checking one checks them all."""
        if item.column() != BADGE:
            return
        key, state = self.changes[item.row()].key, item.checkState()
        self.table.blockSignals(True)  # noqa: FBT003 - Qt's own signature
        for row, change in enumerate(self.changes):
            other = self.table.item(row, BADGE)
            if change.key == key and other is not None:
                other.setCheckState(state)
        self.table.blockSignals(False)  # noqa: FBT003
        self._update()

    def _counts(self) -> tuple[int, int]:
        """(changes to apply, Problem lines that will be skipped) among the checked ones."""
        chosen = set(self.chosen())
        skipped = {c.key for c in self.changes if c.kind == "problem" and c.key in chosen}
        return len(chosen - skipped), len(skipped)

    def _update(self) -> None:
        count, skipped = self._counts()
        self.summary.setText(self.text.summary(count, skipped, restart=self.restart))
        self.apply_button.setText(self.text.apply(count))
        self.apply_button.setEnabled(count > 0 and not self.busy)
        self.apply_button.setToolTip(
            QCoreApplication.translate(
                "M-APPLY-07", "Verdra is still restarting Roblox. Try again in a moment."
            )
            if self.busy
            else ""
        )

    def _apply_if_enabled(self) -> None:
        if self.apply_button.isEnabled():
            self.accept()

    def _fix(self, replacement_id: str) -> None:
        self.reject()
        self.fix.emit(replacement_id)
