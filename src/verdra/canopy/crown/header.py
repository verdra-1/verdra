# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Screen title, status pill and its popover, profile selector, Apply now button.

Master plan 7.1. The header is 56 px tall. The pill and its popover render the one routing
status (spec S-14): its state, its reason, the other active reasons and at most one fix button,
which emits `fix_requested` with the fix's key. A fix nobody handles yet is disabled with a
tooltip saying why, as are the profile selector and "Apply now" until replacements exist (M2;
plan 5.4, rule 5).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from PySide6.QtCore import QCoreApplication, QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.badge import Status, StatusPill
from verdra.canopy.leaves.empty import soon

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
    if status is Status.DEGRADED and trigger == "not_routed":
        return "restart_roblox", QCoreApplication.translate(
            "M-STATUS-04", "Restart Roblox through Verdra"
        )
    if status is Status.DEGRADED and trigger == "other_player":
        return "close_others", QCoreApplication.translate("M-LAUNCH-10", "Close Roblox…")
    if status is Status.DEGRADED and trigger == "ca_missing":
        return "repair_certificate", QCoreApplication.translate("M-STATUS-04", "Repair certificate")
    return None


class StatusPopover(QFrame):
    """The popover under the status pill: the reason and at most one fix button.

    Signals:
        fix_requested(key): The fix button was pressed ("start", "retry", "restart_roblox",
            "repair_certificate").
    """

    fix_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("popover", True)
        self.setFixedWidth(POPOVER_WIDTH)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
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
        self.title.setText(status.label())
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
        self.setFixedHeight(tokens.length("header-height"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.length("space-6"), 0, tokens.length("space-6"), 0)
        layout.setSpacing(tokens.length("space-3"))

        self.title = QLabel(self)
        theme.set_text_style(self.title, "title-l")
        layout.addWidget(self.title)
        layout.addStretch()

        self.pill = StatusPill(self)
        self.pill.clicked.connect(self.open_popover)
        layout.addWidget(self.pill)
        self.popover = StatusPopover(self)
        self.set_routing(IDLE)

        not_yet = soon()
        self.profiles = QComboBox(self)
        self.profiles.setMinimumWidth(180)
        self.profiles.setPlaceholderText(self.tr("No profiles"))
        self.profiles.setAccessibleName(self.tr("Active profile"))
        self.profiles.setEnabled(False)
        self.profiles.setToolTip(not_yet)
        layout.addWidget(self.profiles)

        self.apply_now = QPushButton(self.tr("Apply now"), self)
        self.apply_now.setProperty("primary", True)
        self.apply_now.setAccessibleName(self.tr("Apply now"))
        self.apply_now.setEnabled(False)
        self.apply_now.setToolTip(not_yet)
        layout.addWidget(self.apply_now)

    def enable_apply(self) -> None:
        """Replacements exist (M2): "Apply now" works (spec S-24)."""
        self.apply_now.setEnabled(True)
        self.apply_now.setToolTip(self.tr("Use the replacements now"))

    def set_title(self, title: str) -> None:
        """Show the current screen's title."""
        self.title.setText(title)

    def set_routing(self, view: StatusView) -> None:
        """Show a published routing status in the pill and its popover (spec S-14 rule 1)."""
        self.pill.set_status(status_of(view))
        self.popover.show_view(view)

    def open_popover(self) -> None:
        """Open the status popover under the pill."""
        anchor = self.pill.mapToGlobal(
            QPoint(self.pill.width() - POPOVER_WIDTH, self.pill.height() + 4)
        )
        self.popover.move(anchor)
        self.popover.show()
        self.popover.fix.setFocus()
