# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Navigation, collapse to icons, items shown only in Advanced mode.

Master plan 7.1: the sidebar is 220 px wide and collapses to 64 px of icons with a chevron at the
bottom. The Verdra mark sits at the top; main screens follow (Traffic only in Advanced mode);
Activity, Settings and About sit at the foot.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme

MARK_SIZE = 28


@dataclass(frozen=True)
class Entry:
    """One sidebar entry."""

    key: str
    icon: str
    main: bool  # a main screen (Ctrl/Cmd+1 to 5), or a footer link
    advanced_only: bool = False

    def title(self) -> str:
        """Return the entry's label, which is also its screen's title."""
        titles = {
            "replacements": QCoreApplication.translate("Sidebar", "Replacements"),
            "library": QCoreApplication.translate("Sidebar", "Library"),
            "tweaks": QCoreApplication.translate("Sidebar", "Tweaks"),
            "accounts": QCoreApplication.translate("Sidebar", "Accounts"),
            "traffic": QCoreApplication.translate("Sidebar", "Traffic"),
            "activity": QCoreApplication.translate("Sidebar", "Activity"),
            "settings": QCoreApplication.translate("Sidebar", "Settings"),
            "about": QCoreApplication.translate("Sidebar", "About"),
        }
        return titles[self.key]


ENTRIES = (
    Entry("replacements", "graft", main=True),
    Entry("library", "seed", main=True),
    Entry("tweaks", "tweaks", main=True),
    Entry("accounts", "users", main=True),
    Entry("traffic", "activity", main=True, advanced_only=True),
    Entry("activity", "scroll-text", main=False),
    Entry("settings", "settings", main=False),
    Entry("about", "info", main=False),
)


class Sidebar(QFrame):
    """The navigation column.

    Signals:
        selected(key): An entry was chosen ("about" opens a dialog rather than a screen).
        collapsed_changed(collapsed): The sidebar was collapsed or expanded.
    """

    selected = Signal(str)
    collapsed_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        tokens = theme.Tokens.load()
        self.expanded_width = tokens.length("sidebar-width")
        self.collapsed_width = tokens.length("sidebar-width-collapsed")
        self.collapsed = False
        self.buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        margin = tokens.length("space-3")
        layout.setContentsMargins(margin, tokens.length("space-4"), margin, margin)
        layout.setSpacing(tokens.length("space-1"))

        brand = QHBoxLayout()
        brand.setSpacing(tokens.length("space-2"))
        self.mark = QLabel(self)
        self.mark.setFixedSize(QSize(MARK_SIZE, MARK_SIZE))
        self.mark.setAccessibleName(self.tr("Verdra"))
        brand.addWidget(self.mark)
        self.name = QLabel("Verdra", self)  # noqa: VT001 - the product name is never translated
        theme.set_text_style(self.name, "title-m")
        brand.addWidget(self.name)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(tokens.length("space-4"))

        for entry in ENTRIES:
            if entry.key == "activity":
                layout.addStretch()
            self.buttons[entry.key] = self._entry_button(entry)
            layout.addWidget(self.buttons[entry.key])

        self.toggle = QToolButton(self)
        self.toggle.setIconSize(QSize(20, 20))
        self.toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        layout.addSpacing(tokens.length("space-2"))
        layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        current = theme.Theme.instance()
        if current is not None:
            current.changed.connect(self.refresh_icons)
        self.refresh_icons()
        self.set_collapsed(False)

    def _entry_button(self, entry: Entry) -> QToolButton:
        button = QToolButton(self)
        button.setCheckable(entry.key != "about")
        button.setText(entry.title())
        button.setAccessibleName(entry.title())
        button.setToolTip(entry.title())
        button.setIconSize(QSize(20, 20))
        button.setMinimumHeight(36)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, key=entry.key: self.selected.emit(key))
        if button.isCheckable():
            self._group.addButton(button)
        return button

    def refresh_icons(self) -> None:
        """Repaint the mark and icons in the current theme."""
        current = theme.Theme.instance()
        dark = current is not None and current.mode == "dark"
        mark = theme.brand_file("symbol-reversed.svg" if dark else "symbol.svg")
        self.mark.setPixmap(theme.svg_pixmap(mark, MARK_SIZE, self.devicePixelRatioF()))
        for entry in ENTRIES:
            self.buttons[entry.key].setIcon(
                theme.icon(entry.icon, "ink-muted", 20, active="primary")
            )
        self._update_toggle()

    def select(self, key: str) -> None:
        """Mark an entry as the current screen."""
        button = self.buttons.get(key)
        if button is not None and button.isCheckable():
            button.setChecked(True)

    def set_advanced(self, advanced: bool) -> None:
        """Show or hide the entries that exist only in Advanced mode."""
        for entry in ENTRIES:
            if entry.advanced_only:
                self.buttons[entry.key].setVisible(advanced)

    def set_collapsed(self, collapsed: bool) -> None:
        """Collapse to icons only, or expand to icons and labels."""
        changed = collapsed != self.collapsed
        self.collapsed = collapsed
        self.setFixedWidth(self.collapsed_width if collapsed else self.expanded_width)
        self.name.setVisible(not collapsed)
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button in self.buttons.values():
            button.setToolButtonStyle(style)
        self._update_toggle()
        if changed:
            self.collapsed_changed.emit(collapsed)

    def _update_toggle(self) -> None:
        name = "chevrons-right" if self.collapsed else "chevrons-left"
        label = self.tr("Expand the sidebar") if self.collapsed else self.tr("Collapse the sidebar")
        self.toggle.setIcon(theme.icon(name, "ink-muted", 20))
        self.toggle.setAccessibleName(label)
        self.toggle.setToolTip(label)
