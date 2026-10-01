# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Main window: sidebar, header, content stack, splitter and geometry memory.

Master plan 7.1 and spec S-01. `MainWindow` is the frame every screen plugs into; `Shell` puts
the window, theme, splash, toasts, tray and shortcuts together for `trunk/sapwood/startup`.
Window size, position, sidebar state and the last screen live in `state.json`, keyed by the
screen setup, so a laptop on and off its dock remembers both layouts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QCoreApplication, QSize, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.crown.dew import Dew, Kind
from verdra.canopy.crown.header import Header
from verdra.canopy.crown.shortcuts import ShortcutHelp, Shortcuts
from verdra.canopy.crown.sidebar import ENTRIES, Sidebar
from verdra.canopy.crown.splash import Splash
from verdra.canopy.crown.tray import Tray
from verdra.canopy.leaves.empty import soon
from verdra.canopy.screens.garden import TweaksScreen
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.canopy.screens.hive import AccountsScreen
from verdra.canopy.screens.rings import ActivityScreen
from verdra.canopy.screens.seedbank import LibraryScreen
from verdra.canopy.screens.settings import SettingsScreen
from verdra.canopy.screens.streams import TrafficScreen

if TYPE_CHECKING:
    from verdra.trunk.sapwood.startup import Services
    from verdra.trunk.tendrils import Job

log = logging.getLogger(__name__)

MINIMUM_SIZE = QSize(1000, 640)
DEFAULT_SIZE = QSize(1200, 760)
TRAY_NOTICE_KEY = "shell.tray_notice_shown"


def screen_setup_key() -> str:
    """Return a key for the current arrangement of screens (sizes and positions)."""
    parts = []
    for screen in QGuiApplication.screens():
        geometry = screen.geometry()
        parts.append(f"{geometry.x()},{geometry.y()},{geometry.width()}x{geometry.height()}")
    return "window." + ";".join(sorted(parts))


class MainWindow(QMainWindow):
    """The main window.

    Signals:
        close_requested(): The user closed the window; the shell decides whether to hide or quit.
        about_requested(): The About entry was chosen.
    """

    close_requested = Signal()
    about_requested = Signal()

    def __init__(self, services: Services | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Verdra")  # noqa: VT001 - the product name is never translated
        self.setMinimumSize(MINIMUM_SIZE)
        self.resize(DEFAULT_SIZE)
        self.allow_close = False

        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar(root)
        layout.addWidget(self.sidebar)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.header = Header(root)
        column.addWidget(self.header)
        self.stack = QStackedWidget(root)
        self.stack.setObjectName("content")
        padding = theme.Tokens.load().length("space-6")
        self.stack.setContentsMargins(padding, padding, padding, padding)
        column.addWidget(self.stack, 1)
        layout.addLayout(column, 1)
        self.setCentralWidget(root)

        self.screens: dict[str, QWidget] = {
            "replacements": ReplacementsScreen(self.stack),
            "library": LibraryScreen(self.stack),
            "tweaks": TweaksScreen(self.stack),
            "accounts": AccountsScreen(self.stack),
            "traffic": TrafficScreen(self.stack),
            "activity": ActivityScreen(self.stack),
            "settings": SettingsScreen(self.stack),
        }
        for screen in self.screens.values():
            self.stack.addWidget(screen)
        self.current = "replacements"
        self.sidebar.selected.connect(self._sidebar_selected)
        self.dew = Dew(self)

        advanced = bool(services.settings.value("advanced.advanced_mode")) if services else False
        self.set_advanced(advanced)
        if services is not None:
            services.settings.changed.connect(self._setting_changed)
        self.show_screen("replacements")

    # --- Screens --------------------------------------------------------------------------

    def show_screen(self, key: str) -> None:
        """Switch to a screen (Traffic only while Advanced mode is on)."""
        if key not in self.screens or (key == "traffic" and not self.advanced):
            return
        self.current = key
        self.stack.setCurrentWidget(self.screens[key])
        entry = next(entry for entry in ENTRIES if entry.key == key)
        self.header.set_title(entry.title())
        self.sidebar.select(key)

    def show_main_screen(self, number: int) -> None:
        """Switch to the n-th main screen (Ctrl/Cmd+1 to 5)."""
        mains = [entry.key for entry in ENTRIES if entry.main]
        if 1 <= number <= len(mains):
            self.show_screen(mains[number - 1])

    def set_advanced(self, advanced: bool) -> None:
        """Show or hide what only Advanced mode shows."""
        self.advanced = advanced
        self.sidebar.set_advanced(advanced)
        if not advanced and getattr(self, "current", "") == "traffic":
            self.show_screen("replacements")

    def _sidebar_selected(self, key: str) -> None:
        if key == "about":
            self.about_requested.emit()
        else:
            self.show_screen(key)

    def _setting_changed(self, key: str, value: object) -> None:
        if key == "advanced.advanced_mode":
            self.set_advanced(bool(value))

    # --- Geometry memory ------------------------------------------------------------------

    def restore_state(self) -> None:
        """Restore size, position, sidebar state and the last screen from state.json."""
        if self.services is None:
            return
        saved = self.services.state.get(screen_setup_key())
        if isinstance(saved, dict) and isinstance(saved.get("geometry"), str):
            self.restoreGeometry(QByteArray.fromBase64(saved["geometry"].encode("ascii")))
        self.sidebar.set_collapsed(bool(self.services.state.get("sidebar.collapsed", False)))
        last = self.services.state.get("screen.last")
        if isinstance(last, str):
            self.show_screen(last)

    def save_state(self) -> None:
        """Write size, position, sidebar state and the current screen to state.json."""
        if self.services is None:
            return
        geometry = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        self.services.state.set(screen_setup_key(), {"geometry": geometry})
        self.services.state.set("sidebar.collapsed", self.sidebar.collapsed)
        self.services.state.set("screen.last", self.current)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        """Let the shell decide whether closing hides to the tray or quits."""
        self.save_state()
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.close_requested.emit()


class Shell:
    """The whole interface: theme, splash, window, toasts, tray and shortcuts."""

    def __init__(self, services: Services) -> None:
        # Plan 8.4 step 4 applies the theme before the splash; the window, tray and shortcuts
        # are built by build() once the services have started (step 5).
        self.services = services
        self.theme = theme.Theme(
            services.app, services.settings, os_reduce_motion=services.os_reduce_motion
        )
        self.splash: Splash | None = None
        self.tray: Tray | None = None
        self.window: MainWindow
        self.shortcuts: Shortcuts

    # --- startup.Interface ----------------------------------------------------------------

    def build(self) -> None:
        """Build the main window, tray and shortcuts; startup calls this after step 5."""
        services = self.services
        app = services.app
        self.window = MainWindow(services)
        self.window.close_requested.connect(self.close_window)
        self.window.about_requested.connect(self.show_about)
        if Tray.available():
            self.tray = Tray()
            self.tray.open_requested.connect(lambda: self.activate(""))
            self.tray.quit_requested.connect(self.quit)
            self.tray.show()
        app.setQuitOnLastWindowClosed(self.tray is None)
        self.shortcuts = Shortcuts(
            self.window,
            {
                "Ctrl+1": lambda: self.window.show_main_screen(1),
                "Ctrl+2": lambda: self.window.show_main_screen(2),
                "Ctrl+3": lambda: self.window.show_main_screen(3),
                "Ctrl+4": lambda: self.window.show_main_screen(4),
                "Ctrl+5": lambda: self.window.show_main_screen(5),
                "Ctrl+,": lambda: self.window.show_screen("settings"),
                "F1": self.show_shortcuts,
            },
        )
        services.tendrils.slow.connect(self.window.dew.show_job)
        services.tendrils.submitted.connect(self._report_job_end)
        for notice in services.settings.notices:
            kind = self._notice_kind(notice.message_id)
            self.window.dew.show(notice.text, kind)
        self.window.restore_state()

    def _report_job_end(self, job: Job) -> None:
        """Show M-JOB-01 or M-JOB-02 when any job is canceled or fails (spec S-04)."""
        job.canceled.connect(lambda: self.window.dew.report_job(job))
        job.failed.connect(lambda _reason: self.window.dew.report_job(job))

    @staticmethod
    def _notice_kind(message_id: str) -> Kind:
        return Kind.WARNING if message_id in {"M-SET-01", "M-SET-03"} else Kind.ERROR

    def show_splash(self) -> None:
        """Show the splash screen."""
        self.splash = Splash()
        self.splash.start()

    def show_window(self, *, minimized: bool) -> None:
        """Show the main window, or stay in the tray, and close the splash once it's ready."""
        stay_in_tray = minimized and self.tray is not None

        def reveal() -> None:
            if not stay_in_tray:
                self.window.show()
                self.window.raise_()
                self.window.activateWindow()
            self.services.step("main window ready")

        if self.splash is None:
            reveal()
        else:
            self.splash.finish(reveal)

    def activate(self, link: str) -> None:
        """Bring the window forward; a `roblox-player:` link is handed on from M1 (S-12)."""
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        if link:
            log.info(
                "%s",
                QCoreApplication.translate(
                    "M-SHELL-03",
                    "Verdra received a Roblox link. Opening games from links isn't available "
                    "in this version yet.",
                ),
            )

    # --- Closing and quitting -------------------------------------------------------------

    def close_window(self) -> None:
        """Hide to the tray when "Keep running in the tray" is on; otherwise quit."""
        keep = bool(self.services.settings.value("general.close_to_tray"))
        if keep and self.tray is not None:
            self.window.hide()
            if not self.services.state.get(TRAY_NOTICE_KEY, False):
                self.services.state.set(TRAY_NOTICE_KEY, True)
                text = QCoreApplication.translate(
                    "M-SHELL-01", "Verdra is still running in the tray. Quit it from the tray menu."
                )
                log.info("%s", text)
                if self.tray is not None:
                    self.tray.icon.showMessage("Verdra", text)  # noqa: VT001 - the product name
            return
        self.quit()

    def quit(self) -> None:
        """Quit Verdra (shutdown runs from the application's aboutToQuit)."""
        self.window.save_state()
        self.window.allow_close = True
        self.window.close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()

    # --- Dialogs --------------------------------------------------------------------------

    def show_about(self) -> None:
        """Show M-SOON-01 until the About dialog is built with S-01's dialogs (next step)."""
        self.window.dew.show(soon(), Kind.INFO)

    def show_shortcuts(self) -> None:
        """Open the keyboard shortcut overlay."""
        ShortcutHelp(self.window, self.shortcuts.working).exec()
