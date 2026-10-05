# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Specs S-01 and S-02: Settings and Activity screens, onboarding, About, shared dialogs."""

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
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
from verdra.canopy.leaves.empty import soon
from verdra.canopy.leaves.notice import Notice, Tone
from verdra.canopy.leaves.switch import Switch
from verdra.canopy.screens.rings import ActivityScreen
from verdra.canopy.screens.settings import SettingsScreen, groups
from verdra.soil import terrain
from verdra.trunk.almanac import schema
from verdra.trunk.almanac.store import SettingsStore
from verdra.trunk.sapwood import startup
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
    shell.show_window(minimized=False)
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


def test_about_shows_notice_and_texts(qtbot: QtBot, shell: Shell) -> None:
    dialog = AboutDialog(shell.window)
    qtbot.addWidget(dialog)
    assert '<a href="https://github.com/verdra-1/verdra">' in dialog.notice.text()
    assert "not affiliated" in dialog.not_affiliated.text()
    # The credit line is in the README only, never in the app (plan 3.3, decision record 0008).
    assert not any("inspired by" in label.text() for label in dialog.findChildren(QLabel))
    assert dialog.viewers["license"].text() == "License"  # US spelling in the UI
    assert dialog.viewers["license"].isEnabled()
    assert dialog.viewers["privacy"].isEnabled()
    notices = dialog.viewers["notices"]
    assert notices.isEnabled() == (terrain.legal_dir() / "THIRD_PARTY_NOTICES.md").exists()
    assert notices.isEnabled() or notices.toolTip()
    assert (
        notice_html("a <b>\nhttps://x.example/")
        == 'a &lt;b&gt;<br><a href="https://x.example/">https://x.example/</a>'
    )


def test_legal_texts_exist_once_at_the_repository_root() -> None:
    # Decision record 0010: no copy in the source tree; About reads the root files.
    assert not (ROOT / "src" / "verdra" / "assets" / "legal").exists()
    assert terrain.legal_dir() == ROOT
    for name in ("LICENSE", "NOTICE", "PRIVACY.md"):
        assert startup.legal_text(name) == (ROOT / name).read_text(encoding="utf-8"), name


def test_about_privacy_text_equals_the_root_file(
    qtbot: QtBot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []

    class Recorder(about.TextViewer):
        def exec(self) -> int:
            view = self.findChild(QPlainTextEdit)
            assert view is not None
            shown.append(view.toPlainText())
            return 0

    monkeypatch.setattr(about, "TextViewer", Recorder)
    dialog = AboutDialog(shell.window)
    qtbot.addWidget(dialog)
    dialog.viewers["privacy"].click()
    assert shown == [(ROOT / "PRIVACY.md").read_text(encoding="utf-8")]


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


def test_unbuilt_parts_never_promise_a_version() -> None:
    # Screens and controls that aren't built yet say M-SOON-01 instead (Reference R5).
    catalog = (ROOT / "src" / "verdra" / "assets" / "i18n" / "verdra_en.ts").read_text("utf-8")
    assert not re.search(r"Verdra \d+\.\d", catalog)
    assert "M-SOON-01" in catalog


def test_the_tray_line_has_singular_and_plural_forms(qapp: QApplication) -> None:
    """Reference R5 M-STATUS-02, plural forms through the compiled catalogue (finding M2)."""
    from verdra.canopy.crown.tray import Status

    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    try:
        tray = Tray()
        lines = {}
        for count in (0, 1, 2, 12):
            tray.set_status(Status.ROUTING, count)
            lines[count] = tray.status_action.text()
        assert lines == {
            0: "Routing · 0 replacements active",
            1: "Routing · 1 replacement active",
            2: "Routing · 2 replacements active",
            12: "Routing · 12 replacements active",
        }
    finally:
        qapp.removeTranslator(translator)


def test_privacy_section_links_the_privacy_text_and_names_features(
    qtbot: QtBot, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2 Privacy & safety: a link to the privacy text; accepted warnings by name (M17)."""
    import typing

    from verdra.canopy.screens import settings as settings_module

    keys = set(typing.get_args(schema.RiskFeature))
    assert set(settings_module.feature_names()) == keys
    accepted = {
        key: {"accepted_at": "2026-10-02T12:00:00Z", "app_version": "0.0.1"} for key in keys
    }
    services.settings.set("privacy.risk_acceptances", accepted)
    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    labels = {label.text() for label in screen.findChildren(QLabel)}
    for key, name in settings_module.feature_names().items():
        assert name in labels, key
        assert key not in labels, key
    withdraw = {
        b.accessibleName() for b in screen.findChildren(QPushButton) if b.text() == "Withdraw"
    }
    assert withdraw == {f"Withdraw {name}" for name in settings_module.feature_names().values()}
    shown: list[str] = []

    class Recorder(about.TextViewer):
        def exec(self) -> int:
            shown.append(self.findChild(QPlainTextEdit).toPlainText())  # type: ignore[union-attr]
            return 0

    monkeypatch.setattr(settings_module, "TextViewer", Recorder)
    screen.privacy_link.click()
    assert shown == [(ROOT / "PRIVACY.md").read_text(encoding="utf-8")]


SENTENCE = re.compile(r"[.?!:]$")
MESSAGE_ID = re.compile(r"^M-[A-Z]+-\d+$")


def catalog() -> list[tuple[str, str]]:
    """Return (message ID or context, source) for every message.

    A plural message (`self.tr(text, message_id, n)`, the only form lupdate makes plural
    entries from) carries its ID as the disambiguation comment; its context is the class.
    """
    root = ET.parse(ROOT / "src" / "verdra" / "assets" / "i18n" / "verdra_en.ts").getroot()  # noqa: S314
    return [
        (
            comment
            if MESSAGE_ID.match(comment := message.findtext("comment", ""))
            else context.findtext("name", ""),
            message.findtext("source", ""),
        )
        for context in root.iter("context")
        for message in context.iter("message")
    ]


def test_every_sentence_has_a_message_id() -> None:
    """Finding M10: full sentences (messages, notices, dialog text, empty states, help text)
    carry a catalogue ID; short labels need none."""
    loose = [
        f"[{context}] {source}"
        for context, source in catalog()
        if SENTENCE.search(source.strip())
        and len(source.split()) >= 3
        and not MESSAGE_ID.match(context)
    ]
    assert loose == []


def test_every_message_id_is_listed_word_for_word_in_a_spec() -> None:
    """R5: IDs marked new are listed in their spec; every ID's text matches it word for word."""
    specs = " ".join(
        " ".join(path.read_text(encoding="utf-8").split())
        for path in sorted((ROOT / "docs" / "specs").glob("S-*.md"))
    )
    specs = re.sub(r"<(\w+)>", lambda m: f"<{m.group(1).lower()}>", specs)
    missing = []
    for context, source in catalog():
        if not MESSAGE_ID.match(context):
            continue
        text = re.sub(r"\{(\w+)\}", r"<\1>", " ".join(source.split())).replace("%n", "<n>")
        if context not in specs or text not in specs:
            missing.append(f"[{context}] {text}")
    assert missing == []


def test_the_tray_has_every_plan_size_and_shows_why_items_are_off(qapp: QApplication) -> None:
    """Plan 4.6 tray sizes for Windows and Linux; unbuilt items show M-SOON-01 (finding L6)."""
    from verdra.canopy.crown.tray import Status, tray_icon

    for variant in ("light", "dark"):
        sizes = {size.width() for size in tray_icon(Status.IDLE, variant).availableSizes()}
        assert {16, 20, 22, 24, 32} <= sizes
    tray = Tray()
    assert tray.menu.toolTipsVisible()
    for action in (tray.apply_action, tray.pause_action):
        assert not action.isEnabled()
        assert action.toolTip() == soon()
    assert tray.reset_action.isEnabled()  # Reset everything is built (S-16)


def test_system_changes_lists_the_ledger(services: Services, qtbot: QtBot) -> None:
    """Spec S-16: every ledger entry that isn't removed, with its plain name, place and state."""
    from verdra.bark import scar

    screen = SettingsScreen(services.settings)
    qtbot.addWidget(screen)
    screen.show()
    assert screen.changes_empty.isVisible()
    assert not screen.changes_table.isVisible()

    ledger = scar.Ledger()
    done = ledger.begin("ca_roblox_bundle", "/roblox/1/cacert.pem", {"mode": 0o644})
    ledger.mark(done.id, "done")
    gone = ledger.begin("ca_roblox_bundle", "/roblox/0/cacert.pem", {"mode": 0o644})
    ledger.mark(gone.id, "removed")
    failed = ledger.begin("uri_handler", "roblox-player", {})
    ledger.mark(failed.id, "failed", error="Access denied")
    screen.hide()
    screen.show()  # read again whenever the screen is shown
    table = screen.changes_table
    assert table.isVisible() and not screen.changes_empty.isVisible()
    rows = [
        [table.item(row, column).text() for column in (0, 1, 3)]  # type: ignore[union-attr]
        for row in range(table.rowCount())
    ]
    assert rows == [
        ["Roblox link handler", "roblox-player", "Failed: Access denied"],
        ["Verdra's certificate in Roblox", "/roblox/1/cacert.pem", "Done"],
    ]
    assert table.item(0, 2).text()  # type: ignore[union-attr] # the date, in the user's locale
    assert table.accessibleName() == "System changes Verdra made"
    assert table.editTriggers() == table.EditTrigger.NoEditTriggers


def test_system_changes_says_when_the_ledger_cant_be_read(
    services: Services, qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from verdra.trunk.branches import fallow

    broken = True

    def list_changes() -> list[fallow.Change]:
        if broken:
            raise fallow.LedgerUnreadableError(tmp_path / "changes.json")
        return []

    with caplog.at_level(logging.ERROR):
        screen = SettingsScreen(services.settings, list_changes=list_changes)
    qtbot.addWidget(screen)
    screen.show()
    assert screen.changes_error is not None and screen.changes_error.isVisible()
    expected = f"Verdra can't read its list of system changes in {tmp_path / 'changes.json'}."
    assert screen.changes_error.label.text() == expected
    assert [r.getMessage() for r in caplog.records] == [expected]  # written to Activity once
    assert not screen.changes_table.isVisible() and not screen.changes_empty.isVisible()
    broken = False
    screen.refresh_changes()
    assert screen.changes_error is None
    assert screen.changes_empty.isVisible()


def test_every_system_change_kind_has_a_plain_name(qapp: QApplication) -> None:
    from typing import get_args

    from verdra.bark import scar
    from verdra.trunk.branches.fallow import kind_names

    assert set(kind_names()) == set(get_args(scar.Kind))
    assert all(name and "_" not in name for name in kind_names().values())
