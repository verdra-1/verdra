# SPDX-FileCopyrightText: 2026 q0f7
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

from PySide6.QtCore import QByteArray, QCoreApplication, QObject, QSize, Signal
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
from verdra.canopy.crown.about import AboutDialog
from verdra.canopy.crown.dew import Dew, Kind, Toast
from verdra.canopy.crown.header import Header, StatusView, status_of
from verdra.canopy.crown.seedling import Onboarding
from verdra.canopy.crown.shortcuts import ShortcutHelp, Shortcuts
from verdra.canopy.crown.sidebar import ENTRIES, Sidebar
from verdra.canopy.crown.splash import Splash
from verdra.canopy.crown.tray import Tray
from verdra.canopy.leaves.dialogs import Choice, DestructiveConfirmation, Information
from verdra.canopy.leaves.notice import Notice, Tone
from verdra.canopy.screens.garden import TweaksScreen
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.canopy.screens.hive import AccountsScreen
from verdra.canopy.screens.rings import ActivityScreen
from verdra.canopy.screens.seedbank import LibraryScreen
from verdra.canopy.screens.settings import SettingsScreen
from verdra.canopy.screens.streams import TrafficScreen
from verdra.trunk.branches.sprout import (
    cache_moved_text,
    capture_text,
    control_text,
    other_player_text,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from verdra.trunk.almanac.store import Notice as SettingsNotice
    from verdra.trunk.branches.sprout import CacheMove, RunningRoblox
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
    setup_requested = Signal()
    erase_requested = Signal()
    #: "Launch Roblox" was pressed (Library empty state, spec S-12).
    launch_requested = Signal()

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
        content = QWidget(root)
        content.setObjectName("content")
        padded = QVBoxLayout(content)
        padding = theme.Tokens.load().length("space-6")  # plan 7.1: content padding 24 px
        padded.setContentsMargins(padding, padding, padding, padding)
        # Notices about the whole app (R5 kind "Notice": inline, until resolved) sit above the
        # screens.
        self.notices = QVBoxLayout()
        self.notices.setSpacing(theme.Tokens.load().length("space-3"))
        padded.addLayout(self.notices)
        self.stack = QStackedWidget(content)
        padded.addWidget(self.stack)
        column.addWidget(content, 1)
        layout.addLayout(column, 1)
        self.setCentralWidget(root)

        self.dew = Dew(self)
        self.screens: dict[str, QWidget] = {
            "replacements": ReplacementsScreen(
                self.stack, services.grafts if services is not None else None
            ),
            "library": LibraryScreen(
                self.stack,
                self.launch_requested.emit if services and services.sprout else None,
            ),
            "tweaks": TweaksScreen(self.stack),
            "accounts": AccountsScreen(self.stack),
            "traffic": TrafficScreen(self.stack),
            "activity": ActivityScreen(services, self.dew, self.stack),
        }
        if services is not None:
            self.screens["settings"] = SettingsScreen(
                services.settings,
                self.setup_requested.emit,
                self.stack,
                pool=services.tendrils,
                on_erase=self.erase_requested.emit,
                routing=services.sprout,
            )
        for screen in self.screens.values():
            self.stack.addWidget(screen)
        self.current = "replacements"
        self.sidebar.selected.connect(self._sidebar_selected)

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

    def main_screens(self) -> list[str]:
        """Return the main screens the sidebar shows now (Traffic only in Advanced mode)."""
        advanced = getattr(self, "advanced", False)
        return [e.key for e in ENTRIES if e.main and (advanced or not e.advanced_only)]

    def show_main_screen(self, number: int) -> None:
        """Switch to the n-th main screen the sidebar shows (Ctrl/Cmd+1 to 5)."""
        mains = self.main_screens()
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


class ApplyText(QObject):
    """Apply now's toasts, with their plural forms (spec S-24)."""

    def next_time(self, count: int) -> str:
        return self.tr(
            "Applied %n replacements. They'll appear next time Roblox starts.", "M-APPLY-02", count
        )

    def restarted(self, count: int) -> str:
        return self.tr("Applied %n replacements. Roblox is restarting.", "M-APPLY-01", count)

    def not_prepared(self, count: int) -> str:
        return self.tr(
            "%n replacements couldn't be prepared. See the warnings in Replacements.",
            "M-GRAFT-01",
            count,
        )

    def waiting(self, count: int) -> str:
        return self.tr(
            "Downloading %n replacements first. Apply now goes on when they're ready.",
            "M-APPLY-04",
            count,
        )

    def restarted_cached(self, count: int) -> str:
        return self.tr(
            "Applied %n replacements. Assets Roblox already saved may change only after it "
            "refreshes them.",
            "M-APPLY-03",
            count,
        )


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
        self.onboarding: Onboarding | None = None
        self.tray: Tray | None = None
        self.window: MainWindow
        self.shortcuts: Shortcuts
        #: M-LAUNCH-08's banner while a Player Verdra didn't start is running.
        self.others_banner: Notice | None = None
        #: M-APPLY-04's toast while Apply now waits for downloads.
        self.apply_waiting: Toast | None = None

    # --- startup.Interface ----------------------------------------------------------------

    def build(self) -> None:
        """Build the main window, tray and shortcuts; startup calls this after step 5."""
        services = self.services
        app = services.app
        self.window = MainWindow(services)
        self.window.close_requested.connect(self.close_window)
        self.window.about_requested.connect(self.show_about)
        self.window.setup_requested.connect(self.run_setup)
        self.window.erase_requested.connect(self.quit_and_erase)
        self.window.launch_requested.connect(self.launch_roblox)
        if services.sprout is not None:
            services.sprout.refused.connect(self.show_launch_notice)
            services.sprout.other_tool.connect(self.show_other_tool)
            services.sprout.others_changed.connect(self.show_others)
            services.sprout.held_back.connect(self.ask_about_others)
            services.sprout.handed_off.connect(self.show_handed_off)
            popover = self.window.header.popover
            popover.set_handled(
                {"start", "retry", "restart_roblox", "repair_certificate", "close_others"}
            )
            popover.fix_requested.connect(self.fix_routing)
            services.sprout.refresh_others()
        if services.grafts is not None:
            self.window.header.enable_apply()
            self.window.header.apply_now.clicked.connect(self.apply_now)
            grafts = services.grafts
            grafts.changed.connect(lambda: self.window.header.show_profiles(grafts.profiles))
            self.window.header.show_profiles(grafts.profiles)
        replacements = self.window.screens["replacements"]
        if isinstance(replacements, ReplacementsScreen):
            replacements.deleted.connect(
                lambda text: self.window.dew.show(
                    text,
                    Kind.INFO,
                    (QCoreApplication.translate("M-PROF-09", "Undo"), replacements.undo_delete),
                )
            )
        if Tray.available():
            self.tray = Tray(self.window)  # destroyed with the window, its menu with it
            self.tray.open_requested.connect(lambda: self.activate(""))
            self.tray.quit_requested.connect(self.quit)
            self.tray.reset_requested.connect(self.reset_everything)
            self.tray.show()
        app.setQuitOnLastWindowClosed(self.tray is None)
        actions: dict[str, Callable[[], None]] = {
            "Ctrl+1": lambda: self.window.show_main_screen(1),
            "Ctrl+2": lambda: self.window.show_main_screen(2),
            "Ctrl+3": lambda: self.window.show_main_screen(3),
            "Ctrl+4": lambda: self.window.show_main_screen(4),
            "Ctrl+5": lambda: self.window.show_main_screen(5),
            "Ctrl+,": lambda: self.window.show_screen("settings"),
            "F1": self.show_shortcuts,
        }
        if services.grafts is not None:
            actions |= {
                "Ctrl+N": self.add_replacement,
                "Ctrl+Z": lambda: self._replacements_button("undo"),
                "Shift+Ctrl+Z": lambda: self._replacements_button("redo"),
                "Ctrl+Return": self.apply_now,
            }
        self.shortcuts = Shortcuts(self.window, actions)
        if services.errors is not None:
            services.errors.happened.connect(self.show_error)
        services.tendrils.slow.connect(self.window.dew.show_job)
        services.tendrils.submitted.connect(self._report_job_end)
        if services.routing is not None:
            # One published value drives the pill, the popover and the tray (spec S-14 rule 1).
            services.routing.changed.connect(self.show_routing)
            self.show_routing(services.routing.current)
        for notice in services.settings.notices:
            self.show_settings_notice(notice)
        self._show_diagnostics()
        self.window.restore_state()

    def _show_diagnostics(self) -> None:
        """M-DIAG-01, -03 and -08, for as long as a source-only diagnostic is on."""
        arguments = self.services.arguments
        if arguments.diagnose_interception:
            self.show_diagnostic_notice()
        texts = []
        if arguments.format_capture:
            texts.append(capture_text(arguments.format_capture))
        if arguments.control_swap:
            texts.append(control_text(*arguments.control_swap))
        for text in texts:
            self.window.notices.addWidget(Notice(text, Tone.WARNING, self.window))

    def _report_job_end(self, job: Job) -> None:
        """Show M-JOB-01 or M-JOB-02 when any job is canceled or fails (spec S-04)."""
        job.canceled.connect(lambda: self.window.dew.report_job(job))
        job.failed.connect(lambda _reason: self.window.dew.report_job(job))

    def show_settings_notice(self, notice: SettingsNotice) -> None:
        """Show M-SET-01 or M-SET-02 inline above the screens (R5 kind "Notice").

        M-SET-03 lasts as long as the file stays read-only, so the Settings screen shows it, at
        the top and on every control it disables.
        """
        if notice.message_id == "M-SET-03":
            return
        tone = Tone.WARNING if notice.message_id == "M-SET-01" else Tone.DANGER
        self.window.notices.addWidget(Notice(notice.text, tone, self.window, dismissible=True))

    def show_diagnostic_notice(self) -> None:
        """Show M-DIAG-01 for as long as diagnostic interception is on (spec S-11).

        It lasts until Verdra restarts without the flag, so it has no Dismiss button.
        """
        text = QCoreApplication.translate(
            "M-DIAG-01",
            "Diagnostic interception is on. Verdra is reading Roblox's traffic to check it, and "
            "changes nothing. Restart Verdra without --diagnose-interception to turn it off.",
        )
        self.window.notices.addWidget(Notice(text, Tone.WARNING, self.window))

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
            if not self.services.settings.value("general.onboarding_done") and not stay_in_tray:
                self.run_setup()

        if self.splash is None:
            reveal()
        else:
            # The splash deletes itself once it has closed. The shell keeps its reference until
            # then: dropping the last Python reference to a window without a parent deletes it at
            # once, before its timer could close it and reveal the main window.
            self.splash.destroyed.connect(self._splash_gone)
            self.splash.finish(reveal)

    def _splash_gone(self) -> None:
        self.splash = None

    def reset_everything(self) -> None:
        """Open Settings and run Reset everything from there (tray menu item 5, spec S-16)."""
        self.activate("")
        self.window.show_screen("settings")
        screen = self.window.screens.get("settings")
        if isinstance(screen, SettingsScreen):
            screen.start_reset()

    def activate(self, link: str) -> None:
        """Bring the window forward; a `roblox-player:` link starts Roblox through Verdra (S-12)."""
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        if link and self.services.sprout is not None:
            self.services.sprout.launch(link)

    # --- Routing and launching (spec S-12) ------------------------------------------------

    def launch_roblox(self) -> None:
        """Start Roblox through Verdra; a refusal shows as a notice (`show_launch_notice`)."""
        if self.services.sprout is not None:
            self.services.sprout.launch()

    def fix_routing(self, key: str) -> None:
        """Run the routing popover's fix (spec S-14): start, try again, relaunch Roblox, or
        repair the certificate."""
        sprout = self.services.sprout
        if sprout is None:
            return
        if key == "restart_roblox":
            sprout.launch()
        elif key == "close_others":
            self.close_other_roblox()
        elif key == "retry":
            sprout.retry()
        elif key == "repair_certificate":
            sprout.repair_certificate()
        else:
            sprout.start_routing()

    # --- A Roblox Player Verdra didn't start (M-LAUNCH-08 to M-LAUNCH-17) ------------------

    def show_others(self, running: bool) -> None:  # noqa: FBT001 - a Qt signal's argument
        """Show or remove the banner saying Roblox runs without Verdra (on every screen)."""
        if running and self.others_banner is None:
            banner = Notice(other_player_text(), Tone.WARNING, self.window)
            banner.add_action(
                QCoreApplication.translate("M-LAUNCH-18", "How to close it"), self.explain_others
            )
            banner.add_action(
                QCoreApplication.translate("M-LAUNCH-10", "Close Roblox…"), self.close_other_roblox
            )
            self.window.notices.insertWidget(0, banner)
            self.others_banner = banner
        elif not running and self.others_banner is not None:
            self.others_banner.hide()
            self.others_banner.deleteLater()
            self.others_banner = None

    def show_handed_off(self, text: str) -> None:
        """M-LAUNCH-14: the game most likely opened in the Roblox running without Verdra."""
        self.window.dew.show(text, Kind.WARNING)

    def explain_others(self) -> None:
        """M-LAUNCH-18: how to close every Roblox, in plain steps."""
        Information(
            QCoreApplication.translate("M-LAUNCH-18", "How to close Roblox completely"),
            QCoreApplication.translate(
                "M-LAUNCH-18",
                "1. Leave your game and close every Roblox window.\n"
                "2. If Roblox still runs, open Task Manager (Ctrl+Shift+Esc), select each "
                '"Roblox" entry and click End task.\n'
                "3. Back in Verdra, click Apply now, then join your game.",
            ),
            self.window,
        ).exec()

    def close_other_roblox(self) -> None:
        """Close the Roblox running without Verdra, only once the user confirms (M-LAUNCH-10)."""
        sprout = self.services.sprout
        if sprout is None:
            return
        dialog = DestructiveConfirmation(
            QCoreApplication.translate(
                "M-LAUNCH-10",
                "Close the Roblox that is running without Verdra? Unsaved progress in its game "
                "may be lost.",
            ),
            QCoreApplication.translate("M-LAUNCH-10", "Close Roblox"),
            parent=self.window,
        )
        if dialog.exec() == DestructiveConfirmation.DialogCode.Accepted:
            sprout.close_others()

    def ask_about_others(self, link: str) -> None:
        """M-LAUNCH-17: a launch waits while Roblox runs without Verdra; the user decides."""
        sprout = self.services.sprout
        if sprout is None:
            return
        self.window.showNormal()
        self.window.raise_()
        dialog = Choice(
            QCoreApplication.translate("M-LAUNCH-17", "Roblox is already running without Verdra"),
            QCoreApplication.translate(
                "M-LAUNCH-17",
                "If Verdra starts this game now, it opens in that Roblox and your replacements "
                "don't show. Close it first, so the game opens through Verdra.",
            ),
            QCoreApplication.translate("M-LAUNCH-17", "Close Roblox and continue"),
            QCoreApplication.translate("M-LAUNCH-17", "Continue anyway"),
            self.window,
        )
        dialog.exec()
        if dialog.choice == "primary":
            sprout.close_others()
            if sprout.others:
                return  # M-LAUNCH-16 says why; the banner stays
            sprout.launch(link or None)
        elif dialog.choice == "secondary":
            sprout.launch(link or None, despite_others=True)

    def add_replacement(self) -> None:
        """Ctrl+N: show Replacements and open the editor drawer."""
        self.window.show_screen("replacements")
        screen = self.window.screens["replacements"]
        if isinstance(screen, ReplacementsScreen):
            screen.add_replacement()

    def _replacements_button(self, name: str) -> None:
        """Ctrl+Z and Shift+Ctrl+Z: undo or redo replacement edits, on the Replacements screen.

        A focused text field keeps its own undo (Qt gives it the key first).
        """
        screen = self.window.screens["replacements"]
        if isinstance(screen, ReplacementsScreen) and self.window.stack.currentWidget() is screen:
            getattr(screen, name).click()  # a disabled button ignores the click

    def apply_now(self, *, retry: bool = True) -> None:
        """Apply now (spec S-24): publish, move Roblox's cache aside, restart Roblox if it runs.

        Links still downloading are waited for first, with a toast that shows it (M-APPLY-04);
        Apply now goes on by itself when the last one is done (without trying a failed one
        again, so a link that keeps failing can't keep it waiting).

        The cache moves only while no Player or Studio runs (S-24 rule 4): Studio, or a Player
        Verdra didn't start, is never closed; Apply now then says why the cache stayed. A Player
        Verdra started is closed after M-LAUNCH-03 and started again once the cache has moved.
        """
        grafts, sprout = self.services.grafts, self.services.sprout
        if grafts is None:
            return
        count = grafts.publish(retry=retry)
        if grafts.downloading:  # M-APPLY-04: go on once the links are here, without a 2nd click
            self._wait_for_downloads(grafts.downloading)
            return
        self._stop_waiting()
        if grafts.warnings:  # S-21: a replacement that can't be prepared is never silent
            self.window.dew.show(ApplyText().not_prepared(len(grafts.warnings)), Kind.WARNING)
        if sprout is None:
            self.window.dew.show(ApplyText().next_time(count))
            return
        running = sprout.roblox_processes()
        others = sprout.refresh_others()
        ours = sprout.players_started_here()
        clear = self._cache_can_move(running, others)
        if ours:
            dialog = DestructiveConfirmation(
                QCoreApplication.translate(
                    "M-LAUNCH-03", "Restart Roblox now? Unsaved progress in your game may be lost."
                ),
                QCoreApplication.translate("M-LAUNCH-03", "Restart Roblox"),
                parent=self.window,
            )
            if dialog.exec() != DestructiveConfirmation.DialogCode.Accepted:
                self.window.dew.show(ApplyText().next_time(count))  # S-24 rule 3
                return
            sprout.close_roblox()
            moved = sprout.clear_cache() if clear else None
            self._show_moved(moved)
            sprout.launch()
            text = ApplyText()
            self.window.dew.show(text.restarted(count) if moved else text.restarted_cached(count))
            return
        moved = sprout.clear_cache() if clear else None
        self._show_moved(moved)
        if not sprout.routing:
            sprout.start_routing()  # S-24 rule 2
        self.window.dew.show(ApplyText().next_time(count))

    def _wait_for_downloads(self, count: int) -> None:
        grafts = self.services.grafts
        if self.apply_waiting is not None or grafts is None:
            return  # already waiting: Apply now goes on once
        self.apply_waiting = self.window.dew.show(
            ApplyText().waiting(count),
            Kind.INFO,
            (QCoreApplication.translate("M-APPLY-04", "Cancel"), self._stop_waiting),
            progress=True,
        )
        grafts.settled.connect(self._downloads_settled)

    def _downloads_settled(self) -> None:
        if self.apply_waiting is None:
            return
        self._stop_waiting()
        self.apply_now(retry=False)

    def _stop_waiting(self) -> None:
        """Stop waiting for downloads (they carry on and apply when ready, S-21)."""
        grafts, toast = self.services.grafts, self.apply_waiting
        if toast is None:
            return  # not waiting
        self.apply_waiting = None
        if grafts is not None:
            grafts.settled.disconnect(self._downloads_settled)
        toast.dismiss()

    def _cache_can_move(self, running: RunningRoblox | None, others: frozenset[int]) -> bool:
        """Whether nothing but Verdra's own Players runs; else say why the cache stays."""
        if running is None:
            return False
        if running.studio:
            self.window.dew.show(
                QCoreApplication.translate(
                    "M-CACHE-02",
                    "Roblox Studio is open, so Verdra didn't move Roblox's saved assets aside. "
                    "Close Studio, then click Apply now again.",
                ),
                Kind.WARNING,
            )
            return False
        if others:
            self.window.dew.show(
                QCoreApplication.translate(
                    "M-CACHE-03",
                    "A Roblox Player that Verdra didn't start is running, so Verdra didn't move "
                    "Roblox's saved assets aside. Close it, then click Apply now again.",
                ),
                Kind.WARNING,
            )
            return False
        return True

    def _show_moved(self, moved: CacheMove | None) -> None:
        if moved is not None:
            self.window.dew.show(cache_moved_text(moved))

    def show_error(self) -> None:
        """M-ERR-01: an unhandled error was logged; say so, with a way to the details."""
        text = QCoreApplication.translate(
            "M-ERR-01", "Something went wrong. Details are in Activity."
        )
        if any(toast.text == text for toast in self.window.dew.toasts):
            return  # one notice for a burst of the same error, not one per click
        self.window.dew.show(
            text,
            Kind.ERROR,
            (
                QCoreApplication.translate("M-ERR-01", "Open Activity"),
                lambda: self.window.show_screen("activity"),
            ),
        )

    def show_other_tool(self, text: str) -> None:
        """M-COEX-01: another tool routes Roblox; "Try again" runs the check again (S-15)."""
        dialog = DestructiveConfirmation(
            text, QCoreApplication.translate("M-COEX-01", "Try again"), parent=self.window
        )
        if dialog.exec() == DestructiveConfirmation.DialogCode.Accepted:
            sprout = self.services.sprout
            if sprout is not None:
                sprout.retry()

    def show_launch_notice(self, text: str) -> None:
        """Show why routing or a launch didn't happen (M-LAUNCH-01, -04, -05, M-CA-01)."""
        self.window.notices.addWidget(Notice(text, Tone.WARNING, self.window, dismissible=True))

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

    def show_routing(self, view: StatusView) -> None:
        """Render a published routing status everywhere it shows (spec S-14)."""
        self.window.header.set_routing(view)
        if self.tray is not None:
            self.tray.set_status(status_of(view), reason=view.reason)

    def quit_and_erase(self) -> None:
        """Quit; shutdown then deletes Verdra's own folders (reset option, spec S-16)."""
        self.services.erase_own_data = True
        self.quit()

    def quit(self) -> None:
        """Quit Verdra (shutdown runs from the application's aboutToQuit).

        If a Roblox Verdra launched is still running and Verdra won't close it on quit, M-SHELL-02
        asks first (spec S-12, "Closing on quit").
        """
        sprout = self.services.sprout
        if (
            sprout is not None
            and not self.services.settings.value("routing.close_roblox_on_quit")
            and sprout.roblox_running()
        ):
            question = DestructiveConfirmation(
                QCoreApplication.translate("M-SHELL-02", "Quit Verdra while Roblox is running?"),
                QCoreApplication.translate("M-SHELL-02", "Quit"),
                QCoreApplication.translate(
                    "M-SHELL-02", "Your replacements stop the next time Roblox starts."
                ),
                self.window,
            )
            if question.exec() != DestructiveConfirmation.DialogCode.Accepted:
                return
        self.window.save_state()
        self.window.allow_close = True
        self.window.close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()

    # --- Dialogs --------------------------------------------------------------------------

    def show_about(self) -> None:
        """Open the About dialog."""
        AboutDialog(self.window).exec()

    def run_setup(self) -> None:
        """Show first-run onboarding (also from Settings › General › "Run setup again")."""
        settings = self.services.settings
        if not settings.read_only:
            settings.set("general.onboarding_done", False)
        self.onboarding = Onboarding(settings, self.window)
        self.onboarding.open()

    def show_shortcuts(self) -> None:
        """Open the keyboard shortcut overlay."""
        # Ctrl+N for a main screen the sidebar doesn't show does nothing, so it isn't listed.
        hidden = {f"Ctrl+{n}" for n in range(len(self.window.main_screens()) + 1, 10)}
        ShortcutHelp(self.window, self.shortcuts.working - hidden).exec()
