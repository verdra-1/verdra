# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Screen title, the status light and its popover (0027 §3, D3 screen 1).

Master plan 7.1. The header is 56 px tall and carries the screen title and, on the right, the
status light: the one routing status (spec S-14) as a leaf and a word. Clicking the light opens
the popover, which shows the reason, the other active reasons and at most one fix button that
emits `fix_requested` with the fix's key; a fix nobody handles yet is disabled with a tooltip
saying why (plan 5.4, rule 5). The approved D2 frame keeps the header to the title and the status
alone: the active profile is shown in the sidebar card, and "Apply now" lives with the
replacements it applies (Ctrl+Return and the popover fix reach it meanwhile).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from PySide6.QtCore import QCoreApplication, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Status
from verdra.canopy.leaves.empty import soon
from verdra.canopy.leaves.status_light import StatusLight, word_for

POPOVER_WIDTH = 300


class StatusView(Protocol):
    """What the interface reads from a published routing status (trunk passes roots' value)."""

    @property
    def state(self) -> object: ...
    @property
    def trigger(self) -> object: ...
    @property
    def reason(self) -> str: ...
    @property
    def others(self) -> tuple[str, ...]: ...


def status_of(view: StatusView) -> Status:
    """Return the badge status for a published routing status."""
    return Status(str(getattr(view.state, "value", view.state)))


def fix_for(view: StatusView) -> tuple[str, str] | None:
    """Return the popover's fix for a status as (key, button text), or None (spec S-14 table)."""
    status = status_of(view)
    trigger = str(getattr(view.trigger, "value", view.trigger))
    if status is Status.IDLE:
        return "start", QCoreApplication.translate("M-STATUS-03", "Start routing")
    if status is Status.ERROR:
        return "retry", QCoreApplication.translate("M-STATUS-05", "Try again")
    if status is not Status.DEGRADED:
        return None
    fixes = {
        "not_routed": lambda: (
            "restart_roblox",
            QCoreApplication.translate("M-STATUS-04", "Restart Roblox through Verdra"),
        ),
        "other_player": lambda: (
            "close_others",
            QCoreApplication.translate("M-LAUNCH-10", "Close Roblox…"),
        ),
        "not_reaching": lambda: (
            "support_bundle",
            QCoreApplication.translate("M-STATUS-08", "Save a support bundle…"),
        ),
        "no_asset_requests": lambda: (
            "apply_now",
            QCoreApplication.translate("M-STATUS-09", "Apply now"),
        ),
        "ca_missing": lambda: (
            "repair_certificate",
            QCoreApplication.translate("M-STATUS-04", "Repair certificate"),
        ),
    }
    fix = fixes.get(trigger)
    return fix() if fix is not None else None


class StatusPopover(QFrame):
    """The popover under the status pill: the reason and at most one fix button.

    Signals:
        fix_requested(key): The fix button was pressed ("start", "retry", "restart_roblox",
            "repair_certificate", "close_others", "support_bundle", "apply_now").
    """

    fix_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("popover", True)
        self.setFixedWidth(POPOVER_WIDTH)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        self._body = layout
        padding = tokens.length("space-4")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-2"))
        self.title = QLabel(self)
        theme.set_text_style(self.title, "body-strong")
        layout.addWidget(self.title)
        self.reason = QLabel(self)
        self.reason.setWordWrap(True)
        layout.addWidget(self.reason)
        self.others = QLabel(self)
        self.others.setWordWrap(True)
        self.others.setProperty("muted", True)
        layout.addWidget(self.others)
        self.fix = QPushButton(self)
        self.fix.clicked.connect(self._fix_clicked)
        layout.addWidget(self.fix, alignment=Qt.AlignmentFlag.AlignLeft)
        #: The fixes something handles; the others are shown disabled with M-SOON-01.
        self.handled: Collection[str] = ()
        self.fix_key: str | None = None
        self.view: StatusView | None = None

    def show_view(self, view: StatusView) -> None:
        """Fill the popover for a published routing status."""
        self.view = view
        status = status_of(view)
        word = word_for(
            str(getattr(view.state, "value", view.state)), has_fix=fix_for(view) is not None
        )
        self.title.setText(word.label())
        reason = view.reason
        if status is Status.IDLE:
            # M-STATUS-03: "Idle. Routing is off." Button "Start routing".
            reason = QCoreApplication.translate("M-STATUS-03", "Routing is off.")
        self.reason.setText(reason)
        self.reason.setVisible(bool(reason))
        self.others.setText("\n".join(view.others))
        self.others.setVisible(bool(view.others))
        fix = fix_for(view)
        self.fix_key = fix[0] if fix else None
        self.fix.setVisible(fix is not None)
        if fix is not None:
            key, text = fix
            self.fix.setText(text)
            self.fix.setAccessibleName(text)
            self.fix.setEnabled(key in self.handled)
            self.fix.setToolTip("" if key in self.handled else soon())
        self.size_to_contents()

    def size_to_contents(self) -> None:
        """Grow the popover's height so its wrapped reason is never cut off (law 1).

        The width is pinned at POPOVER_WIDTH, so the height is whatever the layout needs for the
        reason and the other reasons wrapped to that width. Computed from the layout's own hint
        (not the shown window), so it holds on a headless runner, where a top-level widget isn't
        resized to its contents on show. The style is applied first, so the hint uses the fonts
        the popover actually paints with (a theme stylesheet can set them).
        """
        self.ensurePolished()
        self._body.activate()
        height = self._body.heightForWidth(POPOVER_WIDTH)
        if height <= 0:  # nothing wraps in this state: the ordinary hint is enough
            height = self._body.sizeHint().height()
        self.setFixedHeight(height)
        self._body.activate()
        # A theme stylesheet's label padding can leave a wrapped label a pixel or two short of
        # the height its text needs at the width it is actually given; give that back (law 1).
        deficit = max(
            (
                label.heightForWidth(label.width()) - label.height()
                for label in (self.reason, self.others)
                if label.isVisibleTo(self) and label.wordWrap() and label.width() > 0
            ),
            default=0,
        )
        if deficit > 0:
            self.setFixedHeight(height + deficit)

    def _fix_clicked(self) -> None:
        if self.fix_key is not None:
            self.hide()
            self.fix_requested.emit(self.fix_key)

    def set_handled(self, keys: Collection[str]) -> None:
        """Enable the fixes in `keys` (the others stay disabled with M-SOON-01)."""
        self.handled = keys
        self.show_view(self.view if self.view is not None else IDLE)


class _Idle:
    """The status before anything is published: Idle, no reason."""

    state = "idle"
    trigger = None
    reason = ""
    others: tuple[str, ...] = ()


IDLE: StatusView = _Idle()


class Header(QFrame):
    """The window header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        tokens = theme.Tokens.load()
        self._row_height = tokens.length("header-height")
        self._hpad = tokens.length("space-6")
        self._vpad = tokens.length("space-2")
        self._gap = tokens.length("space-3")
        # The header keeps the width it is given and takes only the height it needs, so it can
        # grow to a second row when the title and controls don't fit side by side (law 1).
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(self._hpad, 0, self._hpad, 0)
        self._stack.setSpacing(0)
        self._row1 = QHBoxLayout()
        self._row1.setSpacing(self._gap)
        self._row2 = QHBoxLayout()
        self._row2.setSpacing(self._gap)
        self._stack.addLayout(self._row1)
        self._stack.addLayout(self._row2)

        self.title = QLabel(self)
        theme.set_text_style(self.title, "title-l")

        # The status light sits on the right of the title, and drops to a second row when the two
        # don't fit side by side (law 1). It is kept in its own container so the wrapping logic
        # has one widget to move.
        self.controls = QWidget(self)
        controls = QHBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(self._gap)

        self.light = StatusLight(self.controls)
        self.light.clicked.connect(self.open_popover)
        controls.addWidget(self.light)

        self.popover = StatusPopover(self)
        self._two_row: bool | None = None
        self._apply_rows(two_row=False)
        self.set_routing(IDLE)

    def _apply_rows(self, *, two_row: bool) -> None:
        """Lay the title and controls on one row, or stack them when they don't fit (law 1)."""
        if two_row == self._two_row:
            return
        self._two_row = two_row
        self._empty(self._row1)
        self._empty(self._row2)
        self._row1.addWidget(self.title)
        self._row1.addStretch()
        if two_row:
            self._row2.addStretch()
            self._row2.addWidget(self.controls)
        else:
            self._row1.addWidget(self.controls)
        self._set_height(two_row=two_row)

    def _empty(self, layout: QLayout) -> None:
        """Take every item off a row, keeping its widgets alive for the other row."""
        while layout.count():
            item = layout.takeAt(0)
            if item is None:  # pragma: no cover - count() guarantees an item; guard for the type
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(self)

    def _set_height(self, *, two_row: bool) -> None:
        """Fix the header's height to the chosen layout, tall enough for the text (law 1)."""
        title_height = max(self._row_height, self.title.sizeHint().height() + 2 * self._vpad)
        controls_height = max(self._row_height, self.controls.sizeHint().height() + 2 * self._vpad)
        self.setFixedHeight(
            title_height + controls_height if two_row else max(title_height, controls_height)
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Allow the header to be as narrow as its wider single row, so it can wrap instead of
        forcing the window wider (law 1): the minimum is the widest of the title and the controls,
        not their sum."""
        widest = max(self.title.minimumSizeHint().width(), self.controls.minimumSizeHint().width())
        return QSize(widest + 2 * self._hpad, self.height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        """Stack the controls onto a second row when they no longer fit beside the title."""
        super().resizeEvent(event)
        available = self.width() - 2 * self._hpad
        needed = self.title.sizeHint().width() + self._gap + self.controls.sizeHint().width()
        if available > 0:
            self._apply_rows(two_row=needed > available)

    def set_title(self, title: str) -> None:
        """Show the current screen's title."""
        self.title.setText(title)

    def set_routing(self, view: StatusView) -> None:
        """Show a published routing status in the light and its popover (spec S-14 rule 1)."""
        has_fix = fix_for(view) is not None
        self.light.set_word(
            word_for(str(getattr(view.state, "value", view.state)), has_fix=has_fix)
        )
        self.popover.show_view(view)

    def open_popover(self) -> None:
        """Open the status popover under the light."""
        anchor = self.light.mapToGlobal(
            QPoint(self.light.width() - POPOVER_WIDTH, self.light.height() + 4)
        )
        self.popover.move(anchor)
        self.popover.show()
        # Re-measure now the popover is shown and its children carry the theme's fonts, so a long
        # reason is never cut off (law 1, D1 audit blocker 2).
        self.popover.size_to_contents()
        self.popover.fix.setFocus()
