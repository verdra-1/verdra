# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12 in the interface: Launch Roblox, links, refusals, the status fixes, M-SHELL-02."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.notice import Notice
from verdra.trunk.sapwood.startup import Services


class StubSprout(QObject):
    """Records what the interface asks of trunk's Sprout."""

    refused = Signal(str)
    other_tool = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None]] = []
        self.running = False

    def launch(self, link: str | None = None) -> None:
        self.calls.append(("launch", link))

    def start_routing(self) -> None:
        self.calls.append(("start", None))

    def retry(self) -> None:
        self.calls.append(("retry", None))

    def repair_certificate(self) -> None:
        self.calls.append(("repair", None))

    def roblox_running(self) -> bool:
        return self.running


@pytest.fixture
def stub(services: Services) -> Iterator[StubSprout]:
    made = StubSprout()
    services.sprout = made  # type: ignore[assignment]
    yield made
    services.sprout = None
    made.deleteLater()


@pytest.fixture
def launching(services: Services, stub: StubSprout, qtbot: QtBot) -> Iterator[Shell]:
    made = Shell(services)
    made.build()
    qtbot.addWidget(made.window)
    yield made
    made.window.allow_close = True
    made.window.close()


def library_button(shell: Shell) -> QPushButton:
    [button] = shell.window.screens["library"].empty.buttons  # type: ignore[attr-defined]
    return button


def test_launch_roblox_in_the_library_starts_roblox_through_verdra(
    launching: Shell, stub: StubSprout
) -> None:
    button = library_button(launching)
    assert button.isEnabled()
    button.click()
    assert stub.calls == [("launch", None)]


def test_without_routing_the_library_button_says_why(shell: Shell) -> None:
    button = library_button(shell)  # type: ignore[arg-type]
    assert not button.isEnabled()
    assert button.toolTip()


def test_a_roblox_link_starts_roblox_with_that_link(launching: Shell, stub: StubSprout) -> None:
    link = "roblox-player:1+launchmode:play+gameinfo:abc"
    launching.activate(link)
    launching.activate("")
    assert stub.calls == [("launch", link)]


def test_a_refusal_is_a_notice(launching: Shell, stub: StubSprout) -> None:
    stub.refused.emit("Roblox isn't installed, or Verdra couldn't find it.")
    notices = launching.window.findChildren(Notice)
    assert any("Roblox isn't installed" in n.label.text() for n in notices)


def test_the_status_fixes_start_routing_or_relaunch(launching: Shell, stub: StubSprout) -> None:
    popover = launching.window.header.popover
    assert set(popover.handled) == {"start", "retry", "restart_roblox", "repair_certificate"}
    assert popover.fix.isEnabled()  # Idle: "Start routing"
    for key in ("start", "retry", "restart_roblox", "repair_certificate"):
        popover.fix_requested.emit(key)
    assert stub.calls == [("start", None), ("retry", None), ("launch", None), ("repair", None)]


def test_quitting_while_roblox_runs_asks_first(
    launching: Shell, stub: StubSprout, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    asked: list[str] = []
    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(True))

    def answer(self: DestructiveConfirmation) -> int:
        asked.append(self.windowTitle() or self.findChildren(QPushButton)[-1].text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(DestructiveConfirmation, "exec", answer)
    stub.running = True
    launching.quit()
    assert len(asked) == 1 and quits == []  # canceled: Verdra keeps running
    stub.running = False
    launching.quit()
    assert len(asked) == 1 and quits == [True]  # nothing running: no question


@pytest.mark.spec("S-15", 2)
def test_another_tool_asks_and_try_again_checks_again(
    launching: Shell, stub: StubSprout, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = [QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected]
    shown: list[str] = []

    def answer(self: DestructiveConfirmation) -> int:
        shown.append(self.findChildren(QPushButton)[-1].text())
        return answers.pop(0)

    monkeypatch.setattr(DestructiveConfirmation, "exec", answer)
    text = "Another tool is already routing Roblox traffic. Close it, then try again."
    stub.other_tool.emit(text)  # "Try again"
    stub.other_tool.emit(text)  # "Cancel"
    assert shown == ["Try again", "Try again"]
    assert stub.calls == [("retry", None)]


def test_how_a_dialog_was_answered_is_logged(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    """Stage 2 showed M-SHELL-02 twice; the log must say how each was answered."""
    for answer, said in ((QDialog.accept, "with its action"), (QDialog.reject, "with Cancel")):
        dialog = DestructiveConfirmation("Quit Verdra while Roblox is running?", "Quit")
        qtbot.addWidget(dialog)
        with caplog.at_level("DEBUG", logger="verdra"):
            answer(dialog)  # finished() follows accept() and reject() whether shown or not
        assert f"Dialog answered {said}: Quit Verdra while Roblox is running?" in caplog.text
        caplog.clear()
