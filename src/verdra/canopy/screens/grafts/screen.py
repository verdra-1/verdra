# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Full-width specimen rows, a wrapping toolbar, and the editor drawer.

Specs S-20, S-22, S-23, S-24 (D3 screen 2). The screen fills its width with one row per
replacement: before/after thumbnails (placeholders, not a preview Verdra can draw yet), the asset
ID as the primary line with its target as the caption (shortened in the middle, kept on hover and
copyable, law 2), and a Live/Draft/Off pill from the real state. The profile is chosen in the
sidebar card's popover (D3 screen 2, PR A); this screen follows it and tells it back. The toolbar
wraps rather than clip (law 1, D1 #16): Add replacement; Delete, Undo, Redo; Preview changes;
Apply now (also Ctrl+Return). With no profile yet, the empty state (M-EMPTY-01) offers "Add
replacement", which makes a first profile. Presets arrive with the catalogue (M7), so "Browse
presets" stays disabled with M-SOON-01.
"""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import QCoreApplication, QPoint, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.empty import EmptyState, soon
from verdra.canopy.leaves.flow import FlowLayout
from verdra.canopy.screens.grafts import specimen
from verdra.canopy.screens.grafts.editor import Editor, dropped_target
from verdra.canopy.screens.grafts.preview import PreviewDialog
from verdra.canopy.screens.grafts.specimen import KIND, NAME, RID, STATE, Pill
from verdra.trunk.branches import grafts


class ReplacementsScreen(QWidget):
    """The Replacements screen.

    Signals:
        deleted(str): A profile was deleted (M-PROF-09); the window shows it with "Undo".
        shown(str): The shown profile changed; the sidebar card follows it (D3 screen 2).
        apply_requested(): Apply now was pressed (the window runs it, spec S-24).
    """

    deleted = Signal(str)
    shown = Signal(str)
    apply_requested = Signal()

    def __init__(self, parent: QWidget | None = None, service: grafts.Grafts | None = None) -> None:
        super().__init__(parent)
        self.service = service
        #: The profile shown now (chosen in the sidebar popover); the rows follow it.
        self._shown_id: str | None = None
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
        self.setAcceptDrops(True)
        if service is not None:
            service.changed.connect(self.refresh)
            service.applied.connect(self._show_replacements)
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
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.Tokens.load().length("space-4"))
        column.addWidget(self._build_toolbar(host))
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.Tokens.load().length("space-4"))
        body.addWidget(self._build_list(host), 1)
        self.editor = Editor(host, self.service.lookup if self.service is not None else None)
        self.editor.saved.connect(self._save)
        self.editor.hide()
        body.addWidget(self.editor, 0)
        column.addLayout(body, 1)
        self.drop_hint = QLabel(
            QCoreApplication.translate(
                "M-PROF-11", "Drop a picture, mesh or a link anywhere to add a replacement."
            ),
            host,
        )
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setWordWrap(True)
        column.addWidget(self.drop_hint)

    def _toolbar_button(self, text: str, slot: Any, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text, self)
        if primary:
            button.setProperty("primary", True)
        button.clicked.connect(slot)
        return button

    def _group(self, *buttons: QPushButton) -> QWidget:
        """A labelled toolbar group: its buttons in a row (D1 #16); the flow wraps whole groups."""
        box = QWidget(self)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.Tokens.load().length("space-2"))
        for button in buttons:
            row.addWidget(button)
        return box

    def _build_toolbar(self, host: QWidget) -> QWidget:
        self.add = self._toolbar_button(self.tr("Add replacement"), self._open_editor, primary=True)
        # "Delete" removes the selected replacement row; "Remove" is a replacement kind (show
        # nothing in game), so the row action uses a different word to tell the two apart (D1 #22).
        self.remove = self._toolbar_button(self.tr("Delete"), self._remove)
        self.undo = self._toolbar_button(self.tr("Undo"), lambda: self._edit("undo"))
        self.redo = self._toolbar_button(self.tr("Redo"), lambda: self._edit("redo"))
        self.preview = self._toolbar_button(self.tr("Preview changes"), self.show_preview)
        self.apply = self._toolbar_button(self.tr("Apply now"), self.apply_requested.emit)
        bar = QWidget(host)
        flow = FlowLayout(bar, spacing=theme.Tokens.load().length("space-4"))
        flow.addWidget(self._group(self.add))
        flow.addWidget(self._group(self.remove, self.undo, self.redo))
        flow.addWidget(self._group(self.preview))
        flow.addWidget(self._group(self.apply))
        return bar

    def _build_list(self, host: QWidget) -> QWidget:
        self.rows = QListWidget(host)
        self.rows.setObjectName("replacementRows")
        self.rows.setAccessibleName(self.tr("Replacements"))
        self.rows.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rows.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Rows fill the width; the free-length caption shortens inside the row (law 2) rather than
        # push a horizontal scrollbar, so the pill at the right is always in view.
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows.setWordWrap(False)
        self.rows.setItemDelegate(specimen.RowDelegate(self.rows))
        self.rows.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rows.customContextMenuRequested.connect(self._row_menu)
        self.rows.currentItemChanged.connect(lambda *_: self._update_buttons())
        copy_rows = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.rows)
        copy_rows.activated.connect(self._copy_current)
        return self.rows

    # --- Showing ----------------------------------------------------------------------------

    def refresh(self) -> None:
        """Show the service's profiles (after any edit, undo or redo)."""
        service = self.service
        if service is None or not service.profiles:
            self._shown_id = None
            self.restore_note.setVisible(self._deleted is not None)
            self.restore.setVisible(self._deleted is not None)
            self.stack.setCurrentWidget(self.empty_page)
            return
        self.stack.setCurrentWidget(self.main)
        ids = [p.id for p in service.profiles]
        previous = self._shown_id
        if self._shown_id not in ids:
            self._shown_id = ids[0]
        self._show_replacements()
        self.undo.setEnabled(service.store.can_undo)
        self.redo.setEnabled(service.store.can_redo)
        if self._shown_id != previous and self._shown_id is not None:
            self.shown.emit(self._shown_id)

    def _show_replacements(self) -> None:
        service, profile_id = self.service, self._shown_id
        self.rows.clear()
        if service is None or profile_id is None:
            self._update_buttons()
            return
        profile = service.store.get(profile_id)
        live = service.live
        warnings = dict(service.store.compile().left_out)
        for replacement in profile.replacements:
            self._add_row(replacement, live, warnings)
        self._update_buttons()

    def _add_row(
        self, replacement: grafts.Replacement, live: frozenset[str], warnings: dict[str, str]
    ) -> None:
        caption = self._caption(replacement, warnings.get(replacement.id, ""))
        state = self._pill(replacement, live)
        item = QListWidgetItem(caption, self.rows)
        item.setData(NAME, str(replacement.original.asset_id))
        item.setData(KIND, replacement.target.kind)
        item.setData(RID, replacement.id)
        item.setData(STATE, state.value)
        if caption:
            item.setToolTip(caption)  # the full target on hover (law 2)
        item.setData(
            Qt.ItemDataRole.AccessibleTextRole,
            self.tr("Asset {id}: {target} — {state}").format(
                id=replacement.original.asset_id,
                target=caption,
                state=specimen.pill_word(state),
            ),
        )

    @staticmethod
    def _pill(replacement: grafts.Replacement, live: frozenset[str]) -> Pill:
        if not replacement.enabled:
            return Pill.OFF
        return Pill.LIVE if replacement.id in live else Pill.DRAFT

    @staticmethod
    def _caption(replacement: grafts.Replacement, warning: str) -> str:
        """The target line: a short description of what replaces the asset (with any warning)."""
        target = replacement.target
        kinds = {
            "asset_id": QCoreApplication.translate("Replacements", "Asset {value}"),
            "file": QCoreApplication.translate("Replacements", "Local file — {value}"),
            "url": QCoreApplication.translate("Replacements", "Link — {value}"),
            "remove": QCoreApplication.translate("Replacements", "Remove — shows nothing in game"),
        }
        text = kinds[target.kind]
        described = text if target.kind == "remove" else text.format(value=target.value)
        return f"{described}  ·  {warning}" if warning else described

    def _update_buttons(self) -> None:
        self.remove.setEnabled(self.rows.currentItem() is not None)

    def show_preview(self) -> None:
        """Preview changes (spec S-23)."""
        if self.service is not None:
            PreviewDialog(self.service.preview(), self).exec()

    def selected_id(self) -> str | None:
        """Return the shown profile's ID (chosen in the sidebar popover)."""
        return self._shown_id

    def select_profile(self, profile_id: str) -> None:
        """Show a profile by its ID (the sidebar popover switched to it)."""
        if self.service is None or profile_id not in [p.id for p in self.service.profiles]:
            return
        if profile_id != self._shown_id:
            self._shown_id = profile_id
            self._show_replacements()
            self.shown.emit(profile_id)

    def _current_rid(self) -> str | None:
        item = self.rows.currentItem()
        return None if item is None else str(item.data(RID))

    # --- Copy (law 2: a shortened target stays copyable) ------------------------------------

    def _copy_current(self) -> None:
        item = self.rows.currentItem()
        if item is not None and item.text():
            QGuiApplication.clipboard().setText(item.text())

    def _row_menu(self, where: QPoint) -> None:
        item = self.rows.itemAt(where)
        if item is None or not item.text():
            return
        menu = QMenu(self.rows)
        menu.addAction(self.tr("Copy")).triggered.connect(
            lambda: QGuiApplication.clipboard().setText(item.text())
        )
        menu.exec(self.rows.viewport().mapToGlobal(where))

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
        created = self._edit("create", QCoreApplication.translate("M-PROF-07", "My replacements"))
        self._shown_id = created.id
        self._open_editor()

    def delete_profile(self, profile_id: str | None) -> None:
        """Delete a profile after confirming; the window shows "Undo" (also the sidebar popover)."""
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
        if profile_id == self._shown_id:
            self._shown_id = None
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
        self._shown_id = profile.id
        self._deleted = None
        self.refresh()

    def _open_editor(self) -> None:
        if self._shown_id is None and self.service is not None and self.service.profiles:
            self._shown_id = self.service.profiles[0].id
        if self.service is not None and self._shown_id is not None:
            profile = self.service.store.get(self._shown_id)
            self.editor.start(self.service.store.folder / profile.name)
        else:
            self.editor.start()

    def _save(self, original: grafts.Original, target: grafts.Target, family: str) -> None:
        if self._shown_id is None:
            return
        try:
            self._edit("add_replacement", self._shown_id, original, target, family)
        except grafts.ProfileError as error:  # a refusal the user can act on: say it in place
            self.editor.problem.setText(str(error))
            return
        self.editor.hide()

    def _remove(self) -> None:
        rid = self._current_rid()
        if self._shown_id is None or rid is None:
            return
        self._edit("remove_replacement", self._shown_id, rid)

    # --- Drop anywhere (Qt API) -------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        """Accept a dropped local file or a link anywhere on the screen."""
        if self.service is not None and dropped_target(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        """Open the editor on the dropped file or link, ready to save (drop anywhere)."""
        target = dropped_target(event.mimeData())
        if self.service is None or target is None:
            return
        self._open_editor()
        kind, value = target
        self.editor.use_dropped(kind, value)
        event.acceptProposedAction()
