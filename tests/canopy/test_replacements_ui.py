# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Specs S-20, S-22 and S-24 in the interface: the Replacements screen and Apply now."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.dew import Toast
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.soil import terrain
from verdra.trunk.branches import grafts
from verdra.trunk.sapwood import startup
from verdra.trunk.sapwood.startup import Services


class StubSprout(QObject):
    """Records what Apply now asks of trunk's Sprout."""

    refused = Signal(str)
    other_tool = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.running = False
        self.routing = True

    def roblox_running(self) -> bool:
        return self.running

    def restart_roblox(self) -> None:
        self.calls.append("restart")

    def start_routing(self) -> None:
        self.calls.append("start")


@pytest.fixture(autouse=True)
def catalog(qapp: QApplication) -> Iterator[None]:
    """The English catalogue, which gives M-APPLY-02 and M-APPLY-03 their plural forms."""
    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    yield
    qapp.removeTranslator(translator)
    translator.deleteLater()


@pytest.fixture
def made(services: Services, qtbot: QtBot) -> Iterator[tuple[Shell, StubSprout]]:
    services.grafts = grafts.Grafts(terrain.config_dir() / "profiles", services.settings)
    stub = StubSprout()
    services.sprout = stub  # type: ignore[assignment]
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    yield shell, stub
    shell.window.allow_close = True
    shell.window.close()
    services.sprout = None
    stub.deleteLater()
    services.grafts.deleteLater()


def screen_of(shell: Shell) -> ReplacementsScreen:
    screen = shell.window.screens["replacements"]
    assert isinstance(screen, ReplacementsScreen)
    return screen


def toasts(shell: Shell) -> list[str]:
    return [t.text for t in shell.window.findChildren(Toast)]


@pytest.mark.spec("S-22", 3)
def test_a_first_replacement_from_the_empty_state_with_the_keyboard(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    shell, _stub = made
    screen = screen_of(shell)
    assert screen.stack.currentWidget() is screen.empty
    add, presets = screen.empty.buttons
    assert add.isEnabled() and not presets.isEnabled()
    add.click()  # makes "My replacements" and opens the editor with the cursor in it
    assert screen.stack.currentWidget() is screen.main
    editor = screen.editor
    assert not editor.isHidden()
    assert not editor.save.isEnabled() and editor.save.toolTip()
    qtbot.keyClicks(editor.original, "1111111")
    editor.target.setFocus()
    qtbot.keyClicks(editor.target, "1111111")
    assert editor.save.toolTip() == "An asset can't replace itself. Enter a different asset ID."
    editor.target.clear()
    qtbot.keyClicks(editor.target, "2222222")
    assert editor.save.isEnabled()
    qtbot.keyClick(editor.target, Qt.Key.Key_Return)  # saves
    assert editor.isHidden()
    [profile] = shell.services.grafts.profiles  # type: ignore[union-attr]
    assert profile.name == "My replacements"
    assert [(r.original.asset_id, r.target.value) for r in profile.replacements] == [
        (1111111, "2222222")
    ]
    assert screen.table.rowCount() == 1
    cell = screen.table.item(0, 1)
    assert cell is not None and cell.text() == "2222222"
    saved = json.loads((terrain.config_dir() / "profiles" / "My replacements.json").read_bytes())
    assert saved["replacements"][0]["target"] == {"kind": "asset_id", "value": "2222222"}


def test_only_asset_id_targets_can_be_chosen_for_now(made: tuple[Shell, StubSprout]) -> None:
    screen = screen_of(made[0])
    buttons = screen.editor.kinds.buttons()
    assert [b.isEnabled() for b in buttons] == [True, False, False, False]
    assert all(b.toolTip() for b in buttons[1:])


@pytest.mark.spec("S-20", 4)
def test_profiles_switch_undo_and_delete_from_the_screen(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    shell, _stub = made
    screen = screen_of(shell)
    service = shell.services.grafts
    assert service is not None
    screen.empty.buttons[0].click()
    screen.editor.hide()
    qtbot.keyClicks(screen.new_name, "Night")
    qtbot.keyClick(screen.new_name, Qt.Key.Key_Return)
    assert [p.name for p in service.profiles] == ["Night", "My replacements"]
    current = screen.profiles.currentItem()
    assert current is not None and current.text() == "Night"
    qtbot.keyClicks(screen.new_name, "night")  # same name, other case
    qtbot.keyClick(screen.new_name, Qt.Key.Key_Return)
    assert screen.name_problem.text() == "A profile named night already exists."
    current = screen.profiles.currentItem()
    assert current is not None
    current.setCheckState(Qt.CheckState.Unchecked)
    assert not service.profiles[0].enabled
    screen.undo.click()
    assert service.profiles[0].enabled
    screen.redo.click()
    assert not service.profiles[0].enabled
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _self: QDialog.DialogCode.Accepted)
    screen.delete_profile.click()
    assert [p.name for p in service.profiles] == ["My replacements"]


@pytest.mark.spec("S-24", 3)
def test_apply_now_without_roblox_running_publishes_and_says_next_time(
    made: tuple[Shell, StubSprout],
) -> None:
    shell, stub = made
    service = shell.services.grafts
    assert service is not None
    profile = service.edit("create", "A")
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=1111111),
        grafts.Target(kind="asset_id", value="2222222"),
    )
    assert service.holder.current.swaps() == {}  # nothing applies before Apply now
    header = shell.window.header
    assert header.apply_now.isEnabled()
    header.apply_now.click()
    assert service.holder.current.swaps() == {1111111: 2222222}
    assert stub.calls == []
    assert toasts(shell)[-1] == "Applied 1 replacement. They'll appear next time Roblox starts."
    stub.routing = False
    header.apply_now.click()
    assert stub.calls == ["start"]  # S-24 rule 2: routing starts first


@pytest.mark.spec("S-24", 4)
def test_canceling_the_restart_publishes_and_closes_nothing(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, stub = made
    stub.running = True
    asked: list[str] = []

    def answer(dialog: DestructiveConfirmation) -> int:
        asked.append(dialog.findChildren(type(shell.window.header.apply_now))[-1].text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(DestructiveConfirmation, "exec", answer)
    shell.window.header.apply_now.click()
    assert asked == ["Restart Roblox"]
    assert stub.calls == []
    assert toasts(shell)[-1] == "Applied 0 replacements. They'll appear next time Roblox starts."


@pytest.mark.spec("S-24", 2)
def test_confirming_restarts_only_the_roblox_verdra_launched(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, stub = made
    stub.running = True
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _self: QDialog.DialogCode.Accepted)
    shell.window.header.apply_now.click()
    assert stub.calls == ["restart"]  # Sprout closes only its own launches (S-12 rule 4)
    assert toasts(shell)[-1].startswith("Applied 0 replacements. Assets Roblox already saved")


def test_without_the_service_the_screen_and_apply_now_say_why(shell: Shell) -> None:
    screen = screen_of(shell)
    assert not any(b.isEnabled() for b in screen.empty.buttons)
    assert not shell.window.header.apply_now.isEnabled()


def test_startup_publishes_saved_replacements(home: Path, services: Services) -> None:
    folder = terrain.config_dir() / "profiles"
    first = grafts.Grafts(folder, services.settings)
    profile = first.edit("create", "A")
    first.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=5),
        grafts.Target(kind="asset_id", value="6"),
    )
    again = grafts.Grafts(folder, services.settings)
    assert again.publish() == 1
    assert again.holder.current.swaps() == {5: 6}
    first.deleteLater()
    again.deleteLater()
