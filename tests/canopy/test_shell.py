# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-01: app shell (window, theme, splash, toasts, shortcuts, closing)."""

import logging
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QLayout,
    QWidget,
    QWidgetItem,
)
from pytestqt.qtbot import QtBot

from tests.support import qt_lifetimes
from verdra.canopy.crown import splash as splash_module
from verdra.canopy.crown import theme
from verdra.canopy.crown.dew import DISMISS_MS, MAX_TOASTS, Kind
from verdra.canopy.crown.splash import Splash
from verdra.canopy.crown.window import TRAY_NOTICE_KEY, MainWindow, Shell
from verdra.trunk.sapwood.single import SingleInstance
from verdra.trunk.sapwood.startup import Services

THEMES: tuple[theme.Mode, ...] = ("light", "dark")


@pytest.mark.spec("S-01", 1, 7)
def test_second_launch_hands_over_its_link_and_exits_fast(qtbot: QtBot, home: object) -> None:
    name = f"verdra-test-single-{time.time_ns()}"
    first = SingleInstance(name)
    assert first.claim()
    link = "roblox-player:1+launchmode:play+gameinfo:abc+placelauncherurl:https%3A%2F%2Fx"
    script = textwrap.dedent(
        f"""
        import time
        from PySide6.QtCore import QCoreApplication
        from verdra.trunk.sapwood.single import SingleInstance
        app = QCoreApplication([])
        started = time.monotonic()
        claimed = SingleInstance({name!r}).claim({link!r})
        print(int(claimed), time.monotonic() - started, flush=True)
        """
    )
    with qtbot.waitSignal(first.activated, timeout=5000) as signal:
        process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
        )
    output, _ = process.communicate(timeout=10)
    claimed, elapsed = output.split()
    assert claimed == "0"
    assert float(elapsed) < 1.0
    assert signal.args == [link]
    first.release()


def test_a_stale_or_garbled_message_is_harmless(qtbot: QtBot) -> None:
    name = f"verdra-test-garbled-{time.time_ns()}"
    first = SingleInstance(name)
    assert first.claim()
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(name)
    assert socket.waitForConnected(500)
    with qtbot.waitSignal(first.activated, timeout=2000) as signal:
        socket.write(b'{"link": "https://evil.example"}\n')
        socket.flush()
    assert signal.args == [""]
    first.release()


@pytest.mark.spec("S-01", 2)
def test_theme_switches_live(
    shell: Shell, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    tokens = theme.Tokens.load()
    services.settings.set("appearance.theme", "dark")
    assert shell.theme.mode == "dark"
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.color("bg", "dark")
    services.settings.set("appearance.theme", "light")
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.color("bg", "light")
    # Match system follows the OS scheme when it changes. The offscreen test platform has no
    # scheme of its own, so the test plays the OS: it reports a scheme and announces the change.
    services.settings.set("appearance.theme", "system")
    scheme = [Qt.ColorScheme.Dark]
    monkeypatch.setattr(shell.theme, "os_scheme", lambda: scheme[0])
    app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert shell.theme.mode == "dark"
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.color("bg", "dark")
    scheme[0] = Qt.ColorScheme.Light
    app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert shell.theme.mode == "light"


def test_the_theme_skips_stale_wrappers_from_all_widgets(
    shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PySide can return a stale wrapper of another type from allWidgets() (CI run 37089139006:
    # "'QWidgetItem' object has no attribute 'property'"); applying the theme must not fail.
    app = shell.theme.app
    widgets = app.allWidgets()
    stale = QWidgetItem(QWidget())
    monkeypatch.setattr(app, "allWidgets", lambda: [stale, *widgets])
    shell.theme.apply()


def focus_chain(window: QWidget) -> list[QWidget]:
    chain: list[QWidget] = []
    widget = window.nextInFocusChain()
    while widget is not None and widget is not window and widget not in chain:
        focusable = widget.focusPolicy() & Qt.FocusPolicy.TabFocus
        if widget.isVisibleTo(window) and widget.isEnabled() and focusable:
            chain.append(widget)
        widget = widget.nextInFocusChain()
    return chain


@pytest.mark.spec("S-01", 3)
def test_tab_reaches_every_control_in_order(shell: Shell) -> None:
    window = shell.window
    window.show()
    for key in ("replacements", "library", "tweaks", "accounts", "activity", "settings"):
        window.show_screen(key)
        chain = focus_chain(window)
        interactive = [
            widget
            for widget in window.findChildren(QWidget)
            if isinstance(widget, (QAbstractButton, QComboBox)) or widget is window.header.pill
            if widget.isVisibleTo(window)
            and widget.isEnabled()
            and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
        ]
        assert set(interactive) <= set(chain), key
        sidebar = [w for w in chain if window.sidebar.isAncestorOf(w)]
        header = [w for w in chain if window.header.isAncestorOf(w)]
        content = [w for w in chain if window.stack.isAncestorOf(w)]
        positions = [chain.index(w) for w in sidebar + header + content]
        assert positions == sorted(positions), key


@pytest.mark.spec("S-01", 4)
def test_splash_stays_900_ms_and_closes_when_ready(qtbot: QtBot, shell: Shell) -> None:
    shell.show_splash()
    splash = shell.splash
    assert splash is not None
    assert splash.shown_at is not None
    shown_at = splash.shown_at
    closed: list[float] = []
    splash.finish(lambda: closed.append(time.monotonic() - shown_at))
    qtbot.waitUntil(lambda: bool(closed), timeout=3000)
    assert closed[0] >= 0.9
    # Once closed, the splash is deleted: nothing keeps it for the rest of the session.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(splash)


def test_splash_timeline_follows_section_4_5(
    qtbot: QtBot, shell: Shell, services: Services
) -> None:
    # CI machines often have animations turned off; this test is about the full timeline.
    services.settings.set("appearance.reduce_motion", "off")
    splash = Splash()
    qtbot.addWidget(splash)
    splash.elapsed_ms = 0
    assert splash.leaf_scale(0) == pytest.approx(0, abs=1e-6)
    splash.elapsed_ms = 80
    assert splash.leaf_scale(splash_module.RIGHT_LEAF_DELAY_MS) == pytest.approx(0, abs=1e-6)
    assert splash.leaf_scale(0) > 0
    splash.elapsed_ms = 640
    assert splash.leaf_scale(0) == pytest.approx(1)
    assert splash.node_scale() == 1
    splash.elapsed_ms = 640 + 120
    assert splash.node_scale() == pytest.approx(1.15)
    assert 0 < splash.wordmark_opacity() < 1
    splash.elapsed_ms = 880
    assert splash.node_scale() == 1
    assert splash.wordmark_opacity() == 1
    assert splash.total_ms == 880


@pytest.mark.spec("S-01", 5)
def test_shortcuts_switch_screens(shell: Shell, services: Services, qtbot: QtBot) -> None:
    window = shell.window
    expected = {
        "Ctrl+1": "replacements",
        "Ctrl+2": "library",
        "Ctrl+3": "tweaks",
        "Ctrl+4": "accounts",
    }
    for keys, screen in expected.items():
        shell.shortcuts.shortcuts[keys].activated.emit()
        assert window.current == screen
    shell.shortcuts.shortcuts["Ctrl+5"].activated.emit()
    assert window.current == "accounts"  # Traffic exists only in Advanced mode.
    services.settings.set("advanced.advanced_mode", True)
    shell.shortcuts.shortcuts["Ctrl+5"].activated.emit()
    assert window.current == "traffic"
    services.settings.set("advanced.advanced_mode", False)
    assert window.current == "replacements"
    shell.shortcuts.shortcuts["Ctrl+,"].activated.emit()
    assert window.current == "settings"


@pytest.mark.spec("S-01", 6)
def test_reduced_motion_means_fades_only(shell: Shell, services: Services, qtbot: QtBot) -> None:
    services.settings.set("appearance.reduce_motion", "on")
    assert shell.theme.reduce_motion
    splash = Splash()
    qtbot.addWidget(splash)
    assert splash.total_ms == theme.Tokens.load().reduced_fade()
    for elapsed in (0, 50, 150):
        splash.elapsed_ms = elapsed
        assert splash.leaf_scale(0) == 1
        assert splash.node_scale() == 1
    splash.elapsed_ms = 75
    assert splash.opacity() == pytest.approx(0.5)
    toast = shell.window.dew.show("Applied 12 replacements.")
    animations = toast.findChildren(QPropertyAnimation)
    assert [bytes(a.propertyName().data()) for a in animations] == [b"opacity"]
    assert all(a.duration() <= 150 for a in animations)
    services.settings.set("appearance.reduce_motion", "off")
    moving = shell.window.dew.show("Applied 3 replacements.")
    names = {bytes(a.propertyName().data()) for a in moving.findChildren(QPropertyAnimation)}
    assert names == {b"opacity", b"pos"}


@pytest.mark.spec("S-01", 8)
def test_closing_hides_to_the_tray_once_noticed(
    shell: Shell,
    services: Services,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    messages: list[str] = []

    class FakeIcon:
        def showMessage(self, title: str, text: str) -> None:  # noqa: N802
            messages.append(text)

    class FakeTray:
        icon = FakeIcon()

        def hide(self) -> None:
            pass

    shell.tray = FakeTray()  # type: ignore[assignment]
    shell.window.show()
    shell.window.close()
    assert not shell.window.isVisible()
    assert messages == ["Verdra is still running in the tray. Quit it from the tray menu."]
    assert services.state.get(TRAY_NOTICE_KEY) is True
    shell.window.show()
    shell.window.close()
    assert len(messages) == 1  # Only the first time.
    # Plan 16.2 (round 3, F12): M-SHELL-01 is also written to Activity, once.
    services.rings.stop()  # records reach the ring on the listener thread: drain it first
    activity = [record.message for record in services.rings.ring.snapshot()]
    assert activity.count("Verdra is still running in the tray. Quit it from the tray menu.") == 1

    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(True))
    services.settings.set("general.close_to_tray", False)
    shell.window.show()
    shell.window.close()
    assert quits == [True]


def layout_widgets(layout: QLayout) -> list[QWidget]:
    """Return a layout's widgets, in order, without making a Python wrapper of any layout item.

    PySide keeps every `itemAt()` result alive, registered under the item's address, for as long
    as the layout's wrapper lives. Qt frees the item when its widget leaves the layout, and PySide
    then hands the stale wrapper back for a new object made at the same address (#33, and the
    failure on main after #44). `QLayout.indexOf` searches in C++ and returns only a number.
    """
    parent = layout.parentWidget()
    if parent is None:
        return []
    children = parent.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    return sorted((w for w in children if layout.indexOf(w) >= 0), key=layout.indexOf)


def css_colors(sheet: str) -> set[str]:
    return set(re.findall(r"#[0-9a-fA-F]{6}\b|rgba\([^)]*\)", sheet))


@pytest.mark.spec("S-01", 10)
def test_palette_and_stylesheet_come_from_tokens(qapp: QApplication) -> None:
    tokens = theme.Tokens.load()
    roles = {
        QPalette.ColorRole.Window: "bg",
        QPalette.ColorRole.AlternateBase: "bg",
        QPalette.ColorRole.WindowText: "ink",
        QPalette.ColorRole.Text: "ink",
        QPalette.ColorRole.ButtonText: "ink",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.PlaceholderText: "ink-muted",
        QPalette.ColorRole.ToolTipBase: "tooltip-bg",
        QPalette.ColorRole.ToolTipText: "tooltip-ink",
        QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.HighlightedText: "on-primary",
        QPalette.ColorRole.Link: "primary",
        QPalette.ColorRole.LinkVisited: "primary",
        QPalette.ColorRole.Accent: "primary",
        QPalette.ColorRole.BrightText: "on-primary",
        QPalette.ColorRole.Light: "surface",
        QPalette.ColorRole.Midlight: "divider",
        QPalette.ColorRole.Mid: "border-strong",
        QPalette.ColorRole.Dark: "border-strong",
        QPalette.ColorRole.Shadow: "palette-shadow",
    }
    for mode in THEMES:
        built = theme.palette(tokens, mode)
        for role, name in roles.items():
            assert built.color(QPalette.ColorGroup.Active, role) == tokens.color(name, mode), (
                mode,
                role,
            )
        disabled = built.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        assert disabled == tokens.color("ink-disabled", mode)
        allowed = {theme.css_color(tokens.color(name, mode)) for name in tokens.color_names()}
        tint = tokens.color("primary-tint", mode)
        tint.setAlphaF(0.6)
        allowed.add(theme.css_color(tint))
        sheet = theme.stylesheet(tokens, mode)
        assert "{" not in re.sub(r"\{[^{}]*\}", "", sheet)  # every placeholder was filled
        assert css_colors(sheet) <= {c for c in allowed}
    assert not css_colors(theme.STYLESHEET)


def test_combo_and_spin_arrows_are_the_generated_chevrons(qtbot: QtBot) -> None:
    """The style sheet's flat subcontrols draw only an image, so every arrow must have one."""
    tokens = theme.Tokens.load()
    for mode in ("light", "dark"):
        sheet = theme.stylesheet(tokens, mode)
        urls = re.findall(r"url\(([^)]+)\)", sheet)
        files = [
            theme.ASSETS / "brand" / f"arrow-{d}-{mode}{s}.svg"
            for d in ("down", "up")
            for s in ("", "-disabled")
        ]
        assert sorted(urls) == sorted(file.as_posix() for file in files)
        assert all(file.is_file() for file in files)


@pytest.mark.spec("S-01", 11)
@pytest.mark.spec("S-03", 6)
def test_toasts_stack_dismiss_and_reach_activity(
    shell: Shell, services: Services, qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    dew = shell.window.dew
    shell.window.show()
    with caplog.at_level(logging.INFO, logger="verdra"):
        toasts = [dew.show(f"Applied {n} replacements.") for n in range(1, 5)]
    assert len(dew.toasts) == MAX_TOASTS
    assert toasts[0] not in dew.toasts  # the oldest left first
    assert {r.getMessage() for r in caplog.records} >= {
        f"Applied {n} replacements." for n in range(1, 5)
    }
    assert all(toast.timer.interval() == DISMISS_MS for toast in toasts[1:])
    held = dew.show("Support bundle saved to /tmp.", action=("Show in folder", lambda: None))
    failed = dew.show("Export failed: the disk is full.", Kind.ERROR)
    assert not held.timer.isActive()
    assert not failed.timer.isActive()
    qtbot.wait(400)  # let the entry slides settle
    bottom = dew.toasts[-1]
    margin = shell.window.height() - (bottom.y() + bottom.height())
    assert margin == 16
    assert shell.window.width() - (bottom.x() + bottom.width()) == 16
    plain = dew.show("Done.")
    plain.timer.setInterval(50)
    plain.timer.start()
    qtbot.waitUntil(lambda: plain not in dew.toasts, timeout=1000)
    services.rings.stop()
    activity = [record.message for record in services.rings.ring.snapshot()]
    assert "Export failed: the disk is full." in activity


@pytest.mark.spec("S-04", 5)
def test_slow_jobs_get_a_progress_toast_with_cancel(
    shell: Shell, services: Services, qtbot: QtBot
) -> None:
    def work(handle: object) -> None:
        for step in range(400):
            handle.check()  # type: ignore[attr-defined]
            handle.report(step // 4, "Copying files")  # type: ignore[attr-defined]
            time.sleep(0.01)

    job = services.tendrils.submit("Exporting 12 assets", work)
    qtbot.waitUntil(lambda: any(t.bar is not None for t in shell.window.dew.toasts), timeout=3000)
    toast = next(t for t in shell.window.dew.toasts if t.bar is not None)
    assert toast.action_button is not None
    assert toast.action_button.text() == "Cancel"
    qtbot.waitUntil(lambda: "Copying files" in toast.label.text(), timeout=1000)
    with qtbot.waitSignal(job.canceled, timeout=1000):
        toast.action_button.click()
    qtbot.waitUntil(lambda: toast not in shell.window.dew.toasts, timeout=1000)


@pytest.mark.spec("S-01", 12)
def test_window_state_is_restored(
    services: Services, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = MainWindow(services)
    qtbot.addWidget(first)
    first.sidebar.set_collapsed(True)
    first.show_screen("tweaks")
    first.save_state()
    saved = bytes(first.saveGeometry().data())
    services.state.save()
    services.state.load()
    # The offscreen test screen is smaller than the window's minimum, so Qt would clamp any
    # restored size; check that the saved geometry is what gets restored.
    restored: list[bytes] = []
    monkeypatch.setattr(
        MainWindow,
        "restoreGeometry",
        lambda _self, data: restored.append(bytes(data.data())) or True,
    )
    second = MainWindow(services)
    qtbot.addWidget(second)
    second.restore_state()
    assert restored == [saved]
    assert second.sidebar.collapsed
    assert second.current == "tweaks"
    assert second.minimumSize().width() == 1000


def test_disabled_controls_say_why(shell: Shell) -> None:
    for widget in shell.window.findChildren(QWidget):
        if isinstance(widget, (QAbstractButton, QComboBox)) and not widget.isEnabled():
            assert widget.toolTip(), widget.accessibleName() or widget.objectName()


def test_main_window_controls_have_accessible_names(shell: Shell) -> None:
    for widget in shell.window.findChildren(QWidget):
        if isinstance(widget, (QAbstractButton, QComboBox)) and widget.isVisibleTo(shell.window):
            name = widget.accessibleName() or (
                widget.text() if isinstance(widget, QAbstractButton) else ""
            )
            assert name, type(widget).__name__
            if isinstance(widget, QAbstractButton) and not widget.text():
                assert widget.toolTip()


@pytest.mark.spec("S-04", 6)
def test_every_failed_or_canceled_job_shows_its_message(
    shell: Shell, services: Services, qtbot: QtBot
) -> None:
    # Review finding H4: the toast must appear for any job, not just the support bundle.
    def broken(_handle: object) -> None:
        raise OSError("The disk is full")

    services.tendrils.submit("Exporting 12 assets", broken)
    expected = "Exporting 12 assets failed: The disk is full. Details are in Activity."
    qtbot.waitUntil(
        lambda: any(t.label.text() == expected for t in shell.window.dew.toasts), timeout=2000
    )

    def waits(handle: object) -> None:
        while True:
            handle.check()  # type: ignore[attr-defined]
            time.sleep(0.01)

    job = services.tendrils.submit("Copying files", waits)
    job.cancel()
    qtbot.waitUntil(
        lambda: any(t.label.text() == "Copying files canceled." for t in shell.window.dew.toasts),
        timeout=2000,
    )


@pytest.mark.spec("S-03", 6)
def test_dialogs_and_notices_reach_activity(
    shell: Shell, services: Services, qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    # Reference R5: every Toast, Dialog and Notice is also written to Activity (finding H7).
    from verdra.canopy.leaves.dialogs import DestructiveConfirmation
    from verdra.canopy.leaves.notice import Notice, Tone

    with caplog.at_level(logging.INFO, logger="verdra"):
        dialog = DestructiveConfirmation("Remove 3 replacements?", "Remove", "They're gone.")
        qtbot.addWidget(dialog)
        dialog.show()
        notice = Notice("Your settings file was damaged.", Tone.WARNING)
        qtbot.addWidget(notice)
    messages = {record.getMessage() for record in caplog.records}
    assert "Remove 3 replacements? They're gone." in messages
    assert "Your settings file was damaged." in messages


def _services_after(
    home: Path, qapp: QApplication, document: bytes, backup: bytes | None
) -> Services:
    from verdra.soil import atomic, terrain
    from verdra.trunk import rings, tendrils
    from verdra.trunk.almanac.store import SettingsStore, StateStore
    from verdra.trunk.sapwood import cli

    path = terrain.config_dir() / terrain.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document)
    if backup is not None:
        atomic.backup_path(path).write_bytes(backup)
    settings = SettingsStore()
    settings.load()
    state = StateStore()
    state.load()
    logs = rings.Rings()
    logs.start()
    return Services(
        app=qapp,
        arguments=cli.Arguments(),
        settings=settings,
        state=state,
        rings=logs,
        tendrils=tendrils.Tendrils(workers=2),
        single=SingleInstance(f"verdra-test-kinds-{home.name}"),
    )


GOOD = b'{"format": "verdra.settings", "version": 1}'


@pytest.mark.parametrize(
    ("document", "backup", "message_id"),
    [
        (b"\x00damaged", GOOD, "M-SET-01"),
        (b"\x00damaged", b"\x00also damaged", "M-SET-02"),
    ],
)
def test_settings_notices_are_inline_notices(  # noqa: PLR0917 - pytest passes fixtures positionally
    home: Path,
    qapp: QApplication,
    qtbot: QtBot,
    document: bytes,
    backup: bytes,
    message_id: str,
) -> None:
    """Reference R5: M-SET-01 and M-SET-02 are kind "Notice" (inline, until resolved), not
    toasts, and are written to Activity once (finding M9)."""
    from verdra.canopy.leaves.notice import Notice

    services = _services_after(home, qapp, document, backup)
    (expected,) = services.settings.notices
    assert expected.message_id == message_id
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    try:
        notices = layout_widgets(shell.window.notices)
        assert [type(n) for n in notices] == [Notice]
        (notice,) = notices
        assert isinstance(notice, Notice)
        assert notice.label.text() == expected.text
        assert shell.window.dew.toasts == []
        services.rings.stop()  # records reach the ring on the listener thread: drain it first
        activity = [record.message for record in services.rings.ring.snapshot()]
        assert activity.count(expected.text) == 1
        assert notice.dismiss is not None
        notice.dismiss.click()
        qtbot.waitUntil(lambda: shell.window.notices.count() == 0)
    finally:
        shell.window.allow_close = True
        services.tendrils.shutdown(grace=0.5)
        services.rings.stop()


def test_a_newer_settings_file_is_a_lasting_notice_on_the_settings_screen(
    home: Path, qapp: QApplication, qtbot: QtBot
) -> None:
    """M-SET-03 lasts while the file is read-only: inline on Settings and on each control."""
    from verdra.canopy.leaves.notice import Notice

    newer = b'{"format": "verdra.settings", "version": 99}'
    services = _services_after(home, qapp, newer, None)
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    try:
        r5 = "This file was made by a newer Verdra. Update Verdra to edit it."
        assert shell.window.notices.count() == 0
        assert shell.window.dew.toasts == []
        from verdra.canopy.screens.settings import SettingsScreen

        screen = shell.window.screens["settings"]
        assert isinstance(screen, SettingsScreen)
        inline = [n for n in screen.findChildren(Notice) if n.label.text() == r5]
        assert len(inline) == 1
        assert inline[0].dismiss is None
        disabled = [c for c in screen.controls.values() if not c.isEnabled()]
        assert disabled
        assert {c.toolTip() for c in disabled} == {r5}
    finally:
        shell.window.allow_close = True
        services.tendrils.shutdown(grace=0.5)
        services.rings.stop()


def test_the_shortcut_overlay_lists_only_working_shortcuts(
    qtbot: QtBot, shell: Shell, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding M13: Ctrl+F, Ctrl+N, undo, redo and Apply now aren't built yet in M0."""
    from verdra.canopy.crown.shortcuts import ShortcutHelp

    opened: list[ShortcutHelp] = []

    def record(dialog: ShortcutHelp) -> int:
        opened.append(dialog)
        return 0

    monkeypatch.setattr(ShortcutHelp, "exec", record)
    shell.show_shortcuts()  # what F1 does
    (help_,) = opened
    qtbot.addWidget(help_)
    # Ctrl+5 opens Traffic, which only Advanced mode shows (finding F15).
    working = shell.shortcuts.working - {"Ctrl+5"}
    assert set(help_.listed) == working
    for keys in help_.listed:
        if keys == "Esc":
            continue
        shortcut = shell.shortcuts.shortcuts[keys]
        assert shortcut.receivers("2activated()") > 0, keys
    for keys in ("Ctrl+F", "Ctrl+N", "Ctrl+Z", "Shift+Ctrl+Z", "Ctrl+Return"):
        assert keys not in help_.listed
        # Still registered, so nothing else takes the key.
        assert keys in shell.shortcuts.shortcuts

    services.settings.set("advanced.advanced_mode", True)
    shell.show_shortcuts()
    qtbot.addWidget(opened[-1])
    assert set(opened[-1].listed) == shell.shortcuts.working


@pytest.mark.spec("S-11", 9)
def test_diagnostic_interception_shows_a_lasting_notice(services: Services, qtbot: QtBot) -> None:
    """M-DIAG-01 shows for as long as the flag is on, so it has no Dismiss button."""
    from verdra.canopy.leaves.notice import Notice, Tone
    from verdra.trunk.sapwood import cli

    services.arguments = cli.Arguments(diagnose_interception=True)
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    try:
        (notice,) = layout_widgets(shell.window.notices)
        assert isinstance(notice, Notice)
        assert notice.label.text().startswith("Diagnostic interception is on.")
        assert notice.tone is Tone.WARNING
        assert notice.dismiss is None
    finally:
        shell.window.allow_close = True
        shell.window.close()


def test_no_diagnostic_notice_without_the_flag(shell: Shell) -> None:
    assert layout_widgets(shell.window.notices) == []


def test_reading_a_layout_leaves_no_stale_item_wrapper(shell: Shell) -> None:
    """The cause of the failure on main after #44: a dismissed notice's layout item, freed by Qt,
    stayed registered in PySide through an itemAt() wrapper and was handed back for the next
    object made at its address (a table header). layout_widgets() must make no such wrapper."""
    from verdra.canopy.leaves.notice import Notice

    notice = Notice("text", parent=shell.window, dismissible=True)
    shell.window.notices.addWidget(notice)
    assert layout_widgets(shell.window.notices) == [notice]
    assert notice.dismiss is not None
    notice.dismiss.click()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert layout_widgets(shell.window.notices) == []
    assert qt_lifetimes.stale_item_wrappers() == []


def test_the_tray_goes_with_its_window_and_takes_its_menu(shell: Shell) -> None:
    """The tray's menu has no widget parent; it is deleted with the tray, and the app-wide
    color-scheme signal no longer reaches a deleted tray (it used to: a lambda kept it)."""
    from PySide6.QtGui import QGuiApplication

    from verdra.canopy.crown.tray import Tray

    tray = Tray(shell.window)
    menu = tray.menu
    tray.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(tray)
    assert not shiboken6.isValid(menu)
    # The tray read its menu when the scheme changed; with the tray gone nothing may answer.
    QGuiApplication.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)


def test_the_toast_filter_does_nothing_once_its_attributes_are_gone(shell: Shell) -> None:
    """CI run 37110221102: Qt called Dew.eventFilter on a Dew whose Python attributes were
    already gone (window teardown). The filter must not raise then."""
    dew = shell.window.dew
    host = dew.host
    attributes = dict(vars(dew))
    vars(dew).clear()
    try:
        event = QResizeEvent(QSize(800, 600), QSize(640, 480))
        assert dew.eventFilter(host, event) is False
    finally:
        vars(dew).update(attributes)


def test_the_window_is_revealed_after_the_splash_with_no_reference_kept(
    qtbot: QtBot, shell: Shell
) -> None:
    """Startup's own sequence: nothing but the shell holds the splash. The main window must
    appear after the splash closes, and the splash is then deleted and forgotten."""
    shell.show_splash()
    shell.show_window(minimized=False)
    qtbot.waitUntil(shell.window.isVisible, timeout=3000)
    qtbot.waitUntil(lambda: shell.splash is None, timeout=3000)


@pytest.mark.qt_no_exception_capture  # the app's own hook must see the error, as in real use
def test_an_error_in_a_slot_is_logged_and_announced_never_only_printed(
    services: Services, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first-texture-swap failure: an exception in Save's slot reached only the console."""
    import threading  # noqa: PLC0415

    from verdra.canopy.screens.grafts.screen import ReplacementsScreen  # noqa: PLC0415
    from verdra.soil import terrain  # noqa: PLC0415
    from verdra.trunk import rings  # noqa: PLC0415
    from verdra.trunk.branches import grafts  # noqa: PLC0415

    services.errors = rings.ErrorHook().install()
    services.grafts = grafts.Grafts(terrain.config_dir() / "profiles", services.settings)
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    try:
        screen = shell.window.screens["replacements"]
        assert isinstance(screen, ReplacementsScreen)
        home = str(Path.home())

        def broken(*_args: object) -> None:
            raise RuntimeError(f"profile folder {home} is broken for asset 15553230204")

        monkeypatch.setattr(grafts.ProfileStore, "add_replacement", broken)
        screen.empty.buttons[0].click()
        qtbot.keyClicks(screen.editor.original, "15553230204")
        qtbot.keyClicks(screen.editor.target, "2147483655")
        for _ in range(3):  # the maintainer clicked Save 12 times: one notice, not twelve
            qtbot.mouseClick(screen.editor.save, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: bool(shell.window.dew.toasts))  # queued to the interface's thread
        notice = "Something went wrong. Details are in Activity."
        texts = [t.text for t in shell.window.dew.toasts]
        assert texts.count(notice) == 1
        [toast] = [t for t in shell.window.dew.toasts if t.text == notice]
        assert toast.kind is Kind.ERROR and toast.action_button is not None
        toast.action_button.click()
        assert shell.window.stack.currentWidget() is shell.window.screens["activity"]

        # An error on another thread is announced on the interface's thread too.
        threads: list[threading.Thread] = []
        services.errors.happened.connect(lambda: threads.append(threading.current_thread()))
        worker = threading.Thread(target=lambda: 1 / 0)
        with qtbot.waitSignal(services.errors.happened):
            worker.start()
            worker.join()
        qtbot.waitUntil(lambda: any(t.text == notice for t in shell.window.dew.toasts))
        assert threads == [threading.main_thread()]  # the notice is made on the interface's thread
    finally:
        services.errors.uninstall()
        shell.window.allow_close = True
        shell.window.close()
    check_activity(services)


def check_activity(services: Services) -> None:
    """Every unhandled error reached Activity in full and anonymized, with the notice's line."""
    services.rings.stop()  # records reach the ring on the listener thread: drain it first
    errors = [r.message for r in services.rings.ring.snapshot() if r.level == logging.ERROR]
    unhandled = [m for m in errors if m.startswith("Verdra ran into an error it didn't expect.")]
    assert len(unhandled) == 4  # three clicks and the thread: every one logged in full
    assert "Traceback (most recent call last):" in unhandled[0]
    assert "RuntimeError: profile folder" in unhandled[0] and "in _save" in unhandled[0]
    assert "ZeroDivisionError" in unhandled[-1]
    assert not any(Path.home().name in m or "15553230204" in m for m in unhandled)
    assert notice_in(errors)


def notice_in(errors: list[str]) -> bool:
    return "Something went wrong. Details are in Activity." in errors
