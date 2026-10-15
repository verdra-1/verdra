# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-27 in the window: the Review & apply dialog, the header button, Undo."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from tests.canopy.applying import StubSprout, toasts
from tests.ids import ABOVE_INT32, ABOVE_UINT32
from verdra.canopy.crown.dew import Toast
from verdra.canopy.crown.window import APPLY_COOLDOWN_SECONDS, Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.screens.grafts.review import BADGE, DETAIL, PICTURE, ReviewDialog, Roblox
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Target
from verdra.trunk.sapwood import startup


def add(service: grafts.Grafts, profile_id: str, original: int, target: int | str) -> str:
    kind = "asset_id" if isinstance(target, int) else "file"
    added = service.edit(
        "add_replacement",
        profile_id,
        Original(asset_id=original),
        Target(kind=kind, value=str(target)),
        "Image",
    )
    return added.id


def answering(
    monkeypatch: pytest.MonkeyPatch, act: Callable[[ReviewDialog], int]
) -> list[ReviewDialog]:
    shown: list[ReviewDialog] = []

    def run(dialog: ReviewDialog) -> int:
        shown.append(dialog)
        return act(dialog)

    monkeypatch.setattr(ReviewDialog, "exec", run)
    return shown


@pytest.fixture(autouse=True)
def catalog(qapp: QApplication) -> Iterator[None]:
    """The English catalogue: the plural forms ("1 change applied.")."""
    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    yield
    qapp.removeTranslator(translator)
    translator.deleteLater()


def lines(dialog: ReviewDialog) -> list[tuple[str, str]]:
    table = dialog.table
    result = []
    for row in range(table.rowCount()):
        badge, detail = table.item(row, BADGE), table.item(row, DETAIL)
        assert badge is not None and detail is not None
        result.append((badge.text(), detail.text()))
    return result


def check(dialog: ReviewDialog, row: int, *, on: bool) -> None:
    item = dialog.table.item(row, BADGE)
    assert item is not None
    item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)


def service_of(shell: Shell) -> grafts.Grafts:
    service = shell.services.grafts
    assert service is not None
    return service


@pytest.mark.spec("S-27", 1)
def test_the_header_counts_what_the_dialog_lists(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _stub = made
    service = service_of(shell)
    header = shell.window.header
    assert header.review.text() == "Review & apply"
    assert header.review.toolTip() == "Nothing is waiting. Every replacement is already live."
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    add(service, profile.id, ABOVE_UINT32, 2222222)
    assert header.review.text() == "Review & apply (2)"
    shown = answering(monkeypatch, lambda _d: QDialog.DialogCode.Rejected)
    header.review.click()
    [dialog] = shown
    assert dialog.windowTitle() == "Review changes before applying"
    assert lines(dialog) == [("New", "New: asset 1111111"), ("New", "New: asset 2222222")]
    assert dialog.summary.text() == ("2 changes. They reach the game the next time Roblox starts.")
    assert dialog.apply_button.text() == "Apply 2 changes"
    assert service.holder.current.swaps() == {}  # Back to editing changes nothing


@pytest.mark.spec("S-27", 3)
def test_an_unchecked_change_keeps_waiting(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _stub = made
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    add(service, profile.id, ABOVE_UINT32, 2222222)

    def second_only(dialog: ReviewDialog) -> int:
        check(dialog, 0, on=False)
        assert dialog.apply_button.text() == "Apply 1 change"
        return QDialog.DialogCode.Accepted

    answering(monkeypatch, second_only)
    shell.window.header.review.click()
    assert service.holder.current.swaps() == {ABOVE_UINT32: 2222222}
    assert shell.window.header.review.text() == "Review & apply (1)"
    assert toasts(shell)[-1] == (
        "1 change applied. It reaches the game the next time Roblox starts."
    )


@pytest.mark.spec("S-27", 6)
@pytest.mark.parametrize(
    ("running", "others", "enabled", "tooltip"),
    [
        (True, (), True, ""),
        (False, (), False, "Roblox isn't running. The changes reach the game the next time it"),
        (False, (9,), False, "A Roblox Player that Verdra didn't start is running"),
    ],
)
def test_the_restart_checkbox_follows_roblox(
    made: tuple[Shell, StubSprout],
    monkeypatch: pytest.MonkeyPatch,
    *,
    running: bool,
    others: tuple[int, ...],
    enabled: bool,
    tooltip: str,
) -> None:
    shell, stub = made
    stub.running, stub.others = running, others
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    asked: list[str] = []
    monkeypatch.setattr(
        DestructiveConfirmation, "exec", lambda d: asked.append(d.windowTitle()) or 0
    )
    shown = answering(monkeypatch, lambda _d: QDialog.DialogCode.Accepted)
    shell.window.header.review.click()
    [dialog] = shown
    box = dialog.restart_box
    assert (box.isEnabled(), box.isChecked()) == (enabled, enabled)
    assert box.toolTip().startswith(tooltip)
    assert asked == []  # the review was the question: M-LAUNCH-03 isn't asked again
    if running:
        assert stub.calls == ["close", "clear", "launch"]  # only Verdra's own Player
        assert toasts(shell)[-1] == "1 change applied. Roblox is restarting."
    else:
        assert "close" not in stub.calls  # a Player Verdra didn't start is never closed


@pytest.mark.spec("S-27", 4)
def test_undo_after_a_restart_waits_for_the_cooldown_then_restarts_again(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, stub = made
    stub.running = True
    # Closing the window at the end asks M-SHELL-02 while Roblox runs: Quit.
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _d: QDialog.DialogCode.Accepted)
    now = [100.0]
    shell.monotonic = lambda: now[0]
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    answering(monkeypatch, lambda _d: QDialog.DialogCode.Accepted)
    shell.window.header.review.click()
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}
    [toast] = [t for t in shell.window.findChildren(Toast) if t.text.startswith("1 change")]
    assert toast.action_button is not None and toast.action_button.text() == "Undo"
    # It lasts 10 s from the end of the cooldown, so it can still be pressed then.
    assert toast.timer.interval() == int((APPLY_COOLDOWN_SECONDS + 10) * 1000)
    shell._undo_apply(service.store.applies, restarted=True)  # noqa: SLF001 - during cooldown
    assert toasts(shell)[-1] == "Verdra is still restarting Roblox. Try again in a moment."
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111}
    now[0] += APPLY_COOLDOWN_SECONDS
    stub.calls.clear()
    toast.action_button.click()
    assert service.holder.current.swaps() == {}
    assert stub.calls == ["close", "clear", "launch"]
    assert toasts(shell)[-1] == ("Put back the replacements applied before. Roblox is restarting.")
    assert shell.window.header.review.text() == "Review & apply (1)"  # the row waits again


def test_undo_after_another_apply_says_it_cant(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _stub = made
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    answering(monkeypatch, lambda _d: QDialog.DialogCode.Accepted)
    shell.window.header.review.click()
    first = service.store.applies
    add(service, profile.id, ABOVE_UINT32, 2222222)
    shell.window.header.review.click()
    shell._undo_apply(first, restarted=False)  # noqa: SLF001 - the first toast's Undo
    assert toasts(shell)[-1] == "Can't undo now: the replacements changed since."
    assert service.holder.current.swaps() == {ABOVE_INT32: 1111111, ABOVE_UINT32: 2222222}


def test_apply_is_disabled_while_roblox_restarts(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _stub = made
    shell.apply_busy_until = shell.monotonic() + 60
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    shown = answering(monkeypatch, lambda _d: QDialog.DialogCode.Rejected)
    shell.window.header.review.click()
    [dialog] = shown
    assert not dialog.apply_button.isEnabled()
    assert dialog.apply_button.toolTip() == (
        "Verdra is still restarting Roblox. Try again in a moment."
    )


@pytest.mark.spec("S-27", 5)
def test_a_problem_line_is_skipped_and_fix_opens_its_row(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shell, _stub = made
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    broken = add(service, profile.id, ABOVE_UINT32, f"{tmp_path}/gone.png")

    def fix(dialog: ReviewDialog) -> int:
        assert dialog.summary.text() == (
            "1 change. It reaches the game the next time Roblox starts. 1 will be skipped."
        )
        dialog._fix(broken)  # noqa: SLF001 - the line's Fix button
        return QDialog.DialogCode.Rejected

    answering(monkeypatch, fix)
    shell.window.header.review.click()
    screen = shell.window.screens["replacements"]
    assert isinstance(screen, ReplacementsScreen)
    assert shell.window.stack.currentWidget() is screen
    assert screen.editor.isVisibleTo(screen) and screen.editor.editing == broken


@pytest.mark.spec("S-27", 8)
def test_the_dialog_with_the_keyboard(qtbot: QtBot) -> None:
    changes = [
        grafts.Change("a", "new", "New: asset 1111111"),
        grafts.Change("b", "new", "New: asset 2222222"),
    ]
    dialog = ReviewDialog(changes, Roblox.NONE)
    qtbot.addWidget(dialog)
    dialog.table.setCurrentCell(0, BADGE)
    qtbot.keyClick(dialog.table, Qt.Key.Key_Space)  # unchecks the first line
    assert dialog.chosen() == ["b"]
    keys = {shortcut.key().toString(): shortcut for shortcut in dialog.findChildren(QShortcut)}
    assert set(keys) == {"Ctrl+Return", "Ctrl+Enter"}  # Ctrl+Enter applies (rule 8)
    with qtbot.waitSignal(dialog.accepted):
        keys["Ctrl+Return"].activated.emit()  # an offscreen window is never active


def test_apply_only_these_starts_with_just_those_checked(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _stub = made
    service = service_of(shell)
    profile = service.edit("create", "A")
    add(service, profile.id, ABOVE_INT32, 1111111)
    second = add(service, profile.id, ABOVE_UINT32, 2222222)
    shown = answering(monkeypatch, lambda _d: QDialog.DialogCode.Accepted)
    screen = shell.window.screens["replacements"]
    assert isinstance(screen, ReplacementsScreen)
    screen.apply_only.emit([second])
    [dialog] = shown
    assert dialog.chosen() == [second]
    assert service.holder.current.swaps() == {ABOVE_UINT32: 2222222}


def test_with_nothing_waiting_the_button_applies_again_without_a_review(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    """After Studio or another Player closed, M-CACHE-02 and -03 send the user back here."""
    shell, stub = made
    shown = answering(monkeypatch, lambda _d: QDialog.DialogCode.Accepted)
    shell.window.header.review.click()
    assert shown == []
    assert stub.calls == ["clear"]


def test_picture_lines_get_thumbnails_and_say_when_scaled(qtbot: QtBot) -> None:
    from verdra.strata import ochre  # noqa: PLC0415 - only this test makes a picture

    changes = [
        grafts.Change("a", "new", "New: file wide.png", replacement_id="a", family="Image"),
        grafts.Change("b", "new", "New: asset 2222222", replacement_id="b", family="Mesh"),
    ]
    dialog = ReviewDialog(changes, Roblox.NONE)
    qtbot.addWidget(dialog)
    icons = [dialog.table.item(row, PICTURE) for row in range(2)]
    assert all(item is not None and not item.icon().isNull() for item in icons)  # family icons
    png = ochre.to_png(ochre.Pixels(2048, 16, b"\x00\xff\x00\xff" * 2048 * 16))
    dialog.show_pictures({"a": grafts.ReviewPicture(png, (2048, 16), (1024, 64))})
    detail = dialog.table.item(0, DETAIL)
    assert detail is not None
    assert detail.text() == "New: file wide.png Scaled to 1024 × 64."
    thumb = dialog.table.item(0, PICTURE)
    assert thumb is not None
    sizes = thumb.icon().availableSizes()
    assert sizes and max(sizes[0].width(), sizes[0].height()) == 64
