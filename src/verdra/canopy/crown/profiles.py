# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The profile popover under the sidebar card: switch, enable, create, rename, delete (D3 screen 2).

Master plan 7.1. The sidebar card names the active profile; clicking it opens this popover to pick
another profile, turn one on or off, or create, rename and delete one. It only emits intents; the
shell runs them through the profile service (spec S-20), shows a name problem inline and asks before
a delete, so this widget holds no profile logic of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme

POPOVER_WIDTH = 280
#: Item data roles: the profile id, and the name and checked state last shown (to tell a rename
#: from an enable when one item changes).
_ID = Qt.ItemDataRole.UserRole
_NAME = Qt.ItemDataRole.UserRole + 1
_ENABLED = Qt.ItemDataRole.UserRole + 2


class ProfileView(Protocol):
    """What the popover reads from a profile (trunk passes the service's own value)."""

    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def enabled(self) -> bool: ...


class ProfilePopover(QFrame):
    """The profile switcher and editor under the sidebar card.

    Signals:
        selected(id): Switch the shown profile to this one.
        enabled_changed(id, on): Turn a profile on or off.
        create_requested(name): Make a new profile with this name.
        rename_requested(id, name): Rename a profile.
        delete_requested(id): Delete a profile (the shell asks first).
    """

    selected = Signal(str)
    enabled_changed = Signal(str, bool)
    create_requested = Signal(str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("popover", True)
        self.setFixedWidth(POPOVER_WIDTH)
        tokens = theme.Tokens.load()
        pad = tokens.length("space-4")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(tokens.length("space-2"))

        title = QLabel(self.tr("Profiles"), self)
        theme.set_text_style(title, "body-strong")
        layout.addWidget(title)

        self.list = QListWidget(self)
        self.list.setObjectName("profileList")
        self.list.setAccessibleName(self.tr("Profiles"))
        self.list.currentItemChanged.connect(self._current_changed)
        self.list.itemChanged.connect(self._item_changed)
        layout.addWidget(self.list)

        actions = QHBoxLayout()
        self.rename = QPushButton(self.tr("Rename…"), self)
        self.rename.setAccessibleName(self.tr("Rename this profile"))
        self.rename.clicked.connect(self._start_rename)
        actions.addWidget(self.rename)
        self.delete = QPushButton(self.tr("Delete…"), self)
        self.delete.setAccessibleName(self.tr("Delete this profile"))
        self.delete.clicked.connect(self._delete_current)
        actions.addWidget(self.delete)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.new_name = QLineEdit(self)
        self.new_name.setPlaceholderText(self.tr("New profile name"))
        self.new_name.setAccessibleName(self.tr("New profile name"))
        self.new_name.returnPressed.connect(self._create)
        layout.addWidget(self.new_name)
        add = QPushButton(self.tr("New profile"), self)
        add.clicked.connect(self._create)
        layout.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)

        self.problem = QLabel(self)
        self.problem.setWordWrap(True)
        self.problem.setProperty("danger", True)
        self.problem.hide()
        layout.addWidget(self.problem)

    def show_profiles(self, profiles: Sequence[ProfileView], selected_id: str | None) -> None:
        """Fill the list with the profiles, the selected one current, each with its on/off box."""
        self.list.blockSignals(True)
        self.list.clear()
        for profile in profiles:
            item = QListWidgetItem(profile.name, self.list)
            item.setData(_ID, profile.id)
            item.setData(_NAME, profile.name)
            item.setData(_ENABLED, profile.enabled)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if profile.enabled else Qt.CheckState.Unchecked
            )
            item.setToolTip(profile.name)
            if profile.id == selected_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        has = self.list.currentItem() is not None
        self.rename.setEnabled(has)
        self.delete.setEnabled(has)

    def show_problem(self, text: str) -> None:
        """Show why a create or rename was refused (the service's own sentence)."""
        self.problem.setText(text)
        self.problem.setVisible(bool(text))

    def _current_id(self) -> str | None:
        item = self.list.currentItem()
        return None if item is None else str(item.data(_ID))

    def _current_changed(self, current: QListWidgetItem | None) -> None:
        self.rename.setEnabled(current is not None)
        self.delete.setEnabled(current is not None)
        if current is not None:
            self.selected.emit(str(current.data(_ID)))

    def _item_changed(self, item: QListWidgetItem) -> None:
        # One edit per signal: a new name is a rename, a new tick is an on/off change.
        pid = str(item.data(_ID))
        if item.text() != str(item.data(_NAME)):
            self.rename_requested.emit(pid, item.text())
            return
        now_on = item.checkState() == Qt.CheckState.Checked
        if now_on != bool(item.data(_ENABLED)):
            self.enabled_changed.emit(pid, now_on)

    def _start_rename(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list.editItem(item)

    def _delete_current(self) -> None:
        pid = self._current_id()
        if pid is not None:
            self.delete_requested.emit(pid)

    def _create(self) -> None:
        name = self.new_name.text().strip()
        if name:
            self.create_requested.emit(name)

    def clear_new_name(self) -> None:
        """Empty the new-name field (after a profile was made)."""
        self.new_name.clear()
        self.show_problem("")
