# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tray or menu-bar icon, the tray menu (7.10), status-variant icons.

The icon shows the routing status (Master plan 4.6): on Windows and Linux the symbol in
`ink-muted` with a status dot, drawn for the taskbar's light or dark theme; on macOS a template
image the menu bar recolours, with the node carrying the status. Left-click opens the window on
Windows and Linux; on macOS the icon opens the menu.
"""

from __future__ import annotations

import sys
from typing import Literal

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Status
from verdra.canopy.leaves.empty import soon

#: Plan 4.6 tray sizes: Windows 16, 20, 24, 32; Linux 22, 24; macOS 18 pt (18 and 36 px).
TRAY_SIZES = (16, 18, 20, 22, 24, 32, 36)


def tray_icon(status: Status, variant: Literal["light", "dark", "template"]) -> QIcon:
    """Return the tray icon for a status, rendered at every tray size."""
    path = theme.brand_file(f"tray-{status.value}-{variant}.svg")
    result = QIcon()
    for size in TRAY_SIZES:
        result.addPixmap(theme.svg_pixmap(path, size))
    if variant == "template":
        result.setIsMask(True)
    return result


class Tray(QObject):
    """The tray icon and its menu.

    Signals:
        open_requested(): "Open Verdra", or a left-click on Windows and Linux.
        quit_requested(): "Quit Verdra".
    """

    open_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.status = Status.IDLE
        self.icon = QSystemTrayIcon(self)
        self.menu = QMenu()
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
        self.quit_action = QAction(self.tr("Quit Verdra"), self.menu)
        self.quit_action.triggered.connect(self.quit_requested)
        not_yet = soon()
        for action in (self.apply_action, self.pause_action, self.reset_action):
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
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda _scheme: self.set_status(self.status))
        self.set_status(Status.IDLE)

    @staticmethod
    def available() -> bool:
        """Return whether the system has a tray or menu bar for the icon."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def variant(self) -> Literal["light", "dark", "template"]:
        """Return which icon set suits the system's tray."""
        if sys.platform == "darwin":
            return "template"
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def set_status(self, status: Status, replacements: int = 0) -> None:
        """Show a routing status in the icon, its tooltip and the menu's status line."""
        self.status = status
        self.icon.setIcon(tray_icon(status, self.variant()))
        if status is Status.ROUTING:
            # M-STATUS-02: "Routing · <n> replacements active"
            line = QCoreApplication.translate(
                "M-STATUS-02", "Routing · %n replacements active", "", replacements
            )
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

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if sys.platform == "darwin":
            return  # The menu bar icon opens its menu.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_requested.emit()
