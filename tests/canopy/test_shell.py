# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-01: app shell (window, theme, splash, toasts, shortcuts, closing)."""

import logging
import re
import subprocess
import sys
import textwrap
import time

import pytest
from PySide6.QtCore import QPropertyAnimation, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QWidget
from pytestqt.qtbot import QtBot

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
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.colour("bg", "dark")
    services.settings.set("appearance.theme", "light")
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.colour("bg", "light")
    # Match system follows the OS scheme when it changes. The offscreen test platform has no
    # scheme of its own, so the test plays the OS: it reports a scheme and announces the change.
    services.settings.set("appearance.theme", "system")
    scheme = [Qt.ColorScheme.Dark]
    monkeypatch.setattr(shell.theme, "os_scheme", lambda: scheme[0])
    app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert shell.theme.mode == "dark"
    assert app.palette().color(QPalette.ColorRole.Window) == tokens.colour("bg", "dark")
    scheme[0] = Qt.ColorScheme.Light
    app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert shell.theme.mode == "light"


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
    assert shell.splash is not None
    assert shell.splash.shown_at is not None
    shown_at = shell.splash.shown_at
    closed: list[float] = []
    shell.splash.finish(lambda: closed.append(time.monotonic() - shown_at))
    qtbot.waitUntil(lambda: bool(closed), timeout=3000)
    assert closed[0] >= 0.9
    assert not shell.splash.isVisible()


def test_splash_timeline_follows_section_4_5(qtbot: QtBot, shell: Shell) -> None:
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

    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(True))
    services.settings.set("general.close_to_tray", False)
    shell.window.show()
    shell.window.close()
    assert quits == [True]


def css_colours(sheet: str) -> set[str]:
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
            assert built.color(QPalette.ColorGroup.Active, role) == tokens.colour(name, mode), (
                mode,
                role,
            )
        disabled = built.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        assert disabled == tokens.colour("ink-disabled", mode)
        allowed = {theme.css_colour(tokens.colour(name, mode)) for name in tokens.colour_names()}
        tint = tokens.colour("primary-tint", mode)
        tint.setAlphaF(0.6)
        allowed.add(theme.css_colour(tint))
        sheet = theme.stylesheet(tokens, mode)
        assert "{" not in re.sub(r"\{[^{}]*\}", "", sheet)  # every placeholder was filled
        assert css_colours(sheet) <= {c for c in allowed}
    assert not css_colours(theme.STYLESHEET)


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
    with qtbot.waitSignal(job.cancelled, timeout=1000):
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
