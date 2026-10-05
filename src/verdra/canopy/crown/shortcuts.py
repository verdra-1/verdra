# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Keyboard shortcuts (7.1) and their help overlay.

Ctrl is Cmd on macOS (Qt maps `Ctrl` in key sequences to Command there). A shortcut whose
feature isn't built yet is registered but does nothing, so the key isn't taken by something else;
the help overlay lists only the shortcuts that work in this build.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from verdra.canopy.crown import theme


@dataclass(frozen=True)
class Binding:
    """One shortcut: its keys and what it does, as the help overlay lists it."""

    keys: str
    description: str


def bindings() -> list[Binding]:
    """Return every shortcut from Master plan 7.1, in the help overlay's order."""
    return [
        Binding("Ctrl+1", QCoreApplication.translate("Shortcuts", "Replacements")),
        Binding("Ctrl+2", QCoreApplication.translate("Shortcuts", "Library")),
        Binding("Ctrl+3", QCoreApplication.translate("Shortcuts", "Tweaks")),
        Binding("Ctrl+4", QCoreApplication.translate("Shortcuts", "Accounts")),
        Binding("Ctrl+5", QCoreApplication.translate("Shortcuts", "Traffic (Advanced mode)")),
        Binding("Ctrl+F", QCoreApplication.translate("Shortcuts", "Search this screen")),
        Binding("Ctrl+N", QCoreApplication.translate("Shortcuts", "Add a replacement")),
        Binding("Ctrl+Z", QCoreApplication.translate("Shortcuts", "Undo")),
        Binding("Shift+Ctrl+Z", QCoreApplication.translate("Shortcuts", "Redo")),
        Binding("Ctrl+Return", QCoreApplication.translate("Shortcuts", "Apply now")),
        Binding("Ctrl+,", QCoreApplication.translate("Shortcuts", "Open Settings")),
        Binding("Esc", QCoreApplication.translate("Shortcuts", "Close drawers and dialogs")),
        Binding("F1", QCoreApplication.translate("Shortcuts", "Show these shortcuts")),
    ]


class Shortcuts:
    """Registers the window's shortcuts."""

    def __init__(self, window: QWidget, actions: dict[str, Callable[[], None]]) -> None:
        self.shortcuts: dict[str, QShortcut] = {}
        for binding in bindings():
            if binding.keys == "Esc":
                continue  # Drawers and dialogs handle Esc themselves.
            shortcut = QShortcut(QKeySequence(binding.keys), window)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            action = actions.get(binding.keys)
            if action is not None:
                shortcut.activated.connect(action)
            self.shortcuts[binding.keys] = shortcut
        # Esc needs no shortcut of its own: dialogs (and, later, drawers) close on it.
        self.working = {"Esc", *(keys for keys in self.shortcuts if keys in actions)}


class ShortcutHelp(QDialog):
    """The help overlay that lists the shortcuts that work in this build."""

    def __init__(self, parent: QWidget | None = None, working: set[str] | None = None) -> None:
        """List the bindings whose keys are in `working` (every binding if it is None)."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Keyboard shortcuts"))
        self.setAccessibleName(self.tr("Keyboard shortcuts"))
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        padding = tokens.length("space-8")
        layout.setContentsMargins(padding, padding, padding, padding)
        title = QLabel(self.tr("Keyboard shortcuts"), self)
        theme.set_text_style(title, "title-m")
        layout.addWidget(title)
        form = QFormLayout()
        form.setHorizontalSpacing(tokens.length("space-6"))
        self.listed: list[str] = []
        for binding in bindings():
            if working is not None and binding.keys not in working:
                continue
            self.listed.append(binding.keys)
            keys = QKeySequence(binding.keys).toString(QKeySequence.SequenceFormat.NativeText)
            label = QLabel(keys, self)
            theme.set_text_style(label, "mono")
            form.addRow(label, QLabel(binding.description, self))
        layout.addLayout(form)
        close = QPushButton(self.tr("Close"), self)
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
