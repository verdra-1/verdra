# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Specs S-25 and S-26 in the table: status pills, banner, filters, switch and row actions."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QInputDialog
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import FakeSettings
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.screens.grafts import screen as screen_module
from verdra.canopy.screens.grafts.screen import NOTE, ON, ORIGINAL, STATUS, ReplacementsScreen
from verdra.strata import ochre
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Target
from verdra.trunk.sapwood import startup


@pytest.fixture
def made(tmp_path: Path, qtbot: QtBot) -> Iterator[tuple[ReplacementsScreen, grafts.Grafts, str]]:
    service = grafts.Grafts(tmp_path / "profiles", FakeSettings())
    profile = service.edit("create", "A")
    shown = ReplacementsScreen(None, service)
    qtbot.addWidget(shown)
    yield shown, service, profile.id
    service.deleteLater()


def add(service: grafts.Grafts, profile_id: str, original: int, target: int) -> str:
    added = service.edit(
        "add_replacement",
        profile_id,
        Original(asset_id=original),
        Target(kind="asset_id", value=str(target)),
        "Image",
    )
    return added.id


def words(shown: ReplacementsScreen) -> list[str]:
    return [shown.table.item(row, STATUS).text() for row in range(shown.table.rowCount())]  # type: ignore[union-attr]


def select(shown: ReplacementsScreen, *rows: int) -> None:
    shown.table.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for row in rows:
        shown.table.selectionModel().select(shown.table.model().index(row, 0), flags)


@pytest.mark.spec("S-25", 4)
def test_every_status_has_its_own_word_and_accessible_text(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)  # live
    add(service, profile_id, ABOVE_UINT32, 2222222)  # seen
    edited = add(service, profile_id, 5555555, 6666666)
    off = add(service, profile_id, 7777777, 8888888)
    deleted = add(service, profile_id, 9999999, 1212121)
    service.edit("set_replacements_enabled", profile_id, [off], False)
    service.publish()
    service.loads.record(ABOVE_UINT32, 0)
    service.loads.record(ABOVE_UINT32, 0)
    row = next(r for r in service.store.get(profile_id).replacements if r.id == edited)
    row.target = Target(kind="asset_id", value="1313131")
    service.edit("edit_replacement", profile_id, row)
    service.edit("remove_replacement", profile_id, deleted)
    add(service, profile_id, 3333333, 4444444)  # new
    shown.refresh()
    assert words(shown) == [
        "Live · not seen yet",
        "Live · seen 2×",
        "Edited · apply to update",
        "Off",
        "Deleted · apply to remove",
        "New · not applied",
    ]
    # Every status word differs, so nothing relies on color (S-25 rule 4, design J4).
    states = {
        grafts.Status.NEW,
        grafts.Status.EDITED,
        grafts.Status.DELETED,
        grafts.Status.LIVE,
        grafts.Status.SEEN,
        grafts.Status.PROBLEM,
        grafts.Status.OFF,
    }
    labels = {
        screen_module.status_word(grafts.RowState(state, loads=2, detail="file missing"))
        for state in states
    }
    assert len(labels) == len(states)
    status = shown.table.item(4, STATUS)
    assert status is not None
    assert status.data(Qt.ItemDataRole.AccessibleTextRole) == "Deleted · apply to remove"
    assert status.font().strikeOut()
    assert "The game keeps it until you click Review & apply." in status.toolTip()


def test_the_banner_counts_what_waits_and_hides_when_nothing_does(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], qapp: QApplication
) -> None:
    shown, service, profile_id = made
    translator = startup.install_translator(qapp, "en")  # the plural forms (R5)
    assert translator is not None
    add(service, profile_id, ABOVE_INT32, 1111111)
    add(service, profile_id, ABOVE_UINT32, 2222222)
    shown.refresh()
    assert shown.banner.isVisibleTo(shown)
    assert shown.banner.label.text() == (
        "2 changes are waiting. They reach the game when you click Review & apply."
    )
    service.publish()
    shown.refresh()
    assert not shown.banner.isVisibleTo(shown)
    add(service, profile_id, 3333333, 4444444)
    shown.refresh()
    assert shown.banner.label.text() == (
        "1 change is waiting. It reaches the game when you click Review & apply."
    )  # the catalogue's singular (a plural entry)
    qapp.removeTranslator(translator)


def test_filters_show_matching_rows_and_their_counts_add_up(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    add(service, profile_id, ABOVE_UINT32, 2222222)  # waiting
    shown.refresh()
    assert [chip.text() for chip in shown.chips.values()] == [
        "All 2",
        "Live 1",
        "Waiting 1",
        "Problem 0",
        "Off 0",
    ]
    shown.chips["waiting"].click()
    assert words(shown) == ["New · not applied"]
    shown.chips["live"].click()
    assert words(shown) == ["Live · not seen yet"]
    shown.chips["all"].click()
    assert shown.table.rowCount() == 2


def test_the_switch_space_and_the_bulk_menu_switch_rows(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], qtbot: QtBot
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    add(service, profile_id, ABOVE_UINT32, 2222222)
    shown.refresh()
    switch = shown.table.item(0, ON)
    assert switch is not None
    switch.setCheckState(Qt.CheckState.Unchecked)  # the click on the switch
    assert not service.store.get(profile_id).replacements[0].enabled
    select(shown, 0, 1)
    qtbot.keyClick(shown.table, Qt.Key.Key_Space)  # not all on: switches both on
    assert all(r.enabled for r in service.store.get(profile_id).replacements)
    qtbot.keyClick(shown.table, Qt.Key.Key_Space)
    assert not any(r.enabled for r in service.store.get(profile_id).replacements)
    service.edit("undo")
    assert all(r.enabled for r in service.store.get(profile_id).replacements)


def test_delete_asks_first_and_a_live_row_stays_until_applied(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    shown.refresh()
    asked: list[str] = []

    def answer(dialog: DestructiveConfirmation) -> int:
        asked.append(type(dialog).__name__)
        return DestructiveConfirmation.DialogCode.Accepted

    monkeypatch.setattr(DestructiveConfirmation, "exec", answer)
    select(shown, 0)
    qtbot.keyClick(shown.table, Qt.Key.Key_Delete)
    assert asked
    assert words(shown) == ["Deleted · apply to remove"]
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}  # still live


def test_duplicate_moves_and_revert(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shown, service, profile_id = made
    first = add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    shown.refresh()
    select(shown, 0)
    shown._duplicate()  # noqa: SLF001 - the menu's action
    rows = service.store.get(profile_id).replacements
    assert [r.id for r in rows][0] == first
    assert (rows[1].enabled, rows[1].note) == (False, "Copy")  # owner, question N7
    row = rows[0]
    row.target = Target(kind="asset_id", value="2222222")
    service.edit("edit_replacement", profile_id, row)
    select(shown, 0)
    shown._revert()  # noqa: SLF001
    assert service.store.get(profile_id).replacements[0].target.value == "1111111"
    other = service.edit("create", "B")
    shown.profiles.setCurrentRow([p.id for p in service.profiles].index(profile_id))
    select(shown, 0)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_a, **_k: ("B", True))
    shown._move()  # noqa: SLF001
    moved = service.store.get(other.id).replacements
    assert [r.original.asset_id for r in moved] == [ABOVE_INT32]
    left = service.store.get(profile_id).replacements[0]
    assert left.deleted  # live until applied (owner, question N5)
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}


def test_a_note_is_edited_in_place(made: tuple[ReplacementsScreen, grafts.Grafts, str]) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    shown.refresh()
    note = shown.table.item(0, NOTE)
    assert note is not None
    note.setText("Lobby wall")
    saved = service.store.get(profile_id).replacements[0]
    assert saved.note == "Lobby wall"
    assert service.waiting() == 0  # a note is not a change the game sees


def test_a_picture_dropped_on_a_row_becomes_its_local_file(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], tmp_path: Path
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    shown.refresh()
    picture = tmp_path / "wall.png"
    picture.write_bytes(ochre.to_png(ochre.Pixels(1, 1, b"\0\0\0\xff")))
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(picture))])
    target = shown.table.visualItemRect(shown.table.item(0, ORIGINAL)).center()  # type: ignore[arg-type]
    event = QDropEvent(
        QPointF(target),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    shown.table.dropEvent(event)
    saved = service.store.get(profile_id).replacements[0]
    assert saved.target == Target(kind="file", value=str(picture))
