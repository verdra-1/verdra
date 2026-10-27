# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The profile popover emits intents and never runs profile logic of its own (D3 screen 2)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.profiles import ProfilePopover


@dataclass(frozen=True)
class _Profile:
    id: str
    name: str
    enabled: bool = True


def _profile(pid: str, name: str, *, enabled: bool = True) -> _Profile:
    return _Profile(id=pid, name=name, enabled=enabled)


def _shown(qtbot: QtBot) -> ProfilePopover:
    popover = ProfilePopover()
    qtbot.addWidget(popover)
    return popover


def test_the_list_shows_each_profile_with_its_on_off_box(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([_profile("a", "Day"), _profile("b", "Night", enabled=False)], "a")
    assert popover.list.count() == 2
    assert popover.list.currentItem().text() == "Day"
    assert popover.list.item(0).checkState() == Qt.CheckState.Checked
    assert popover.list.item(1).checkState() == Qt.CheckState.Unchecked


def test_picking_a_profile_asks_to_switch_to_it(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([_profile("a", "Day"), _profile("b", "Night")], "a")
    with qtbot.waitSignal(popover.selected) as signal:
        popover.list.setCurrentRow(1)
    assert signal.args == ["b"]


def test_ticking_the_box_asks_to_turn_a_profile_off(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([_profile("a", "Day")], "a")
    with qtbot.waitSignal(popover.enabled_changed) as signal:
        popover.list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert signal.args == ["a", False]


def test_editing_the_label_asks_for_a_rename_not_an_enable(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([_profile("a", "Day")], "a")
    with qtbot.waitSignal(popover.rename_requested) as signal:
        popover.list.item(0).setText("Daytime")
    assert signal.args == ["a", "Daytime"]


def test_new_profile_asks_to_create_with_the_typed_name(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([], None)
    popover.new_name.setText("  Weekend  ")
    with qtbot.waitSignal(popover.create_requested) as signal:
        popover.new_name.returnPressed.emit()
    assert signal.args == ["Weekend"]  # trimmed


def test_a_blank_new_name_asks_for_nothing(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([], None)
    popover.new_name.setText("   ")
    with qtbot.assertNotEmitted(popover.create_requested):
        popover.new_name.returnPressed.emit()


def test_delete_asks_to_delete_the_current_profile(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([_profile("a", "Day"), _profile("b", "Night")], "b")
    with qtbot.waitSignal(popover.delete_requested) as signal:
        popover.delete.click()
    assert signal.args == ["b"]


def test_rename_and_delete_are_off_with_no_profile(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_profiles([], None)
    assert not popover.rename.isEnabled()
    assert not popover.delete.isEnabled()


def test_a_name_problem_is_shown_then_cleared(qtbot: QtBot) -> None:
    popover = _shown(qtbot)
    popover.show_problem("That name is already taken.")
    assert popover.problem.isVisibleTo(popover)
    assert popover.problem.text() == "That name is already taken."
    popover.clear_new_name()
    assert not popover.problem.isVisibleTo(popover)
    assert popover.new_name.text() == ""
