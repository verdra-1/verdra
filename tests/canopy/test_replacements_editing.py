# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-26 in the editor drawer: open any row, save for later, revert, discard, names."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import FakeSettings
from verdra.bark import pollinator
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.screens.grafts.screen import ORIGINAL, STATUS, ReplacementsScreen
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Status, Target


@pytest.fixture
def made(tmp_path: Path, qtbot: QtBot) -> Iterator[tuple[ReplacementsScreen, grafts.Grafts, str]]:
    service = grafts.Grafts(tmp_path / "profiles", FakeSettings())
    profile = service.edit("create", "A")
    shown = ReplacementsScreen(None, service)
    qtbot.addWidget(shown)
    shown.show()
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


def rows(service: grafts.Grafts, profile_id: str) -> list[grafts.Replacement]:
    return service.store.get(profile_id).replacements


def click_row(shown: ReplacementsScreen, qtbot: QtBot, row: int) -> None:
    item = shown.table.item(row, ORIGINAL)
    assert item is not None
    qtbot.mouseClick(
        shown.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=shown.table.visualItemRect(item).center(),
    )


def status(shown: ReplacementsScreen, row: int) -> str:
    item = shown.table.item(row, STATUS)
    assert item is not None
    return item.text()


@pytest.mark.spec("S-26", 1)
def test_a_click_opens_the_row_filled_in_and_saving_keeps_the_live_version(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], qtbot: QtBot
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    shown.refresh()
    click_row(shown, qtbot, 0)
    editor = shown.editor
    assert editor.isVisible()
    assert editor.heading.text() == "Edit replacement"
    assert (editor.original.text(), editor.kind(), editor.target.text()) == (
        str(ABOVE_INT32),
        "asset_id",
        "1111111",
    )
    assert editor.status.text() == "Live · not seen yet"
    assert editor.save.text() == "Save · apply later"
    assert not editor.revert.isVisibleTo(editor)  # nothing to revert yet
    editor.target.setText("2222222")
    qtbot.keyClick(editor.target, Qt.Key.Key_Return)
    assert not editor.isVisible()
    [row] = rows(service, profile_id)
    assert row.target.value == "2222222"
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}  # the game keeps it
    assert status(shown, 0) == "Edited · apply to update"
    service.publish()  # the review's apply (S-27 replaces Apply now in PR f)
    assert service.holder.current.swaps() == {ABOVE_INT32: 2222222}


@pytest.mark.spec("S-26", 5)
def test_revert_in_the_drawer_makes_the_row_live_again(
    made: tuple[ReplacementsScreen, grafts.Grafts, str], qtbot: QtBot
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    [row] = rows(service, profile_id)
    row.target = Target(kind="asset_id", value="2222222")
    service.edit("edit_replacement", profile_id, row)
    shown.refresh()
    qtbot.keyClick(shown.table, Qt.Key.Key_Down)
    qtbot.keyClick(shown.table, Qt.Key.Key_Return)  # Enter opens the row (rule 8)
    editor = shown.editor
    assert editor.status.text() == "Edited · apply to update"
    assert editor.revert.isVisibleTo(editor)
    editor.revert.click()
    [reverted] = rows(service, profile_id)
    assert reverted.target.value == "1111111"
    assert service.states(service.store.get(profile_id))[reverted.id].status is Status.LIVE
    assert editor.target.text() == "1111111"  # the drawer shows the live version
    assert editor.status.text() == "Live · not seen yet"


@pytest.mark.spec("S-26", 2)
def test_switching_a_live_row_off_then_on(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
) -> None:
    shown, service, profile_id = made
    row_id = add(service, profile_id, ABOVE_INT32, 1111111)
    service.publish()
    service.edit("set_replacements_enabled", profile_id, [row_id], False)
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}  # until applied
    service.publish()
    assert service.holder.current.swaps() == {}  # the client gets the original
    service.edit("set_replacements_enabled", profile_id, [row_id], True)
    shown.refresh()
    assert status(shown, 0) == "New · not applied"


@pytest.mark.parametrize("answer", ["Keep editing", "Discard"])
def test_closing_with_unsaved_changes_asks_first(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    shown.refresh()
    click_row(shown, qtbot, 0)
    editor = shown.editor
    qtbot.keyClick(editor.target, Qt.Key.Key_Escape)
    assert not editor.isVisible()  # nothing changed: closes without asking
    click_row(shown, qtbot, 0)
    editor.target.setText("2222222")
    asked: list[tuple[str, str, str]] = []

    def reply(dialog: DestructiveConfirmation) -> int:
        asked.append((dialog.title.text(), dialog.confirm.text(), dialog.cancel.text()))
        return (
            DestructiveConfirmation.DialogCode.Accepted
            if answer == "Discard"
            else DestructiveConfirmation.DialogCode.Rejected
        )

    monkeypatch.setattr(DestructiveConfirmation, "exec", reply)
    qtbot.keyClick(editor.target, Qt.Key.Key_Escape)
    assert asked == [("Discard your changes to this replacement?", "Discard", "Keep editing")]
    assert editor.isVisible() is (answer == "Keep editing")
    assert rows(service, profile_id)[0].target.value == "1111111"  # never saved


def test_the_row_menu_offers_edit_for_one_row(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    add(service, profile_id, ABOVE_UINT32, 2222222)
    shown.refresh()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    shown.table.selectionModel().select(shown.table.model().index(0, 0), flags)
    one = [a.text() for a in shown._bulk_menu(shown).actions()]  # noqa: SLF001
    assert one[0] == "Edit"
    shown.table.selectionModel().select(shown.table.model().index(1, 0), flags)
    assert "Edit" not in [a.text() for a in shown._bulk_menu(shown).actions()]  # noqa: SLF001


def test_the_name_from_robloxs_answer_is_saved_and_shown_without_an_undo_step(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner, question N8: shown only when Roblox's answer carries a name."""
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    shown.refresh()
    monkeypatch.setattr(
        pollinator, "asset_kind", lambda _asset_id: pollinator.AssetKind(1, "Wall picture")
    )
    steps = len(service.store._undo)  # noqa: SLF001
    click_row(shown, qtbot, 0)  # opening a row saved before looks its original up
    qtbot.waitUntil(lambda: rows(service, profile_id)[0].name == "Wall picture")
    assert len(service.store._undo) == steps  # noqa: SLF001 - display only, not an edit
    original = shown.table.item(0, ORIGINAL)
    assert original is not None
    assert original.text() == f"{ABOVE_INT32} · Wall picture"
    assert service.waiting() == 1  # still just the new row: a name isn't a change


def test_a_name_isnt_invented_when_the_answer_has_none(
    made: tuple[ReplacementsScreen, grafts.Grafts, str],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown, service, profile_id = made
    add(service, profile_id, ABOVE_INT32, 1111111)
    shown.refresh()
    asked: list[int] = []

    def kind(asset_id: int) -> pollinator.AssetKind:
        asked.append(asset_id)
        return pollinator.AssetKind(1)

    monkeypatch.setattr(pollinator, "asset_kind", kind)
    click_row(shown, qtbot, 0)
    qtbot.waitUntil(lambda: ABOVE_INT32 in asked)
    original = shown.table.item(0, ORIGINAL)
    assert original is not None
    assert original.text() == str(ABOVE_INT32)
