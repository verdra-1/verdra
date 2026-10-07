# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Profiles list, replacements table, toolbar.

Specs S-20 and S-22. The profiles are listed highest first, each with its switch (a check box);
the table shows the selected profile's replacements, and "Add replacement" opens the editor
drawer beside it. With no profile yet, the empty state (M-EMPTY-01) offers "Add replacement",
which makes a first profile. Presets arrive with the catalogue (M7), so "Browse presets" stays
disabled with M-SOON-01.
"""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.empty import EmptyState, soon
from verdra.canopy.screens.grafts.editor import Editor
from verdra.canopy.screens.grafts.preview import PreviewDialog
from verdra.trunk.branches import grafts


class ReplacementsScreen(QWidget):
    """The Replacements screen.

    Signals:
        deleted(str): A profile was deleted (M-PROF-09); the window shows it with "Undo".
    """

    deleted = Signal(str)

    def __init__(self, parent: QWidget | None = None, service: grafts.Grafts | None = None) -> None:
        super().__init__(parent)
        self.service = service
        #: The profile deleted last and where it was, for "Undo" (M-PROF-09, M-PROF-10).
        self._deleted: tuple[grafts.Profile, int] | None = None
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
        self.stack.addWidget(self._empty_page())
        self.main = QWidget(self)
        self.stack.addWidget(self.main)
        self._build(self.main)
        if service is not None:
            service.changed.connect(self.refresh)
        self.refresh()

    # --- Layout -----------------------------------------------------------------------------

    def _empty_page(self) -> QWidget:
        """The empty state, and under it "Undo" while the last profile was just deleted."""
        page = QWidget(self)
        column = QVBoxLayout(page)
        column.addWidget(self.empty, 1)
        self.restore_note = QLabel(
            QCoreApplication.translate(
                "M-PROF-10",
                "You deleted your last profile, so no replacements are left. Undo brings it "
                "back with its replacements; Add replacement starts a new one.",
            ),
            page,
        )
        self.restore_note.setWordWrap(True)
        self.restore_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.restore_note)
        self.restore = QPushButton(QCoreApplication.translate("M-PROF-10", "Undo"), page)
        self.restore.clicked.connect(self.undo_delete)
        column.addWidget(self.restore, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        self.empty_page = page
        return page

    def _build(self, host: QWidget) -> None:
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.addLayout(self._build_profiles(host), 1)
        row.addLayout(self._build_table(host), 3)
        self.editor = Editor(host, self.service.lookup if self.service is not None else None)
        self.editor.saved.connect(self._save)
        self.editor.hide()
        row.addWidget(self.editor, 2)

    def _build_profiles(self, host: QWidget) -> QVBoxLayout:
        side = QVBoxLayout()
        side.addWidget(QLabel(self.tr("Profiles"), host))
        # Deleting a profile sits in a menu, apart from the buttons used every day (a profile
        # was deleted by accident when a row was meant, Guide B on the maintainer's PC).
        self.profile_menu = QToolButton(host)
        self.profile_menu.setText(self.tr("Profile options"))
        self.profile_menu.setAccessibleName(self.tr("Profile options"))
        self.profile_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.profile_menu)
        self.delete_action = QAction(self.tr("Delete this profile…"), menu)
        self.delete_action.triggered.connect(self._delete)
        menu.addAction(self.delete_action)
        self.profile_menu.setMenu(menu)
        side.addWidget(self.profile_menu, 0, Qt.AlignmentFlag.AlignLeft)
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
        self.add_profile = QPushButton(self.tr("New profile"), host)
        self.add_profile.clicked.connect(self._create)
        side.addWidget(self.add_profile)
        return side

    def _build_table(self, host: QWidget) -> QVBoxLayout:
        middle = QVBoxLayout()
        tools = QVBoxLayout()
        self.add = QPushButton(self.tr("Add replacement"), host)
        self.add.setProperty("primary", True)
        self.add.clicked.connect(self._open_editor)
        self.remove = QPushButton(self.tr("Remove"), host)
        self.remove.clicked.connect(self._remove)
        self.undo = QPushButton(self.tr("Undo"), host)
        self.undo.clicked.connect(lambda: self._edit("undo"))
        self.redo = QPushButton(self.tr("Redo"), host)
        self.redo.clicked.connect(lambda: self._edit("redo"))
        self.preview = QPushButton(self.tr("Preview changes"), host)
        self.preview.clicked.connect(self.show_preview)
        # Two rows, so every label fits at the smallest window with the editor open and the
        # largest text size (a toolbar on one row was cut to "replacem", Guide B on Windows).
        for buttons in ((self.add, self.remove), (self.undo, self.redo, self.preview)):
            row = QHBoxLayout()
            for button in buttons:
                row.addWidget(button)
            row.addStretch(1)
            tools.addLayout(row)
        middle.addLayout(tools)
        self.table = QTableWidget(0, 4, host)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Original"), self.tr("Replace with"), self.tr("Kind"), self.tr("Note")]
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
            self.restore_note.setVisible(self._deleted is not None)
            self.restore.setVisible(self._deleted is not None)
            self.stack.setCurrentWidget(self.empty_page)
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

    def show_preview(self) -> None:
        """Preview changes (spec S-23)."""
        if self.service is not None:
            PreviewDialog(self.service.preview(), self).exec()

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
        # Why each replacement isn't used, as the next Apply now would publish it.
        notes = dict(service.store.compile().left_out)
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
            self.table.setItem(row, 3, QTableWidgetItem(notes.get(replacement.id, "")))

    # --- Editing ----------------------------------------------------------------------------

    def _edit(self, method: str, *args: Any) -> Any:
        assert self.service is not None  # noqa: S101 - only reachable with a service
        return self.service.edit(method, *args)

    def add_replacement(self) -> None:
        """Ctrl+N: open the editor, making a first profile if there is none."""
        if self.service is not None and not self.service.profiles:
            self._first()
        elif self.service is not None:
            self._open_editor()

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
        profile = self.service.store.get(profile_id)
        count = self.tr(
            "Its %n replacements are deleted with it. Undo brings them back.",
            "M-PROF-08",
            len(profile.replacements),
        )
        dialog = DestructiveConfirmation(
            QCoreApplication.translate("M-PROF-02", "Delete profile {name}?").format(
                name=profile.name
            ),
            QCoreApplication.translate("M-PROF-02", "Delete profile"),
            count,
            parent=self,
        )
        if dialog.exec() != DestructiveConfirmation.DialogCode.Accepted:
            return
        index = [p.id for p in self.service.profiles].index(profile_id)
        self._deleted = (copy.deepcopy(profile), index)
        self._edit("delete", profile_id)
        self.deleted.emit(
            QCoreApplication.translate("M-PROF-09", "Deleted profile {name}.").format(
                name=profile.name
            )
        )

    def undo_delete(self) -> None:
        """Bring back the profile deleted last, as it was ("Undo" on M-PROF-09 and M-PROF-10)."""
        if self._deleted is None or self.service is None:
            return
        profile, index = self._deleted
        try:
            self._edit("restore_profile", profile, index)
        except grafts.ProfileError as error:
            self.restore_note.setText(str(error))
            return
        self._deleted = None
        self.refresh()

    def _profile_switched(self, item: QListWidgetItem) -> None:
        enabled = item.checkState() == Qt.CheckState.Checked
        self._edit("set_enabled", str(item.data(Qt.ItemDataRole.UserRole)), enabled)

    def _open_editor(self) -> None:
        if self.selected_id() is None and self.service is not None and self.service.profiles:
            self.profiles.setCurrentRow(0)
        profile_id = self.selected_id()
        if self.service is not None and profile_id is not None:
            profile = self.service.store.get(profile_id)
            self.editor.start(self.service.store.folder / profile.name)
        else:
            self.editor.start()

    def _save(self, original: grafts.Original, target: grafts.Target, family: str) -> None:
        profile_id = self.selected_id()
        if profile_id is None:
            return
        try:
            self._edit("add_replacement", profile_id, original, target, family)
        except grafts.ProfileError as error:  # a refusal the user can act on: say it in place
            self.editor.problem.setText(str(error))
            return
        self.editor.hide()

    def _remove(self) -> None:
        profile_id, row = self.selected_id(), self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if profile_id is None or item is None:
            return
        self._edit("remove_replacement", profile_id, str(item.data(Qt.ItemDataRole.UserRole)))
