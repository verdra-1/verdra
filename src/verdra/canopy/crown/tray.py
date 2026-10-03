# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tray or menu-bar icon, the tray menu (7.10), status-variant icons.

The icon shows the routing status (Master plan 4.6): the symbol in `ink-muted` with a status
dot, drawn for the taskbar's light or dark theme. Left-click opens the window. (The macOS
template images are still generated, but macOS is deferred until after 1.0: decision record
0014.)
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Status
from verdra.canopy.leaves.empty import soon

#: Plan 4.6 tray sizes: Windows 16, 20, 24, 32; Linux 22, 24.
TRAY_SIZES = (16, 20, 22, 24, 32)


def tray_icon(status: Status, variant: Literal["light", "dark"]) -> QIcon:
    """Return the tray icon for a status, rendered at every tray size."""
    path = theme.brand_file(f"tray-{status.value}-{variant}.svg")
    result = QIcon()
    for size in TRAY_SIZES:
        result.addPixmap(theme.svg_pixmap(path, size))
    return result


class Tray(QObject):
    """The tray icon and its menu.

    Signals:
        open_requested(): "Open Verdra", or a left-click on Windows and Linux.
        quit_requested(): "Quit Verdra".
        reset_requested(): "Reset everything…" (spec S-16).
    """

    open_requested = Signal()
    quit_requested = Signal()
    reset_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.status = Status.IDLE
        self.reason = ""
        self.icon = QSystemTrayIcon(self)
        # A menu can only have a widget as parent, so it goes when the tray goes.
        self.menu = QMenu()
        self.destroyed.connect(self.menu.deleteLater)
        self.menu.setAccessibleName(self.tr("Verdra menu"))
        # Menus hide action tooltips unless asked; the unbuilt items explain themselves there.
        self.menu.setToolTipsVisible(True)
        self.open_action = QAction(self.tr("Open Verdra"), self.menu)
        self.open_action.triggered.connect(self.open_requested)
        self.status_action = QAction(self.menu)
        self.status_action.setEnabled(False)
        self.apply_action = QAction(self.tr("Apply now"), self.menu)
        self.pause_action = QAction(self.tr("Pause routing"), self.menu)
        self.reset_action = QAction(self.tr("Reset everything…"), self.menu)
        self.reset_action.triggered.connect(self.reset_requested)
        self.quit_action = QAction(self.tr("Quit Verdra"), self.menu)
        self.quit_action.triggered.connect(self.quit_requested)
        not_yet = soon()
        for action in (self.apply_action, self.pause_action):
            action.setEnabled(False)
            action.setToolTip(not_yet)
        self.menu.addAction(self.open_action)
        self.menu.addAction(self.status_action)
        self.menu.addAction(self.apply_action)
        self.menu.addAction(self.pause_action)
        self.menu.addAction(self.reset_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        # A bound method, not a lambda: Qt drops the connection when the tray is destroyed, so the
        # app-wide signal never reaches a deleted menu.
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._scheme_changed)
        self.set_status(Status.IDLE)

    @staticmethod
    def available() -> bool:
        """Return whether the system has a tray or menu bar for the icon."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def variant(self) -> Literal["light", "dark"]:
        """Return which icon set suits the system's tray."""
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def set_status(self, status: Status, replacements: int = 0, reason: str = "") -> None:
        """Show a routing status in the icon, its tooltip and the menu's status line.

        The line reads M-STATUS-02 in Routing, and the state word with its reason otherwise
        (spec S-14, "Tray").
        """
        self.status = status
        self.reason = reason
        self.icon.setIcon(tray_icon(status, self.variant()))
        if status is Status.ROUTING:
            # M-STATUS-02: "Routing · <n> replacements active". `tr` with a count makes this a
            # plural entry in the catalog ("1 replacement", "2 replacements").
            line = self.tr("Routing · %n replacements active", "M-STATUS-02", replacements)
        elif reason:
            line = self.tr("{state}: {reason}").format(state=status.label(), reason=reason)
        else:
            line = status.label()
        self.status_action.setText(line)
        self.icon.setToolTip(f"Verdra · {line}")  # noqa: VT001 - product name and a translated line

    def show(self) -> None:
        """Show the icon."""
        self.icon.show()

    def hide(self) -> None:
        """Hide the icon."""
        self.icon.hide()

    def _scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        self.set_status(self.status, reason=self.reason)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_requested.emit()
