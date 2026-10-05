# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""First-run onboarding (7.9).

Four steps: Welcome (M-ONB-01), how it works (M-ONB-02), how Roblox reaches Verdra with the exact
system changes for the chosen mode (M-ONB-03), and the start (M-ONB-04). The routing choice is
saved to `routing.mode` and `routing.handle_roblox_links`; nothing on the system changes until
per-app routing exists (spec S-12). Finishing sets `general.onboarding_done`; Settings › General
› "Run setup again" shows it again.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.empty import soon
from verdra.canopy.leaves.switch import Switch

LOCKUP_WIDTH = 150


def system_changes(mode: str, handle_links: bool) -> list[str]:
    """Return the system changes a routing mode makes, as listed before "Allow and continue"."""
    changes = [
        QCoreApplication.translate(
            "M-ONB-06", "Add Verdra's certificate to Roblox's own trust file (not your system's)"
        )
    ]
    if mode == "hosts_file":
        changes += [
            QCoreApplication.translate(
                "M-ONB-07", "Install a small helper with administrator rights"
            ),
            QCoreApplication.translate(
                "M-ONB-08",
                "Point Roblox's addresses at this computer in the hosts file while routing",
            ),
        ]
    else:
        changes.append(
            QCoreApplication.translate(
                "M-ONB-09", "Start Roblox from Verdra with its proxy settings"
            )
        )
    if handle_links:
        changes.append(
            QCoreApplication.translate(
                "M-ONB-10", "Open games from the Roblox website through Verdra (link handler)"
            )
        )
    return changes


class Onboarding(QDialog):
    """The first-run setup."""

    def __init__(self, settings: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        title = QCoreApplication.translate("Onboarding", "Set up Verdra")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setFixedSize(560, 460)
        tokens = theme.Tokens.load()
        self.padding = tokens.length("space-8")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget(self)
        layout.addWidget(self.pages)
        self.pages.addWidget(self._welcome())
        self.pages.addWidget(self._how_it_works())
        self.pages.addWidget(self._routing())
        self.pages.addWidget(self._start())

    # --- Pages ----------------------------------------------------------------------------

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget(self.pages)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(self.padding, self.padding, self.padding, self.padding)
        layout.setSpacing(theme.Tokens.load().length("space-4"))
        return page, layout

    def _buttons(self, layout: QVBoxLayout, primary: QPushButton, back: bool = True) -> None:
        layout.addStretch()
        row = QHBoxLayout()
        if back:
            previous = QPushButton(QCoreApplication.translate("Onboarding", "Back"))
            previous.clicked.connect(
                lambda: self.pages.setCurrentIndex(self.pages.currentIndex() - 1)
            )
            row.addWidget(previous)
        row.addStretch()
        primary.setProperty("primary", True)
        primary.setDefault(True)
        row.addWidget(primary)
        layout.addLayout(row)

    def _next(self) -> None:
        self.pages.setCurrentIndex(self.pages.currentIndex() + 1)

    def _welcome(self) -> QWidget:
        page, layout = self._page()
        current = theme.Theme.instance()
        dark = current is not None and current.mode == "dark"
        lockup = QLabel(page)
        lockup.setAccessibleName("Verdra")  # noqa: VT001 - the product name is never translated
        lockup.setPixmap(
            theme.svg_pixmap(
                theme.brand_file("lockup-stacked-reversed.svg" if dark else "lockup-stacked.svg"),
                LOCKUP_WIDTH,
                self.devicePixelRatioF(),
            )
        )
        layout.addWidget(lockup, alignment=Qt.AlignmentFlag.AlignHCenter)
        heading = QLabel(QCoreApplication.translate("M-ONB-01", "Welcome to Verdra!"), page)
        theme.set_text_style(heading, "title-l")
        layout.addWidget(heading, alignment=Qt.AlignmentFlag.AlignHCenter)
        line = QLabel(
            QCoreApplication.translate(
                "M-ONB-01", "Change how your game looks, only on your screen."
            ),
            page,
        )
        line.setProperty("muted", True)
        layout.addWidget(line, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.get_started = QPushButton(QCoreApplication.translate("M-ONB-01", "Get started"), page)
        self.get_started.clicked.connect(self._next)
        self._buttons(layout, self.get_started, back=False)
        return page

    def _how_it_works(self) -> QWidget:
        page, layout = self._page()
        heading = QLabel(QCoreApplication.translate("Onboarding", "How Verdra works"), page)
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        for icon_name, text in (
            ("leaf", QCoreApplication.translate("M-ONB-02", "Everything stays on this computer.")),
            (
                "users",
                QCoreApplication.translate("M-ONB-02", "Other players see the game as usual."),
            ),
            ("undo-2", QCoreApplication.translate("M-ONB-02", "Every change can be undone.")),
        ):
            row = QHBoxLayout()
            icon = QLabel(page)
            current = theme.Theme.instance()
            color = theme.Tokens.load().color("primary", current.mode if current else "light")
            icon.setPixmap(theme.icon_pixmap(icon_name, color, 20, self.devicePixelRatioF()))
            row.addWidget(icon)
            row.addWidget(QLabel(text, page), 1)
            layout.addLayout(row)
        self.continue_button = QPushButton(
            QCoreApplication.translate("Onboarding", "Continue"), page
        )
        self.continue_button.clicked.connect(self._next)
        self._buttons(layout, self.continue_button)
        return page

    def _routing(self) -> QWidget:
        page, layout = self._page()
        heading = QLabel(
            QCoreApplication.translate("M-ONB-03", "How should Roblox reach Verdra?"), page
        )
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        self.per_app = QRadioButton(
            QCoreApplication.translate("M-ONB-03", "Per app (recommended)"), page
        )
        self.hosts_file = QRadioButton(
            QCoreApplication.translate("M-ONB-03", "Hosts file (needs administrator rights)"), page
        )
        self.hosts_file.setEnabled(False)
        self.hosts_file.setToolTip(soon())
        group = QButtonGroup(page)
        group.addButton(self.per_app)
        group.addButton(self.hosts_file)
        mode = self.settings.value("routing.mode")
        (self.hosts_file if mode == "hosts_file" else self.per_app).setChecked(True)
        layout.addWidget(self.per_app)
        layout.addWidget(self.hosts_file)

        links = QHBoxLayout()
        links_label = QLabel(
            QCoreApplication.translate(
                "Settings", "Open games started from the Roblox website through Verdra"
            ),
            page,
        )
        links_label.setWordWrap(True)
        links.addWidget(links_label, 1)
        self.handle_links = Switch(page)
        self.handle_links.setAccessibleName(links_label.text())
        self.handle_links.setChecked(bool(self.settings.value("routing.handle_roblox_links")))
        links.addWidget(self.handle_links)
        layout.addLayout(links)

        caption = QLabel(
            QCoreApplication.translate(
                "M-ONB-05", "Verdra will make these changes, and Reset everything removes them:"
            ),
            page,
        )
        caption.setProperty("muted", True)
        layout.addWidget(caption)
        self.changes = QLabel(page)
        self.changes.setWordWrap(True)
        layout.addWidget(self.changes)
        for widget in (self.per_app, self.hosts_file):
            widget.toggled.connect(self._refresh_changes)
        self.handle_links.toggled.connect(self._refresh_changes)
        self._refresh_changes()

        self.allow = QPushButton(QCoreApplication.translate("M-ONB-03", "Allow and continue"), page)
        self.allow.clicked.connect(self._save_routing)
        self._buttons(layout, self.allow)
        return page

    def _start(self) -> QWidget:
        page, layout = self._page()
        heading = QLabel(QCoreApplication.translate("M-ONB-04", "You're set."), page)
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        not_yet = soon()
        self.later_buttons: list[QPushButton] = []
        for text in (
            QCoreApplication.translate("M-ONB-04", "Import replacement profiles…"),
            QCoreApplication.translate("M-ONB-04", "Browse presets"),
            QCoreApplication.translate("M-ONB-04", "Launch Roblox through Verdra"),
        ):
            button = QPushButton(text, page)
            button.setEnabled(False)
            button.setToolTip(not_yet)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
            self.later_buttons.append(button)
        self.finish = QPushButton(QCoreApplication.translate("M-ONB-04", "Finish"), page)
        self.finish.clicked.connect(self._finish)
        self._buttons(layout, self.finish)
        return page

    # --- Actions --------------------------------------------------------------------------

    def chosen_mode(self) -> str:
        """Return the routing mode the user picked."""
        return "hosts_file" if self.hosts_file.isChecked() else "per_app"

    def _refresh_changes(self) -> None:
        items = system_changes(self.chosen_mode(), self.handle_links.isChecked())
        self.changes.setText("\n".join(f"•  {item}" for item in items))

    def _save_routing(self) -> None:
        if not self.settings.read_only:
            self.settings.set("routing.mode", self.chosen_mode())
            self.settings.set("routing.handle_roblox_links", self.handle_links.isChecked())
        self._next()

    def _finish(self) -> None:
        if not self.settings.read_only:
            self.settings.set("general.onboarding_done", True)
        self.accept()
