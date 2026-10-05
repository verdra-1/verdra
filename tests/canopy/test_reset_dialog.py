# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-16 test 8: the Reset everything dialog, its progress and Activity lines."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from tests.trunk.branches.test_reset import trust_files
from verdra.bark import husk, scar
from verdra.canopy.crown.window import Shell
from verdra.canopy.screens import settings as settings_module
from verdra.canopy.screens.settings import ResetDialog, SettingsScreen, confirm_reset
from verdra.roots import gardener
from verdra.trunk.sapwood import startup
from verdra.trunk.sapwood.startup import Services

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def catalog(qapp: QApplication) -> Iterator[None]:
    """The English catalogue, for the summary's singular and plural forms."""
    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    yield
    qapp.removeTranslator(translator)
    translator.deleteLater()


def answer(monkeypatch: pytest.MonkeyPatch, code: QDialog.DialogCode) -> list[str]:
    """Make M-RESET-03 answer `code` without a modal loop; return the questions asked."""
    asked: list[str] = []

    def exec_(dialog: QDialog) -> int:
        asked.append(dialog.windowTitle())
        dialog.deleteLater()
        return int(code.value)

    monkeypatch.setattr(settings_module.DestructiveConfirmation, "exec", exec_)
    return asked


@pytest.mark.spec("S-16", 8)
def test_the_question_names_what_goes_and_cancel_is_the_default(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    question = confirm_reset()
    qtbot.addWidget(question)
    with caplog.at_level(logging.INFO):
        question.show()
    assert question.windowTitle() == "Remove everything Verdra changed on this computer?"
    assert question.body.text() == "Your profiles and library stay."
    assert question.confirm.text() == "Reset everything"
    assert question.cancel.isDefault() and question.focusWidget() is question.cancel
    assert not question.confirm.isDefault()
    assert caplog.messages == [
        "Remove everything Verdra changed on this computer? Your profiles and library stay."
    ]
    qtbot.keyClick(question, Qt.Key.Key_Return)  # Enter takes the default: Cancel
    assert question.result() == QDialog.DialogCode.Rejected


@pytest.mark.spec("S-16", 8)
def test_reset_shows_each_change_and_the_summary_and_writes_them_to_activity(
    services: Services,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    screen = SettingsScreen(services.settings, pool=services.tendrils)
    qtbot.addWidget(screen)
    screen.show()
    assert screen.reset_everything.isEnabled()
    assert screen.changes_table.rowCount() == len(files)
    asked = answer(monkeypatch, QDialog.DialogCode.Accepted)
    with caplog.at_level(logging.INFO):
        dialog = screen.start_reset()
        assert isinstance(dialog, ResetDialog)
        assert not dialog.close_button.isEnabled()
        dialog.reject()  # Escape can't stop it halfway
        assert dialog.isVisible()
        qtbot.waitUntil(dialog.close_button.isEnabled, timeout=10_000)
    assert asked == ["Remove everything Verdra changed on this computer?"]
    lines = [dialog.items.item(n).text() for n in range(dialog.items.count())]
    assert lines == [f"Removed Verdra's certificate in Roblox ({p})." for p in reversed(files)]
    summary = f"Removed {len(files)} changes. Verdra left nothing behind."
    assert dialog.summary.text() == summary
    assert dialog.progress.value() == 100
    assert [line for line in caplog.messages if line in [*lines, summary]] == [*lines, summary]
    assert dialog.close_button.isDefault() and dialog.focusWidget() is dialog.close_button
    qtbot.keyClick(dialog, Qt.Key.Key_Return)  # Enter closes it once it's done
    qtbot.waitUntil(lambda: screen.reset_dialog is None)
    assert screen.changes_empty.isVisible()  # the list was read again
    assert all(p.read_bytes() for p in files[:-1])
    assert list(scar.Ledger().open_entries()) == []


def test_canceling_the_question_changes_nothing(
    services: Services, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    contents = [p.read_bytes() for p in files]
    screen = SettingsScreen(services.settings, pool=services.tendrils)
    qtbot.addWidget(screen)
    answer(monkeypatch, QDialog.DialogCode.Rejected)
    assert screen.start_reset() is None
    assert [p.read_bytes() for p in files] == contents
    assert len(list(scar.Ledger().open_entries())) == len(files)


def test_a_reset_that_cant_read_the_ledger_says_so(
    services: Services, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    scar.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    scar.ledger_path().write_text("{ damaged", encoding="utf-8")
    screen = SettingsScreen(services.settings, pool=services.tendrils)
    qtbot.addWidget(screen)
    answer(monkeypatch, QDialog.DialogCode.Accepted)
    dialog = screen.start_reset()
    assert dialog is not None
    qtbot.waitUntil(dialog.close_button.isEnabled, timeout=10_000)
    assert dialog.summary.text().startswith("Reset everything failed: ")
    assert str(scar.ledger_path().name) in dialog.summary.text()
    dialog.accept()
    qtbot.waitUntil(lambda: screen.reset_dialog is None)


def test_without_background_jobs_the_button_explains_itself(
    services: Services, qtbot: QtBot
) -> None:
    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    assert not screen.reset_everything.isEnabled()
    assert screen.reset_everything.toolTip()
    assert screen.start_reset() is None


def test_the_tray_item_opens_settings_and_starts_reset(
    shell: Shell, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    from verdra.canopy.crown.tray import Tray

    tray = Tray()
    asked: list[bool] = []
    tray.reset_requested.connect(lambda: asked.append(True))
    tray.reset_action.trigger()
    assert asked == [True]
    tray.deleteLater()
    # The shell connects that signal to reset_everything (when the system has a tray at all).
    started: list[bool] = []
    monkeypatch.setattr(SettingsScreen, "start_reset", lambda _self: started.append(True))
    shell.reset_everything()
    assert started == [True]
    assert shell.window.current == "settings"
    assert shell.window.isVisible()


def answer_with_erase(monkeypatch: pytest.MonkeyPatch, *, erase: bool) -> None:
    """Accept M-RESET-03, with the option ticked or not."""

    def exec_(dialog: QDialog) -> int:
        dialog.erase.setChecked(erase)  # type: ignore[attr-defined]
        dialog.deleteLater()
        return int(QDialog.DialogCode.Accepted.value)

    monkeypatch.setattr(settings_module.DestructiveConfirmation, "exec", exec_)


def test_the_option_to_delete_my_data_is_off_by_default(qtbot: QtBot) -> None:
    question = confirm_reset()
    qtbot.addWidget(question)
    erase = question.erase  # type: ignore[attr-defined]
    assert erase.text() == "Also delete my profiles, library and settings"
    assert not erase.isChecked()


@pytest.mark.parametrize("fails", [False, True], ids=["all removed", "one failed"])
def test_with_the_option_verdra_quits_to_delete_its_folders_only_if_all_was_removed(
    services: Services,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fails: bool,
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    if fails:
        files[0].unlink()
        files[0].mkdir()  # its undo fails, so the ledger must stay
    erased: list[bool] = []
    screen = SettingsScreen(
        services.settings, pool=services.tendrils, on_erase=lambda: erased.append(True)
    )
    qtbot.addWidget(screen)
    answer_with_erase(monkeypatch, erase=True)
    dialog = screen.start_reset()
    assert dialog is not None
    qtbot.waitUntil(dialog.close_button.isEnabled, timeout=10_000)
    if fails:
        assert dialog.summary.text().endswith(
            "Your profiles, library and settings were kept, because some changes couldn't be "
            "removed."
        )
    else:
        assert dialog.summary.text() == (
            f"Removed {len(files)} changes. Verdra left nothing behind. When you close this "
            "window, Verdra deletes your profiles, library and settings and quits."
        )
    dialog.accept()
    qtbot.waitUntil(lambda: screen.reset_dialog is None)
    assert erased == ([] if fails else [True])


def test_quitting_to_erase_tells_shutdown(shell: Shell, monkeypatch: pytest.MonkeyPatch) -> None:
    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(True))
    shell.window.erase_requested.emit()
    assert shell.services.erase_own_data
    assert quits == [True]


def test_with_a_moved_library_the_closing_message_says_where_it_stays(
    services: Services, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 16.2, "M1 decisions": a library the user moved is never deleted; they're told where."""
    chosen = tmp_path / "My library"
    chosen.mkdir()
    services.settings.set("library.location", str(chosen))
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), trust_files(tmp_path / "roblox"), NOW)
    screen = SettingsScreen(services.settings, pool=services.tendrils, on_erase=lambda: None)
    qtbot.addWidget(screen)
    answer_with_erase(monkeypatch, erase=True)
    dialog = screen.start_reset()
    assert dialog is not None
    qtbot.waitUntil(dialog.close_button.isEnabled, timeout=10_000)
    assert dialog.summary.text().endswith(
        f"Your library in {chosen} stays, because you chose that folder; delete it yourself if "
        "you no longer need it."
    )
    dialog.accept()
    qtbot.waitUntil(lambda: screen.reset_dialog is None)
