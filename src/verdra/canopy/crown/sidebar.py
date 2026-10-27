# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Navigation, collapse to icons, items shown only in Advanced mode.

Master plan 7.1: the sidebar is 220 px wide and collapses to 64 px of icons with a chevron at the
bottom. The Verdra mark sits at the top; main screens follow (Traffic only in Advanced mode);
Activity, Settings and About sit at the foot. Library carries a muted "coming later" note (D2
screen 1, honest: it isn't built yet), and a card above the chevron names the shown profile and
opens the profile popover to switch, create, rename, delete or turn one on or off (D3 screen 2).
Both are text, so they hide when collapsed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
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
from verdra.canopy.crown.profiles import ProfilePopover, ProfileView


class _ProfileCard(QFrame):
    """The sidebar's profile card: a click or Space/Enter opens the profile popover.

    Signals:
        clicked(): The card was activated with the mouse or keyboard.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("profileCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


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
        #: The design width (plan 7.1); the sidebar grows past it so a label is never cut off
        #: at larger text (law 1), never shrinks below it.
        self._base_width = tokens.length("sidebar-width")
        self.expanded_width = self._base_width
        self.collapsed_width = tokens.length("sidebar-width-collapsed")
        self.collapsed = False
        self.buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        margin = tokens.length("space-3")
        self._side_margin = margin  # left + right padding, for the expanded-width measurement
        layout.setContentsMargins(margin, tokens.length("space-4"), margin, margin)
        layout.setSpacing(tokens.length("space-1"))

        layout.addLayout(self._build_brand(tokens))
        layout.addSpacing(tokens.length("space-4"))

        for entry in ENTRIES:
            if entry.key == "activity":
                layout.addStretch()
            button = self._entry_button(entry)
            self.buttons[entry.key] = button
            if entry.key == "library":
                layout.addWidget(self._later_row(button))
            else:
                layout.addWidget(button)

        self._profiles: list[ProfileView] = []
        self._selected_profile: str | None = None
        self.profiles_popover = ProfilePopover(self)
        self.profile_card = self._profile_card()
        layout.addSpacing(tokens.length("space-2"))
        layout.addWidget(self.profile_card)
        self.set_profiles((), None)

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

    def _build_brand(self, tokens: theme.Tokens) -> QHBoxLayout:
        """The Verdra mark and wordmark at the top of the sidebar."""
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
        return brand

    def _later_row(self, button: QToolButton) -> QWidget:
        """The Library row with a muted "coming later" note beside it (honest: it isn't built)."""
        row = QWidget(self)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(theme.Tokens.load().length("space-1"))
        box.addWidget(button, 1)
        self.later_caption = QLabel(self.tr("coming later"), row)
        self.later_caption.setProperty("muted", True)
        theme.set_text_style(self.later_caption, "caption")
        box.addWidget(self.later_caption)
        note = self.tr("Library — coming later")
        button.setToolTip(note)
        button.setAccessibleName(note)
        return row

    def _profile_card(self) -> _ProfileCard:
        """The card naming the active profile; a click opens the profile popover (D3 screen 2)."""
        tokens = theme.Tokens.load()
        pad = tokens.length("space-3")
        card = _ProfileCard(self)
        card.setAccessibleName(self.tr("Profiles"))
        box = QVBoxLayout(card)
        box.setContentsMargins(pad, pad, pad, pad)
        box.setSpacing(tokens.length("space-1"))
        label = QLabel(self.tr("Profile"), card)
        theme.set_text_style(label, "label")
        label.setProperty("muted", True)
        box.addWidget(label)
        self.profile_name = QLabel(card)
        self.profile_name.setWordWrap(True)
        theme.set_text_style(self.profile_name, "body-strong")
        box.addWidget(self.profile_name)
        self.profile_count = QLabel(card)
        self.profile_count.setProperty("muted", True)
        theme.set_text_style(self.profile_count, "caption")
        box.addWidget(self.profile_count)
        card.clicked.connect(self.open_profiles)
        return card

    def open_profiles(self) -> None:
        """Open the profile popover above the card (it is near the foot of the sidebar)."""
        self.profiles_popover.show_profiles(self._profiles, self._selected_profile)
        anchor = self.profile_card.mapToGlobal(
            QPoint(0, -self.profiles_popover.sizeHint().height())
        )
        self.profiles_popover.move(anchor)
        self.profiles_popover.show()
        self.profiles_popover.list.setFocus()

    def set_profiles(self, profiles: Sequence[ProfileView], selected_id: str | None = None) -> None:
        """Name the shown profile in the card, and keep the popover's list in step.

        The shown profile is `selected_id` when given and present, else the first; the card falls
        back to an empty state when there is no profile.
        """
        self._profiles = list(profiles)
        ids = [p.id for p in self._profiles]
        self._selected_profile = selected_id if selected_id in ids else (ids[0] if ids else None)
        active = next((p for p in self._profiles if p.id == self._selected_profile), None)
        if active is None:
            self.profile_name.setText(self.tr("No profile yet"))
            self.profile_count.setText("")
            self.profile_count.setVisible(False)
        else:
            self.profile_name.setText(active.name)
            count = len(getattr(active, "replacements", ()) or ())
            self.profile_count.setText(
                QCoreApplication.translate("Sidebar", "%n replacements", None, count)
            )
            self.profile_count.setVisible(True)
        if self.profiles_popover.isVisible():
            self.profiles_popover.show_profiles(self._profiles, self._selected_profile)

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
        if not self.collapsed:  # the text may have grown; keep every label readable (law 1)
            self.setFixedWidth(self._expanded_width())

    def _expanded_width(self) -> int:
        """The expanded width: the design width, or wider so no label is cut (law 1).

        Measured from the buttons' own size hints in the text beside icon style, so it tracks the
        current text size; it is only read while expanded, when that style is set.
        """
        widest = max((button.sizeHint().width() for button in self.buttons.values()), default=0)
        # The Library row also carries its "coming later" note, so it is wider than its button.
        library = self.buttons["library"].sizeHint().width()
        library += self.later_caption.sizeHint().width() + theme.Tokens.load().length("space-1")
        widest = max(widest, library)
        return max(self._base_width, widest + 2 * self._side_margin)

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
        self.name.setVisible(not collapsed)
        # The "coming later" note and the profile card are text; they hide with the labels.
        self.later_caption.setVisible(not collapsed)
        self.profile_card.setVisible(not collapsed)
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button in self.buttons.values():
            button.setToolButtonStyle(style)
        # Set the width after the style, so an expanded sidebar is measured with its labels on.
        if collapsed:
            self.setFixedWidth(self.collapsed_width)
        else:
            self.expanded_width = self._expanded_width()
            self.setFixedWidth(self.expanded_width)
        self._update_toggle()
        if changed:
            self.collapsed_changed.emit(collapsed)

    def _update_toggle(self) -> None:
        name = "chevrons-right" if self.collapsed else "chevrons-left"
        label = self.tr("Expand the sidebar") if self.collapsed else self.tr("Collapse the sidebar")
        self.toggle.setIcon(theme.icon(name, "ink-muted", 20))
        self.toggle.setAccessibleName(label)
        self.toggle.setToolTip(label)
