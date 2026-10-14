# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Profiles list, replacements table, toolbar.

Specs S-20, S-22, S-25 and S-26. Each row shows its status (S-25) three ways: a colored left
edge, a pill with a word, and a tooltip; the waiting banner counts what the next apply changes;
chips filter by status and by kind of asset. Rows switch on and off, duplicate, move, revert to
their live version and delete (several at once too), and take a file dropped on them. The
profiles are listed highest first, each with its switch (a check box); the table shows the
selected profile's replacements, and "Add replacement" opens the editor drawer beside it. With
no profile yet, the empty state (M-EMPTY-01) offers "Add replacement", which makes a first
profile. Presets arrive with the catalogue (M7), so "Browse presets" stays disabled with
M-SOON-01.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QCoreApplication,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QPainter,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedLayout,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.empty import EmptyState, soon
from verdra.canopy.screens.grafts.editor import Editor
from verdra.canopy.screens.grafts.preview import PreviewDialog
from verdra.trunk.branches import grafts

Status = grafts.Status

#: S-25: (edge token, pill fill token, pill text token) for each status.
_LOOK = {
    Status.NEW: ("warning", "warning-tint", "warning-ink"),
    Status.EDITED: ("primary", "primary-tint", "ink"),
    Status.DELETED: ("primary", "primary-tint", "ink"),
    Status.LIVE: ("success", "success-tint", "success-ink"),
    Status.SEEN: ("success", "success-tint", "success-ink"),
    Status.PROBLEM: ("danger", "danger-tint", "danger-ink"),
    Status.OFF: ("ink-disabled", "surface-sunken", "ink-muted"),
}
#: Columns: the first four are the M2 table's; status and switch follow.
ORIGINAL, TARGET, KIND, NOTE, STATUS, ON = range(6)
#: A role holding the row's `RowState`, read by the delegate.
STATE_ROLE = Qt.ItemDataRole.UserRole + 1
#: Filter chips (S-25): status filters, then one per kind of asset present.
FILTERS = ("all", "live", "waiting", "problem", "off")


class StatusWords(QObject):
    """The status texts with a count: lupdate makes plural entries only from `self.tr`."""

    def seen(self, loads: int) -> str:
        """M-ROW-05."""
        return self.tr("Live · seen %n×", "M-ROW-05", loads)

    def loaded(self, loads: int, last: str) -> str:
        """M-ROW-08 for Live · seen."""
        return self.tr(
            "Roblox loaded it %n times since it started (last at {time}; a picture arrives in up "
            "to 3 parts).",
            "M-ROW-08",
            loads,
        ).format(time=last)


def status_word(state: grafts.RowState) -> str:
    """The word on a row's pill (M-ROW-02 to M-ROW-07, M-ROW-12)."""
    if state.status is Status.SEEN:
        return StatusWords().seen(state.loads)
    words = {
        Status.NEW: QCoreApplication.translate("M-ROW-02", "New · not applied"),
        Status.EDITED: QCoreApplication.translate("M-ROW-03", "Edited · apply to update"),
        Status.LIVE: QCoreApplication.translate("M-ROW-04", "Live · not seen yet"),
        Status.OFF: QCoreApplication.translate("M-ROW-07", "Off"),
        Status.DELETED: QCoreApplication.translate("M-ROW-12", "Deleted · apply to remove"),
    }
    if state.status is Status.PROBLEM:
        return QCoreApplication.translate("M-ROW-06", "Problem · {reason}").format(
            reason=short_reason(state.detail)
        )
    return words[state.status]


def short_reason(detail: str) -> str:
    """M-ROW-06's short reason, from the full one."""
    text = detail.lower()
    reasons = (
        ("missing", QCoreApplication.translate("M-ROW-06", "file missing")),
        ("too large", QCoreApplication.translate("M-ROW-06", "too large")),
        ("too big", QCoreApplication.translate("M-ROW-06", "too large")),
        ("downloaded", QCoreApplication.translate("M-ROW-06", "link failed")),
        ("can't replace", QCoreApplication.translate("M-ROW-06", "wrong type")),
        ("isn't built yet", QCoreApplication.translate("M-ROW-06", "not built yet")),
    )
    for needle, reason in reasons:
        if needle in text:
            return reason
    return QCoreApplication.translate("M-ROW-06", "can't read the file")


def status_tip(state: grafts.RowState) -> str:
    """The pill's tooltip: one sentence (M-ROW-08), then the detail line if any."""
    if state.status is Status.SEEN:
        last = time.strftime("%H:%M", time.localtime(state.last or 0))
        tip = StatusWords().loaded(state.loads, last)
    elif state.status is Status.PROBLEM:
        return state.detail
    else:
        tips = {
            Status.NEW: QCoreApplication.translate(
                "M-ROW-08", "Saved. It reaches the game when you click Review & apply."
            ),
            Status.EDITED: QCoreApplication.translate(
                "M-ROW-08",
                "Changed since it was applied. The game keeps the applied version until you "
                "click Review & apply.",
            ),
            Status.DELETED: QCoreApplication.translate(
                "M-ROW-08", "Deleted. The game keeps it until you click Review & apply."
            ),
            Status.LIVE: QCoreApplication.translate(
                "M-ROW-08", "Applied. Roblox hasn't asked for this asset since it started."
            ),
            Status.OFF: QCoreApplication.translate(
                "M-ROW-08", "Kept in the profile but not used. The game gets the original."
            ),
        }
        tip = tips[state.status]
    return f"{tip}\n{state.detail}" if state.detail else tip


def family_chip(asset_type: str) -> str:
    """The kind-of-asset chip a row belongs to (S-25 filters)."""
    noun = grafts.type_name(asset_type)
    chips = {
        "picture": QCoreApplication.translate("M-ROW-11", "Images"),
        "decal": QCoreApplication.translate("M-ROW-11", "Images"),
        "mesh": QCoreApplication.translate("M-ROW-11", "Meshes"),
        "sound": QCoreApplication.translate("M-ROW-11", "Sounds"),
    }
    return chips.get(noun, QCoreApplication.translate("M-ROW-11", "Other"))


def chip_name(key: str) -> str:
    """A status chip's word (M-ROW-11)."""
    names = {
        "all": QCoreApplication.translate("M-ROW-11", "All"),
        "live": QCoreApplication.translate("M-ROW-11", "Live"),
        "waiting": QCoreApplication.translate("M-ROW-11", "Waiting"),
        "problem": QCoreApplication.translate("M-ROW-11", "Problem"),
        "off": QCoreApplication.translate("M-ROW-11", "Off"),
    }
    return names[key]


def matches(state: grafts.RowState, chip: str) -> bool:
    """Whether a row shows under a status chip (S-25: Live counts both Live states, Waiting
    counts what the next apply changes)."""
    if chip == "live":
        return state.status in {Status.LIVE, Status.SEEN}
    if chip == "waiting":
        return state.waiting
    if chip == "problem":
        return state.status is Status.PROBLEM
    if chip == "off":
        return state.status is Status.OFF
    return True


class StatusDelegate(QStyledItemDelegate):
    """Paints the colored left edge (first column) and the status pill (status column)."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw the cell, then its part of the status from tokens."""
        state = index.data(STATE_ROLE)
        if not isinstance(state, grafts.RowState):
            super().paint(painter, option, index)
            return
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        edge, fill, ink = _LOOK[state.status]
        rect = QRectF(option.rect)  # pyright: ignore[reportAttributeAccessIssue]
        if index.column() == STATUS:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pill = rect.adjusted(4, 6, -4, -6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tokens.color(fill, mode))
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.setPen(tokens.color(ink, mode))
            painter.drawText(
                pill.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, str(index.data())
            )
            painter.restore()
            return
        super().paint(painter, option, index)
        if index.column() == ORIGINAL:
            width = 6 if state.status is Status.SEEN else 3
            painter.fillRect(
                QRectF(rect.left(), rect.top(), width, rect.height()), tokens.color(edge, mode)
            )


class WaitingBanner(QFrame):
    """S-25: how many changes wait for the next apply (warning tone, icon and words)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.icon = QLabel(self)
        layout.addWidget(self.icon)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        current = theme.Theme.instance()
        if current is not None:
            current.changed.connect(self._restyle)
        self._restyle()

    def show_count(self, count: int) -> None:
        """Show M-ROW-09 for `count` waiting changes, or hide when there are none."""
        text = self.tr(
            "%n changes are waiting. They reach the game when you click Review & apply.",
            "M-ROW-09",
            count,
        )
        self.label.setText(text)
        self.setAccessibleName(text)
        self.setVisible(count > 0)

    def _restyle(self) -> None:
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        fill = theme.css_color(tokens.color("warning-tint", mode))
        ink = theme.css_color(tokens.color("warning-ink", mode))
        radius = tokens.length("radius-m")
        self.setStyleSheet(
            f"WaitingBanner {{ background: {fill}; border-radius: {radius}px; }} "
            f"QLabel {{ color: {ink}; }}"
        )
        self.icon.setPixmap(
            theme.icon_pixmap(
                "triangle-alert", tokens.color("warning-ink", mode), 20, self.devicePixelRatioF()
            )
        )


class RowsTable(QTableWidget):
    """The replacements table: Space switches, Delete asks to delete, a file dropped on a row
    becomes its Local file (S-26)."""

    switch_pressed = Signal()
    delete_pressed = Signal()
    open_pressed = Signal()
    dropped = Signal(object, str)  # a row number; no Qt int crosses (test_real_size_ids)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        """Space and Delete act on the selected rows; anything else as usual."""
        if event.key() == Qt.Key.Key_Space and self.state() != self.State.EditingState:
            self.switch_pressed.emit()
        elif event.key() == Qt.Key.Key_Delete and self.state() != self.State.EditingState:
            self.delete_pressed.emit()
        elif (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and self.state() != self.State.EditingState
        ):
            self.open_pressed.emit()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        """Take one local file."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt API
        """Only over a row."""
        if event.mimeData().hasUrls() and self.rowAt(event.position().toPoint().y()) >= 0:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        """A local file dropped on a row: tell the screen which row and which file."""
        row = self.rowAt(event.position().toPoint().y())
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if row < 0 or len(urls) != 1:
            event.ignore()
            return
        event.acceptProposedAction()
        self.dropped.emit(row, urls[0].toLocalFile())


class ReplacementsScreen(QWidget):
    """The Replacements screen.

    Signals:
        deleted(str): A profile was deleted (M-PROF-09); the window shows it with "Undo".
        apply_only(list[str]): "Apply only these" (S-26): the selected replacements, to review.
    """

    deleted = Signal(str)
    apply_only = Signal(list)

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
        # Loads arrive in bursts (a picture's packs, many assets at a join): one redraw for each
        # burst, half a second after its first load (S-25 "seen").
        self._loads_timer = QTimer(self)
        self._loads_timer.setSingleShot(True)
        self._loads_timer.setInterval(500)
        self._loads_timer.timeout.connect(self._show_replacements)
        if service is not None:
            service.changed.connect(self.refresh)
            service.loaded.connect(lambda _original: self._loads_timer.start())
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
        self.editor.revert_pressed.connect(self._revert_editing)
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
        self.banner = WaitingBanner(host)
        self.banner.hide()
        middle.addWidget(self.banner)
        middle.addLayout(self._build_filters(host))
        self.table = self._make_table(host)
        middle.addWidget(self.table, 1)
        self.row_actions = QToolButton(host)
        self.row_actions.setText(self.tr("Selected rows"))
        self.row_actions.setAccessibleName(self.tr("Selected rows"))
        self.row_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.row_actions.setMenu(self._bulk_menu(self.row_actions))
        middle.addWidget(self.row_actions, 0, Qt.AlignmentFlag.AlignLeft)
        return middle

    def _make_table(self, host: QWidget) -> RowsTable:
        """The table: status and switch columns, multi-selection, inline note, drops (S-25)."""
        table = RowsTable(0, 6, host)
        table.setHorizontalHeaderLabels(
            [
                self.tr("Original"),
                self.tr("Replace with"),
                self.tr("Kind"),
                self.tr("Note"),
                self.tr("Status"),
                self.tr("On"),
            ]
        )
        table.setAccessibleName(self.tr("Replacements"))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Only the note is edited in place, by double-click (S-26 inline edits).
        table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        table.setAcceptDrops(True)
        table.viewport().setAcceptDrops(True)
        table.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        table.setItemDelegate(StatusDelegate(table))
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        corner = table.findChild(QAbstractButton)
        if corner is not None:  # "select all", live with multi-selection (S-01 test 9)
            corner.setAccessibleName(self.tr("Select all"))
            corner.setToolTip(self.tr("Select all"))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda _point: self._row_menu())
        table.itemChanged.connect(self._item_changed)
        table.switch_pressed.connect(self._toggle_selected)
        table.delete_pressed.connect(self._remove)
        table.open_pressed.connect(self._open_selected)
        table.cellClicked.connect(self._clicked)
        table.dropped.connect(self._dropped)
        return table

    def _build_filters(self, host: QWidget) -> QVBoxLayout:
        """S-25: chips with counts, one status chip at a time plus one kind-of-asset chip."""
        rows = QVBoxLayout()
        row = QHBoxLayout()
        second = QHBoxLayout()
        self.chips: dict[str, QPushButton] = {}
        for key in FILTERS:
            chip = QPushButton(chip_name(key), host)
            chip.setAccessibleName(chip_name(key))  # with its count on every refresh
            chip.setCheckable(True)
            chip.setProperty("chip", True)
            chip.clicked.connect(lambda _checked=False, k=key: self._filter(k))
            # Two rows, so the chips fit the smallest window at the largest text size (S-01).
            (row if key in {"all", "live", "waiting"} else second).addWidget(chip)
            self.chips[key] = chip
        row.addStretch(1)
        rows.addLayout(row)
        self.family_chips = QHBoxLayout()
        second.addLayout(self.family_chips)
        second.addStretch(1)
        rows.addLayout(second)
        self.status_filter = "all"
        self.family_filter = ""
        self.chips["all"].setChecked(True)
        return rows

    def _bulk_menu(self, parent: QWidget) -> QMenu:
        """Bulk actions on the selected rows (M-EDIT-18), also the row menu's (M-EDIT-17)."""
        menu = QMenu(parent)
        if len(self.selected_rows()) == 1:
            edit = QAction(QCoreApplication.translate("M-EDIT-17", "Edit"), menu)
            edit.triggered.connect(self._open_selected)
            menu.addAction(edit)
        for text, slot in (
            (QCoreApplication.translate("M-EDIT-18", "Switch on"), lambda: self._switch(True)),
            (QCoreApplication.translate("M-EDIT-18", "Switch off"), lambda: self._switch(False)),
            (QCoreApplication.translate("M-EDIT-17", "Duplicate"), self._duplicate),
            (QCoreApplication.translate("M-EDIT-18", "Move to profile…"), self._move),
            (QCoreApplication.translate("M-EDIT-16", "Revert to live version"), self._revert),
            (
                QCoreApplication.translate("M-EDIT-18", "Apply only these"),
                lambda: self.apply_only.emit(self.selected_rows()),
            ),
            (QCoreApplication.translate("M-EDIT-18", "Delete…"), self._remove),
        ):
            action = QAction(text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        return menu

    def _row_menu(self) -> None:
        if self.selected_rows():
            self._bulk_menu(self).exec(self.cursor().pos())

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
        kept = set(self.selected_rows()) if self.table.rowCount() else set()
        self.table.setRowCount(0)
        if service is None or profile_id is None:
            return
        profile = service.store.get(profile_id)
        states = service.states(profile)
        self.banner.show_count(service.waiting())
        self._update_chips(profile, states)
        kinds = {
            "asset_id": self.tr("Asset ID"),
            "file": self.tr("Local file"),
            "url": self.tr("URL"),
            "remove": self.tr("Remove"),
        }
        self.table.blockSignals(True)  # noqa: FBT003 - Qt's own signature
        shown = [
            r
            for r in profile.replacements
            if matches(states[r.id], self.status_filter)
            and (not self.family_filter or family_chip(r.asset_type) == self.family_filter)
        ]
        for row, replacement in enumerate(shown):
            state = states[replacement.id]
            self.table.insertRow(row)
            word, tip = status_word(state), status_tip(state)
            cells = (
                str(replacement.original.asset_id)
                + (f" · {replacement.name}" if replacement.name else ""),
                replacement.target.value,
                kinds[replacement.target.kind],
                replacement.note,
                word,
                "",
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(STATE_ROLE, state)
                item.setToolTip(tip)
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if column == NOTE:
                    flags |= Qt.ItemFlag.ItemIsEditable
                if column == ON:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                    item.setCheckState(
                        Qt.CheckState.Checked if replacement.enabled else Qt.CheckState.Unchecked
                    )
                    item.setData(Qt.ItemDataRole.AccessibleTextRole, self.tr("On"))
                item.setFlags(flags)
                font = item.font()
                font.setStrikeOut(state.status is Status.DELETED)
                item.setFont(font)
                self.table.setItem(row, column, item)
            first, status = self.table.item(row, ORIGINAL), self.table.item(row, STATUS)
            assert first is not None and status is not None  # noqa: S101 - set just above
            first.setData(Qt.ItemDataRole.UserRole, replacement.id)
            # S-25 rule 4: a screen reader reads the status with the row.
            status.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{word}. {state.detail}" if state.detail else word,
            )
        self._reselect([r.id in kept for r in shown])
        self.table.blockSignals(False)  # noqa: FBT003
        editing = self.editor.editing
        if editing is not None and editing in states:  # the drawer's pill follows the row
            state = states[editing]
            self.editor.show_status(
                status_word(state), can_revert=state.status in {Status.EDITED, Status.DELETED}
            )

    def _reselect(self, chosen: list[bool]) -> None:
        """Select the rows selected before a refresh again, so Space can switch them back."""
        model, selection = self.table.model(), self.table.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        rows = [row for row, picked in enumerate(chosen) if picked]
        for row in rows:
            selection.select(model.index(row, 0), flags)
        if rows:
            selection.setCurrentIndex(
                model.index(rows[0], 0), QItemSelectionModel.SelectionFlag.NoUpdate
            )

    def _update_chips(self, profile: grafts.Profile, states: dict[str, grafts.RowState]) -> None:
        for key, chip in self.chips.items():
            count = sum(1 for state in states.values() if matches(state, key))
            chip.setText(f"{chip_name(key)} {count}")
            chip.setAccessibleName(f"{chip_name(key)}, {count}")
            chip.setChecked(key == self.status_filter)
        while self.family_chips.count():
            taken = self.family_chips.takeAt(0)
            widget = taken.widget() if taken is not None else None
            if widget is not None:
                widget.deleteLater()
        families = sorted({family_chip(r.asset_type) for r in profile.replacements})
        if self.family_filter not in families:
            self.family_filter = ""
        for family in families if len(families) > 1 else ():
            count = sum(1 for r in profile.replacements if family_chip(r.asset_type) == family)
            chip = QPushButton(f"{family} {count}", self)
            chip.setCheckable(True)
            chip.setProperty("chip", True)
            chip.setChecked(family == self.family_filter)
            chip.clicked.connect(lambda _checked=False, f=family: self._filter_family(f))
            self.family_chips.addWidget(chip)

    def _filter(self, key: str) -> None:
        self.status_filter = key
        self._show_replacements()

    def _filter_family(self, family: str) -> None:
        self.family_filter = "" if self.family_filter == family else family
        self._show_replacements()

    def selected_rows(self) -> list[str]:
        """Return the replacement IDs of the selected rows, in table order."""
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        ids = []
        for row in rows:
            item = self.table.item(row, ORIGINAL)
            if item is not None:
                ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return ids

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
        if not self.editor.close_asking():
            return
        if self.selected_id() is None and self.service is not None and self.service.profiles:
            self.profiles.setCurrentRow(0)
        profile_id = self.selected_id()
        if self.service is not None and profile_id is not None:
            profile = self.service.store.get(profile_id)
            self.editor.start(self.service.store.folder / profile.name)
        else:
            self.editor.start()

    def _open_selected(self) -> None:
        """Enter, a click or the row menu's Edit: open the drawer on the row (S-26)."""
        ids = self.selected_rows()
        if len(ids) == 1:
            self.open_row(ids[0])

    def _clicked(self, _row: int, column: int) -> None:
        """A plain click on a row opens it; not on the switch or the note, which edit in place,
        and not while Shift or Ctrl add to the selection."""
        if (
            column in {ON, NOTE}
            or QApplication.keyboardModifiers() != Qt.KeyboardModifier.NoModifier
        ):
            return
        self._open_selected()

    def open_row(self, replacement_id: str) -> None:
        """Open the editor drawer on a replacement, every field filled in (M-EDIT-14)."""
        service, profile_id = self.service, self.selected_id()
        if service is None or profile_id is None:
            return
        if self.editor.isVisible() and self.editor.editing == replacement_id:
            return
        if not self.editor.close_asking():
            return
        profile = service.store.get(profile_id)
        row = next((r for r in profile.replacements if r.id == replacement_id), None)
        if row is None:
            return
        state = service.states(profile)[row.id]
        self.editor.edit(
            row,
            service.store.folder / profile.name,
            status_word(state),
            can_revert=state.status in {Status.EDITED, Status.DELETED},
        )

    def _save(self, original: grafts.Original, target: grafts.Target, family: str) -> None:
        profile_id, service = self.selected_id(), self.service
        if profile_id is None or service is None:
            return
        editing = self.editor.editing
        try:
            if editing is None:
                self._edit("add_replacement", profile_id, original, target, family)
            else:
                rows = service.store.get(profile_id).replacements
                row = copy.deepcopy(next(r for r in rows if r.id == editing))
                if row.original.asset_id != original.asset_id:
                    row.name = ""  # another asset: its own name, once Roblox says it
                row.original = grafts.Original(asset_id=original.asset_id, slot=row.original.slot)
                row.target = target
                row.asset_type = family or row.asset_type
                row.deleted = False  # saving a deleted row brings it back
                self._edit("edit_replacement", profile_id, row)
        except grafts.ProfileError as error:  # a refusal the user can act on: say it in place
            self.editor.problem.setText(str(error))
            return
        name = service.names.get(original.asset_id, "")
        if name:
            service.store.remember_name(original.asset_id, name)
            self.refresh()
        self.editor.hide()

    def _revert_editing(self) -> None:
        """The drawer's Revert to live version (M-EDIT-16): saved back to applied, then the
        drawer shows the live version."""
        profile_id, editing = self.selected_id(), self.editor.editing
        if profile_id is None or editing is None or self.service is None:
            return
        self._edit("revert", profile_id, [editing])
        self.editor.hide()
        self.open_row(editing)

    def _remove(self) -> None:
        """Delete the selected rows after M-EDIT-19 (S-26): applied ones stay live until the
        next apply, struck through."""
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is None or not ids or self.service is None:
            return
        rows = [r for r in self.service.store.get(profile_id).replacements if r.id in set(ids)]
        live, count = any(r.applied is not None for r in rows), len(rows)
        title = self.tr("Delete %n replacements?", "M-EDIT-19", count)
        body = (
            self.tr(
                "The game keeps them until you click Review & apply. Undo brings them back.",
                "M-EDIT-19",
                count,
            )
            if live
            else self.tr("Undo brings them back.", "M-EDIT-19", count)
        )
        dialog = DestructiveConfirmation(
            title, QCoreApplication.translate("M-EDIT-19", "Delete"), body, parent=self
        )
        if dialog.exec() != DestructiveConfirmation.DialogCode.Accepted:
            return
        self._edit("remove_replacements", profile_id, ids)

    def _switch(self, enabled: bool) -> None:  # noqa: FBT001 - the menu's two actions
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is not None and ids:
            self._edit("set_replacements_enabled", profile_id, ids, enabled)

    def _toggle_selected(self) -> None:
        """Space: switch the selected rows (on, unless every one is on already)."""
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is None or not ids or self.service is None:
            return
        rows = [r for r in self.service.store.get(profile_id).replacements if r.id in set(ids)]
        self._edit("set_replacements_enabled", profile_id, ids, not all(r.enabled for r in rows))

    def _duplicate(self) -> None:
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is None:
            return
        for replacement_id in ids:
            try:
                self._edit("duplicate_replacement", profile_id, replacement_id)
            except grafts.ProfileError as error:
                self.deleted.emit(str(error))
                return

    def _move(self) -> None:
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is None or not ids or self.service is None:
            return
        others = [p for p in self.service.profiles if p.id != profile_id]
        if not others:
            return
        name, chosen = QInputDialog.getItem(
            self,
            QCoreApplication.translate("M-EDIT-18", "Move to profile…"),
            QCoreApplication.translate("M-EDIT-18", "Move to profile…"),
            [p.name for p in others],
            0,
            False,  # noqa: FBT003 - Qt's own signature
        )
        if not chosen:
            return
        target = next(p for p in others if p.name == name)
        try:
            count = self._edit("move_replacements", profile_id, ids, target.id)
        except grafts.ProfileError as error:
            self.deleted.emit(str(error))
            return
        self.deleted.emit(
            self.tr("Moved %n replacements to {profile}.", "M-EDIT-22", count).format(
                profile=target.name
            )
        )

    def _revert(self) -> None:
        profile_id, ids = self.selected_id(), self.selected_rows()
        if profile_id is not None and ids:
            self._edit("revert", profile_id, ids)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        """The switch clicked, or a note edited in place (S-26 inline edits)."""
        profile_id = self.selected_id()
        first = self.table.item(item.row(), ORIGINAL)
        if profile_id is None or first is None or self.service is None:
            return
        replacement_id = str(first.data(Qt.ItemDataRole.UserRole))
        row = next(
            (r for r in self.service.store.get(profile_id).replacements if r.id == replacement_id),
            None,
        )
        if row is None:
            return
        if item.column() == ON:
            enabled = item.checkState() == Qt.CheckState.Checked
            if enabled != row.enabled:
                self._edit("set_replacements_enabled", profile_id, [replacement_id], enabled)
        elif item.column() == NOTE and item.text() != row.note:
            row.note = item.text()
            self._edit("edit_replacement", profile_id, row)

    def _dropped(self, row_number: int, path: str) -> None:
        """A local file dropped on a row becomes its Local file target, if it fits (S-22)."""
        profile_id = self.selected_id()
        first = self.table.item(row_number, ORIGINAL)
        if profile_id is None or first is None or self.service is None:
            return
        replacement_id = str(first.data(Qt.ItemDataRole.UserRole))
        profile = self.service.store.get(profile_id)
        row = next((r for r in profile.replacements if r.id == replacement_id), None)
        if row is None:
            return
        folder = self.service.store.folder / profile.name
        value = grafts.stored_path(Path(path), folder)
        problem = grafts.target_problem("file", value, folder)
        family = grafts.file_family(grafts.resolve(value, folder))[0]
        if problem is None and family is not None and row.asset_type:
            problem = grafts.type_problem(row.asset_type, family)
        if problem is not None:
            self.deleted.emit(problem)
            return
        row.target = grafts.Target(kind="file", value=value)
        self._edit("edit_replacement", profile_id, row)
