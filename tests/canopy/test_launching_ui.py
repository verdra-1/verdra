# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12 in the interface: Launch Roblox, links, refusals, the status fixes, M-SHELL-02."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.dew import Toast
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import Choice, DestructiveConfirmation, Information
from verdra.canopy.leaves.notice import Notice
from verdra.trunk.sapwood.startup import Services


class StubSprout(QObject):
    """Records what the interface asks of trunk's Sprout."""

    refused = Signal(str)
    other_tool = Signal(str)
    backups_changed = Signal()
    others_changed = Signal(bool)
    held_back = Signal(str)
    handed_off = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None]] = []
        self.running = False
        #: Players Verdra didn't start (M-LAUNCH-08); closing them only empties this.
        self.others: frozenset[int] = frozenset()
        self.closable = True

    def launch(self, link: str | None = None, *, despite_others: bool = False) -> None:
        self.calls.append(("launch anyway" if despite_others else "launch", link))

    def refresh_others(self) -> frozenset[int]:
        self.others_changed.emit(bool(self.others))
        return self.others

    def close_others(self) -> None:
        self.calls.append(("close others", None))
        if self.closable:
            self.others = frozenset()
        self.refresh_others()

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
    assert set(popover.handled) == {
        "start",
        "retry",
        "restart_roblox",
        "repair_certificate",
        "close_others",
    }
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


# --- A Roblox Player Verdra didn't start (M-LAUNCH-08 to M-LAUNCH-18) ------------------------

BANNER = "Roblox is already running without Verdra. Close it completely, then click Apply now."


def banner_of(shell: Shell) -> Notice | None:
    found = [n for n in shell.window.findChildren(Notice) if n.label.text() == BANNER]
    return found[0] if found and found[0].isVisibleTo(shell.window) else None


def answer_with(monkeypatch: pytest.MonkeyPatch, cls: type[QDialog], result: int) -> list[str]:
    asked: list[str] = []

    def answer(self: QDialog) -> int:
        asked.append(self.windowTitle())
        return result

    monkeypatch.setattr(cls, "exec", answer)
    return asked


@pytest.mark.spec("S-12", 8)
def test_a_banner_says_roblox_runs_without_verdra_until_it_closes(
    launching: Shell, stub: StubSprout, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert banner_of(launching) is None
    stub.others = frozenset({4242})
    stub.refresh_others()
    banner = banner_of(launching)
    assert banner is not None
    help_button, close_button = banner.findChildren(QPushButton)[:2]
    assert (help_button.text(), close_button.text()) == ("How to close it", "Close Roblox…")
    shown = answer_with(monkeypatch, Information, QDialog.DialogCode.Rejected)
    help_button.click()
    assert shown == ["How to close Roblox completely"]
    asked = answer_with(monkeypatch, DestructiveConfirmation, QDialog.DialogCode.Rejected)
    close_button.click()
    assert len(asked) == 1
    assert stub.calls == []  # canceled: Roblox is never closed without a yes
    answer_with(monkeypatch, DestructiveConfirmation, QDialog.DialogCode.Accepted)
    close_button.click()
    assert stub.calls == [("close others", None)]
    assert banner_of(launching) is None  # closed: the banner goes away


def test_the_status_fix_closes_the_other_roblox_after_asking(
    launching: Shell, stub: StubSprout, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub.others = frozenset({4242})
    asked = answer_with(monkeypatch, DestructiveConfirmation, QDialog.DialogCode.Accepted)
    launching.window.header.popover.fix_requested.emit("close_others")
    assert asked == [
        "Close the Roblox that is running without Verdra? Unsaved progress in its game may be lost."
    ]
    assert stub.calls == [("close others", None)]


@pytest.mark.parametrize(
    ("choice", "closable", "calls"),
    [
        ("primary", True, [("close others", None), ("launch", "roblox-player:1")]),
        ("primary", False, [("close others", None)]),  # it didn't close: no join
        ("secondary", True, [("launch anyway", "roblox-player:1")]),
        ("", True, []),  # Cancel
    ],
)
@pytest.mark.spec("S-12", 8)
def test_a_held_back_join_does_what_the_user_chose(  # noqa: PLR0917 - parametrized
    launching: Shell,
    stub: StubSprout,
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
    closable: bool,  # noqa: FBT001
    calls: list[tuple[str, str | None]],
) -> None:
    stub.others = frozenset({4242})
    stub.closable = closable
    asked: list[str] = []

    def answer(self: Choice) -> int:
        asked.append(self.windowTitle())
        self.choice = choice
        return QDialog.DialogCode.Accepted if choice else QDialog.DialogCode.Rejected

    monkeypatch.setattr(Choice, "exec", answer)
    stub.held_back.emit("roblox-player:1")
    assert asked == ["Roblox is already running without Verdra"]
    assert stub.calls == calls


def test_a_join_handed_to_the_other_roblox_is_a_warning(launching: Shell, stub: StubSprout) -> None:
    stub.handed_off.emit("Roblox handed this game to the Roblox that was already running.")
    texts = [t.text for t in launching.window.findChildren(Toast)]
    assert "Roblox handed this game to the Roblox that was already running." in texts


def test_the_choice_dialog_names_both_actions_and_cancel(qtbot: QtBot) -> None:
    dialog = Choice("Question", "Body", "Do it", "Do the other")
    qtbot.addWidget(dialog)
    texts = [b.text() for b in dialog.findChildren(QPushButton)]
    assert sorted(texts) == sorted(["Cancel", "Do the other", "Do it"])
    dialog.secondary.click()
    assert dialog.choice == "secondary"
