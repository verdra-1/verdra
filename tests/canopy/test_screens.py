# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Specs S-01 and S-02: Settings and Activity screens, onboarding, About, shared dialogs."""

import logging
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)
from pytestqt.qtbot import QtBot

from verdra.canopy.crown import about
from verdra.canopy.crown.about import AboutDialog, notice_html
from verdra.canopy.crown.seedling import Onboarding, system_changes
from verdra.canopy.crown.tray import Tray
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation, Explanation, RiskWarning
from verdra.canopy.leaves.notice import Notice, Tone
from verdra.canopy.leaves.switch import Switch
from verdra.canopy.screens.rings import ActivityScreen
from verdra.canopy.screens.settings import SettingsScreen, groups
from verdra.trunk.almanac import schema
from verdra.trunk.almanac.store import SettingsStore
from verdra.trunk.sapwood.startup import Services

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.spec("S-02", 9)
def test_settings_screen_shows_every_key_and_resets_by_group(
    services: Services, qtbot: QtBot
) -> None:
    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    shown = set(screen.controls)
    expected = {
        key
        for key in schema.defaults()
        if key.split(".")[0] in schema.SCREEN_GROUPS
        and key not in {"general.language", "general.onboarding_done", "privacy.risk_acceptances"}
        and key != "advanced.detailed_logging_since"
    }
    # R2: language stays hidden until a second language ships; onboarding_done is set by "Run
    # setup again"; risk acceptances are listed with "Withdraw" buttons.
    assert shown == expected
    assert set(screen.reset_buttons) == set(schema.SCREEN_GROUPS)

    theme_box = screen.controls["appearance.theme"]
    assert isinstance(theme_box, QComboBox)
    theme_box.setCurrentIndex(theme_box.findData("dark"))
    assert services.settings.value("appearance.theme") == "dark"
    close = screen.controls["general.close_to_tray"]
    assert isinstance(close, Switch)
    close.click()
    assert services.settings.value("general.close_to_tray") is False
    port = screen.controls["routing.proxy_port"]
    assert isinstance(port, QSpinBox)
    port.setValue(50123)
    assert services.settings.value("routing.proxy_port") == 50123

    screen.reset_buttons["appearance"].click()
    assert services.settings.value("appearance.theme") == "system"
    assert theme_box.currentData() == "system"
    assert services.settings.value("general.close_to_tray") is False  # other groups untouched
    assert services.settings.value("routing.proxy_port") == 50123


def test_settings_controls_follow_the_store_and_conditions(
    services: Services, qtbot: QtBot
) -> None:
    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    screen.show()
    host = screen.row_widgets["routing.upstream.host"]
    user = screen.row_widgets["routing.upstream.username"]
    assert not host.isVisible()
    services.settings.set("routing.upstream.kind", "http")
    assert host.isVisible() and not user.isVisible()
    services.settings.set("routing.upstream.kind", "socks5")
    assert user.isVisible()
    field = screen.controls["routing.upstream.host"]
    assert isinstance(field, QLineEdit)
    field.setText("proxy.example")
    field.editingFinished.emit()
    assert services.settings.value("routing.upstream.host") == "proxy.example"
    services.settings.set("advanced.worker_threads", 8)
    spin = screen.controls["advanced.worker_threads"]
    assert isinstance(spin, QSpinBox) and spin.value() == 8
    for key, row in screen.rows.items():
        if row.unavailable:
            assert not screen.controls[key].isEnabled()
            assert screen.controls[key].toolTip()


def test_withdrawing_an_accepted_warning(services: Services, qtbot: QtBot) -> None:
    services.settings.set(
        "privacy.risk_acceptances",
        {"custom_flags": {"accepted_at": "2026-10-01T12:00:00Z", "app_version": "0.0.1"}},
    )
    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    withdraw = [b for b in screen.findChildren(QPushButton) if b.text() == "Withdraw"]
    assert len(withdraw) == 1
    withdraw[0].click()
    assert services.settings.value("privacy.risk_acceptances") == {}


def test_settings_from_a_newer_verdra_are_read_only(tmp_path: Path, qtbot: QtBot) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"format": "verdra.settings", "version": 99}', encoding="utf-8")
    store = SettingsStore(path)
    store.load()
    screen = SettingsScreen(store)
    qtbot.addWidget(screen)
    assert screen.findChildren(Notice)
    assert all(not control.isEnabled() for control in screen.controls.values())
    assert all(not button.isEnabled() for button in screen.reset_buttons.values())


def test_every_group_has_rows_with_labels() -> None:
    for _key, title, rows in groups():
        assert title
        assert all(row.label for row in rows)


@pytest.mark.spec("S-01", 13)
def test_onboarding_runs_on_first_start_and_again_on_request(
    shell: Shell, services: Services, qtbot: QtBot
) -> None:
    shell.show_window(minimised=False)
    qtbot.waitUntil(
        lambda: shell.onboarding is not None and shell.onboarding.isVisible(), timeout=2000
    )
    flow = shell.onboarding
    assert flow is not None
    flow.get_started.click()
    flow.continue_button.click()
    assert flow.pages.currentIndex() == 2
    assert flow.per_app.isChecked() and not flow.hosts_file.isEnabled()
    flow.handle_links.click()  # turn link handling off
    assert not any("link handler" in line for line in flow.changes.text().splitlines())
    flow.allow.click()
    assert services.settings.value("routing.handle_roblox_links") is False
    assert services.settings.value("routing.mode") == "per_app"
    assert all(not button.isEnabled() and button.toolTip() for button in flow.later_buttons)
    flow.finish.click()
    assert services.settings.value("general.onboarding_done") is True
    assert flow.result() == QDialog.DialogCode.Accepted

    settings_screen = shell.window.screens["settings"]
    assert isinstance(settings_screen, SettingsScreen)
    settings_screen.run_setup_button.click()
    assert services.settings.value("general.onboarding_done") is False
    qtbot.waitUntil(
        lambda: shell.onboarding is not None and shell.onboarding.isVisible(), timeout=2000
    )
    assert shell.onboarding is not flow


def test_onboarding_lists_the_changes_for_each_mode() -> None:
    per_app = system_changes("per_app", handle_links=True)
    hosts = system_changes("hosts_file", handle_links=False)
    assert any("certificate" in line for line in per_app)
    assert any("link handler" in line for line in per_app)
    assert any("administrator" in line for line in hosts)
    assert not any("link handler" in line for line in hosts)


def accessible(widget: QWidget) -> bool:
    if isinstance(widget, QAbstractButton):
        return bool(widget.accessibleName() or widget.text())
    return bool(widget.accessibleName())


@pytest.mark.spec("S-01", 9)
def test_every_control_has_an_accessible_name(
    shell: Shell, services: Services, qtbot: QtBot
) -> None:
    surfaces: list[QWidget] = [
        shell.window,
        AboutDialog(shell.window),
        Onboarding(services.settings, shell.window),
    ]
    for surface in surfaces:
        for widget in surface.findChildren(QWidget):
            interactive = isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QSpinBox))
            internal = isinstance(widget.parent(), (QComboBox, QSpinBox))  # Qt's own parts
            if interactive and not internal and widget.focusPolicy() != Qt.FocusPolicy.NoFocus:
                assert accessible(widget), f"{type(surface).__name__}: {type(widget).__name__}"
                if (
                    isinstance(widget, QAbstractButton)
                    and not widget.text()
                    and not isinstance(widget, Switch)
                ):
                    assert widget.toolTip(), type(widget).__name__
    tray = Tray()
    actions = [action for action in tray.menu.actions() if not action.isSeparator()]
    assert all(isinstance(action, QAction) and action.text() for action in actions)
    assert tray.menu.accessibleName()


def test_about_shows_notice_credit_and_texts(qtbot: QtBot, shell: Shell) -> None:
    dialog = AboutDialog(shell.window)
    qtbot.addWidget(dialog)
    assert '<a href="https://github.com/verdra-1/verdra">' in dialog.notice.text()
    assert "Fleasion" in dialog.credit.text()
    assert "not affiliated" in dialog.not_affiliated.text()
    assert dialog.viewers["licence"].isEnabled()
    assert dialog.viewers["privacy"].isEnabled()
    notices = dialog.viewers["notices"]
    assert notices.isEnabled() == (about.LEGAL / "THIRD_PARTY_NOTICES.md").exists()
    assert notices.isEnabled() or notices.toolTip()
    assert (
        notice_html("a <b>\nhttps://x.example/")
        == 'a &lt;b&gt;<br><a href="https://x.example/">https://x.example/</a>'
    )


def test_bundled_legal_texts_match_the_repository() -> None:
    for name in ("LICENSE", "NOTICE", "PRIVACY.md"):
        assert (about.LEGAL / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_risk_warning_needs_the_checkbox(qtbot: QtBot, shell: Shell) -> None:
    dialog = RiskWarning("Turn on custom FastFlags?", "Two sentences about the risk.", shell.window)
    qtbot.addWidget(dialog)
    assert not dialog.confirm.isEnabled()
    assert dialog.cancel.isDefault()
    assert dialog.confirm.text() == "Turn on"
    dialog.understood.click()
    assert dialog.confirm.isEnabled()
    dialog.confirm.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_explanation_and_destructive_confirmation(qtbot: QtBot, shell: Shell) -> None:
    plain = Explanation("Turn on the frame-rate cap?", "One sentence.", parent=shell.window)
    qtbot.addWidget(plain)
    assert plain.confirm.isEnabled() and plain.confirm.text() == "Continue"
    account = Explanation(
        "Add an account?", "One sentence.", account_sensitive=True, parent=shell.window
    )
    qtbot.addWidget(account)
    assert not account.confirm.isEnabled()
    assert account.understood is not None
    account.understood.click()
    assert account.confirm.isEnabled()
    delete = DestructiveConfirmation("Delete profile Arsenal skins?", "Delete", parent=shell.window)
    qtbot.addWidget(delete)
    assert delete.confirm.text() == "Delete"
    assert delete.cancel.isDefault()
    delete.cancel.click()
    assert delete.result() == QDialog.DialogCode.Rejected


def test_switch_and_notice(qtbot: QtBot, shell: Shell, caplog: pytest.LogCaptureFixture) -> None:
    switch = Switch()
    qtbot.addWidget(switch)
    switch.setAccessibleName("Example")
    assert not switch.isChecked()
    switch.click()
    assert switch.isChecked()
    switch.setChecked(False)
    assert switch.position == 0.0
    with caplog.at_level(logging.WARNING, logger="verdra"):
        notice = Notice("Your settings file was damaged.", Tone.WARNING)
    qtbot.addWidget(notice)
    assert "Your settings file was damaged." in caplog.text


def test_activity_screen_filters_copies_and_exports(
    shell: Shell, services: Services, qtbot: QtBot, tmp_path: Path
) -> None:
    screen = shell.window.screens["activity"]
    assert isinstance(screen, ActivityScreen)
    log = logging.getLogger("verdra.example")
    log.info("Applied 12 replacements.")
    log.warning("Roblox isn't routed through Verdra yet.")
    log.error("Export failed: the disk is full.")
    qtbot.waitUntil(lambda: len(screen.visible_records()) >= 3, timeout=2000)
    screen.search.setText("roblox")
    assert [r.message for r in screen.visible_records()] == [
        "Roblox isn't routed through Verdra yet."
    ]
    screen.search.clear()
    screen.level_buttons[logging.INFO].click()  # hide Info
    messages = [r.message for r in screen.visible_records()]
    assert "Applied 12 replacements." not in messages
    copied = screen.copy_records()
    assert "Export failed: the disk is full." in copied
    assert QGuiApplication.clipboard().text() == copied

    target = tmp_path / "bundle.zip"
    job = screen.write_bundle(target, include_profiles=False)
    with qtbot.waitSignal(job.finished, timeout=5000):
        pass
    qtbot.waitUntil(
        lambda: any("Support bundle saved" in t.text for t in shell.window.dew.toasts), timeout=2000
    )
    toast = next(t for t in shell.window.dew.toasts if "Support bundle saved" in t.text)
    assert toast.action_button is not None and toast.action_button.text() == "Show in folder"
    with zipfile.ZipFile(target) as bundle:
        assert "verdra.log" in bundle.namelist()
