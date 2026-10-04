# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Profiles list, replacements table, toolbar.

Specs S-20 and S-22. The profiles are listed highest first, each with its switch (a check box);
the table shows the selected profile's replacements, and "Add replacement" opens the editor
drawer beside it. With no profile yet, the empty state (M-EMPTY-01) offers "Add replacement",
which makes a first profile. Presets arrive with the catalogue (M7), so "Browse presets" stays
disabled with M-SOON-01.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.empty import EmptyState, soon
from verdra.canopy.screens.grafts.editor import Editor
from verdra.trunk.branches import grafts


class ReplacementsScreen(QWidget):
    """The Replacements screen."""

    def __init__(self, parent: QWidget | None = None, service: grafts.Grafts | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.stack = QStackedLayout(self)
        not_yet = soon()
        self.empty = EmptyState(
            "graft",
            QCoreApplication.translate("M-EMPTY-01", "Nothing planted yet."),
            QCoreApplication.translate(
                "M-EMPTY-01", "Add your first replacement or start from a preset."
            ),
            [
                (QCoreApplication.translate("M-EMPTY-01", "Add replacement"), self._first),
                (QCoreApplication.translate("M-EMPTY-01", "Browse presets"), lambda: None),
            ],
            self,
        )
        self.empty.buttons[1].setEnabled(False)
        self.empty.buttons[1].setToolTip(not_yet)
        if service is None:
            self.empty.buttons[0].setEnabled(False)
            self.empty.buttons[0].setToolTip(not_yet)
        self.stack.addWidget(self.empty)
        self.main = QWidget(self)
        self.stack.addWidget(self.main)
        self._build(self.main)
        if service is not None:
            service.changed.connect(self.refresh)
        self.refresh()

    # --- Layout -----------------------------------------------------------------------------

    def _build(self, host: QWidget) -> None:
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.addLayout(self._build_profiles(host), 1)
        row.addLayout(self._build_table(host), 3)
        self.editor = Editor(host)
        self.editor.saved.connect(self._save)
        self.editor.hide()
        row.addWidget(self.editor, 2)

    def _build_profiles(self, host: QWidget) -> QVBoxLayout:
        side = QVBoxLayout()
        side.addWidget(QLabel(self.tr("Profiles"), host))
        self.profiles = QListWidget(host)
        self.profiles.setAccessibleName(self.tr("Profiles"))
        self.profiles.currentRowChanged.connect(lambda _row: self._show_replacements())
        self.profiles.itemChanged.connect(self._profile_switched)
        side.addWidget(self.profiles, 1)
        self.new_name = QLineEdit(host)
        self.new_name.setPlaceholderText(self.tr("New profile name"))
        self.new_name.setAccessibleName(self.tr("New profile name"))
        self.new_name.returnPressed.connect(self._create)
        side.addWidget(self.new_name)
        self.name_problem = QLabel(host)
        self.name_problem.setWordWrap(True)
        self.name_problem.hide()
        side.addWidget(self.name_problem)
        buttons = QHBoxLayout()
        self.add_profile = QPushButton(self.tr("New profile"), host)
        self.add_profile.clicked.connect(self._create)
        self.delete_profile = QPushButton(self.tr("Delete profile"), host)
        self.delete_profile.clicked.connect(self._delete)
        buttons.addWidget(self.add_profile)
        buttons.addWidget(self.delete_profile)
        side.addLayout(buttons)
        return side

    def _build_table(self, host: QWidget) -> QVBoxLayout:
        middle = QVBoxLayout()
        tools = QHBoxLayout()
        self.add = QPushButton(self.tr("Add replacement"), host)
        self.add.setProperty("primary", True)
        self.add.clicked.connect(self._open_editor)
        self.remove = QPushButton(self.tr("Remove"), host)
        self.remove.clicked.connect(self._remove)
        self.undo = QPushButton(self.tr("Undo"), host)
        self.undo.clicked.connect(lambda: self._edit("undo"))
        self.redo = QPushButton(self.tr("Redo"), host)
        self.redo.clicked.connect(lambda: self._edit("redo"))
        for button in (self.add, self.remove, self.undo, self.redo):
            tools.addWidget(button)
        tools.addStretch(1)
        middle.addLayout(tools)
        self.table = QTableWidget(0, 3, host)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Original"), self.tr("Replace with"), self.tr("Kind")]
        )
        self.table.setAccessibleName(self.tr("Replacements"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        middle.addWidget(self.table, 1)
        return middle

    # --- Showing ----------------------------------------------------------------------------

    def refresh(self) -> None:
        """Show the service's profiles (after any edit, undo or redo)."""
        service = self.service
        if service is None or not service.profiles:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.main)
        current = self.selected_id()
        self.profiles.blockSignals(True)  # noqa: FBT003 - Qt's own signature
        self.profiles.clear()
        for profile in service.profiles:
            item = QListWidgetItem(profile.name, self.profiles)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if profile.enabled else Qt.CheckState.Unchecked
            )
        self.profiles.blockSignals(False)  # noqa: FBT003
        ids = [p.id for p in service.profiles]
        self.profiles.setCurrentRow(ids.index(current) if current in ids else 0)
        self._show_replacements()
        self.undo.setEnabled(service.store.can_undo)
        self.redo.setEnabled(service.store.can_redo)

    def selected_id(self) -> str | None:
        """Return the selected profile's ID."""
        item = self.profiles.currentItem()
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def _show_replacements(self) -> None:
        service, profile_id = self.service, self.selected_id()
        self.table.setRowCount(0)
        if service is None or profile_id is None:
            return
        profile = service.store.get(profile_id)
        kinds = {
            "asset_id": self.tr("Asset ID"),
            "file": self.tr("Local file"),
            "url": self.tr("URL"),
            "remove": self.tr("Remove"),
        }
        for row, replacement in enumerate(profile.replacements):
            self.table.insertRow(row)
            original = QTableWidgetItem(str(replacement.original.asset_id))
            original.setData(Qt.ItemDataRole.UserRole, replacement.id)
            self.table.setItem(row, 0, original)
            self.table.setItem(row, 1, QTableWidgetItem(replacement.target.value))
            self.table.setItem(row, 2, QTableWidgetItem(kinds[replacement.target.kind]))

    # --- Editing ----------------------------------------------------------------------------

    def _edit(self, method: str, *args: Any) -> Any:
        assert self.service is not None  # noqa: S101 - only reachable with a service
        return self.service.edit(method, *args)

    def _first(self) -> None:
        """The empty state's "Add replacement": make a first profile, then open the editor."""
        if self.service is None:
            return
        self._edit("create", QCoreApplication.translate("M-PROF-07", "My replacements"))
        self._open_editor()

    def _create(self) -> None:
        name = self.new_name.text().strip()
        try:
            created = self._edit("create", name)
        except grafts.ProfileError as error:
            self.name_problem.setText(str(error))
            self.name_problem.show()
            return
        self.name_problem.hide()
        self.new_name.clear()
        self.profiles.setCurrentRow([p.id for p in self.service.profiles].index(created.id))  # type: ignore[union-attr]

    def _delete(self) -> None:
        profile_id = self.selected_id()
        if profile_id is None or self.service is None:
            return
        name = self.service.store.get(profile_id).name
        dialog = DestructiveConfirmation(
            QCoreApplication.translate("M-PROF-02", "Delete profile {name}?").format(name=name),
            QCoreApplication.translate("M-PROF-02", "Delete"),
            parent=self,
        )
        if dialog.exec() == DestructiveConfirmation.DialogCode.Accepted:
            self._edit("delete", profile_id)

    def _profile_switched(self, item: QListWidgetItem) -> None:
        enabled = item.checkState() == Qt.CheckState.Checked
        self._edit("set_enabled", str(item.data(Qt.ItemDataRole.UserRole)), enabled)

    def _open_editor(self) -> None:
        if self.selected_id() is None and self.service is not None and self.service.profiles:
            self.profiles.setCurrentRow(0)
        self.editor.start()

    def _save(self, original: int, target: str) -> None:
        profile_id = self.selected_id()
        if profile_id is None:
            return
        self._edit(
            "add_replacement",
            profile_id,
            grafts.Original(asset_id=original),
            grafts.Target(kind="asset_id", value=target),
        )
        self.editor.hide()

    def _remove(self) -> None:
        profile_id, row = self.selected_id(), self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if profile_id is None or item is None:
            return
        self._edit("remove_replacement", profile_id, str(item.data(Qt.ItemDataRole.UserRole)))
