# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-14: the pill, its popover and the tray render the one published routing status."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tests.roots.test_routing_status import FakeClock
from tools import gallery
from verdra.canopy.crown.header import Header, fix_for
from verdra.canopy.crown.tray import Tray, tray_icon
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.badge import Status
from verdra.canopy.leaves.empty import soon
from verdra.roots.gardener import RoutingStatus, RoutingStatusSource, State, Trigger
from verdra.trunk.sapwood.startup import Services

#: Every state with every reason it can have (spec S-14 table), and the popover's fix.
CASES: list[tuple[RoutingStatus, str | None]] = [
    (RoutingStatus(State.IDLE), "Start routing"),
    (RoutingStatus(State.ROUTING), None),
    (
        RoutingStatus(
            State.DEGRADED,
            Trigger.NOT_ROUTED,
            "Roblox isn't routed through Verdra yet. Restart it from here.",
        ),
        "Restart Roblox through Verdra",
    ),
    (
        RoutingStatus(
            State.DEGRADED,
            Trigger.UPSTREAM_CERTIFICATE,
            "A Roblox server's certificate couldn't be verified (x). That request was blocked.",
        ),
        None,
    ),
    (
        RoutingStatus(State.DEGRADED, Trigger.NO_ASSET_REQUESTS, "Roblox hasn't asked."),
        "Apply now",
    ),
    (
        RoutingStatus(State.DEGRADED, Trigger.NOT_REACHING, "Roblox isn't reaching Verdra."),
        "Save a support bundle…",
    ),
    (
        RoutingStatus(State.DEGRADED, Trigger.CA_MISSING, "The certificate is missing.", ("a",)),
        "Repair certificate",
    ),
    (RoutingStatus(State.ERROR, Trigger.PROXY_FAILED, "No port was free."), "Try again"),
    (RoutingStatus(State.ERROR, Trigger.OTHER_TOOL, "Another tool routes Roblox."), "Try again"),
    (RoutingStatus(State.ERROR, Trigger.KEEPER, "The helper isn't running."), "Try again"),
]


@pytest.mark.spec("S-14", 2)
@pytest.mark.parametrize(("view", "fix"), CASES, ids=lambda c: getattr(c, "trigger", None) or "")
def test_pill_popover_and_tray_agree_in_every_state(
    qtbot: QtBot, view: RoutingStatus, fix: str | None
) -> None:
    header = Header()
    qtbot.addWidget(header)
    tray = Tray()
    header.set_routing(view)
    tray.set_status(Status(view.state.value), reason=view.reason)
    status = Status(view.state.value)
    assert header.pill.status is status
    assert header.pill.accessibleName() == f"Routing status: {status.label()}"
    assert header.popover.title.text() == status.label()
    if view.reason:
        assert header.popover.reason.text() == view.reason
    assert header.popover.others.text() == "\n".join(view.others)
    assert header.popover.fix.isVisibleTo(header.popover) is (fix is not None)
    if fix is not None:
        assert header.popover.fix.text() == fix
        assert header.popover.fix.accessibleName() == fix
    expected_icon = tray_icon(status, tray.variant()).pixmap(16).toImage()
    assert tray.icon.icon().pixmap(16).toImage() == expected_icon
    if status is Status.ROUTING:
        assert tray.status_action.text().startswith("Routing")
    elif view.reason:
        assert tray.status_action.text() == f"{status.label()}: {view.reason}"
    else:
        assert tray.status_action.text() == status.label()
    tray.deleteLater()


@pytest.mark.spec("S-14", 5)
@pytest.mark.parametrize(("view", "fix"), [c for c in CASES if c[1] is not None])
def test_each_fix_button_runs_its_action_and_is_reachable_by_keyboard(
    qtbot: QtBot, view: RoutingStatus, fix: str
) -> None:
    header = Header()
    qtbot.addWidget(header)
    key = fix_for(view)
    assert key is not None
    # Nothing handles it yet: disabled, saying why.
    header.set_routing(view)
    assert not header.popover.fix.isEnabled()
    assert header.popover.fix.toolTip() == soon()
    # A (fake) service handles it: enabled, focusable, and it emits its key.
    header.popover.handled = {key[0]}
    header.set_routing(view)
    button = header.popover.fix
    assert button.isEnabled()
    assert button.focusPolicy() & Qt.FocusPolicy.TabFocus
    asked: list[str] = []
    header.popover.fix_requested.connect(asked.append)
    qtbot.keyClick(button, Qt.Key.Key_Space)
    assert asked == [key[0]]


@pytest.fixture
def routed_shell(services: Services, qtbot: QtBot) -> Iterator[tuple[Shell, Callable[..., None]]]:
    clock = FakeClock()
    services.routing = RoutingStatusSource(clock.schedule)
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    yield shell, clock.advance
    shell.window.allow_close = True
    shell.window.close()
    services.routing.deleteLater()


def test_the_shell_follows_every_published_change(
    routed_shell: tuple[Shell, Callable[..., None]], services: Services
) -> None:
    shell, advance = routed_shell
    source = services.routing
    assert source is not None
    header = shell.window.header
    assert header.pill.status is Status.IDLE
    source.started()
    assert header.pill.status is Status.ROUTING
    source.launched()
    advance(20)
    assert header.pill.status is Status.DEGRADED
    assert header.popover.fix.text() == "Restart Roblox through Verdra"
    source.error(Trigger.OTHER_TOOL, "Another tool routes Roblox.")
    assert header.pill.status is Status.ERROR
    assert header.popover.reason.text() == "Another tool routes Roblox."
    assert header.popover.others.text() == (
        "Roblox isn't routed through Verdra yet. Restart it from here."
    )
    if shell.tray is not None:
        assert shell.tray.status is Status.ERROR


def test_without_a_status_source_the_shell_shows_idle(shell: Shell, qapp: QApplication) -> None:
    assert shell.window.header.pill.status is Status.IDLE
    assert shell.window.header.popover.reason.text() == "Routing is off."


#: A Degraded (f) reason and another active reason, as long as the real ones (D1 audit blocker 2).
LONG_REASON = (
    "Roblox isn't reaching Verdra: nothing from it came through in the minute after it started, "
    "so your replacements can't apply. Save a support bundle and send it with your report."
)
OTHER_REASON = "Roblox isn't routed through Verdra yet. Restart it from here."


@pytest.mark.spec("S-14", 2)
def test_the_popover_grows_to_fit_its_message(qtbot: QtBot) -> None:
    """Law 1 (D1 audit blocker 2): the popover's wrapped reason is never cut off, at any scale.

    At 300 px wide a long Degraded message wraps to several lines; the popover must take the
    height that needs. Checked at ~230 % text through the gallery's law-1 check, which fails on
    the old fixed-height popover.
    """
    header = Header()
    qtbot.addWidget(header)
    font = header.popover.reason.font()
    font.setPointSize(30)
    header.popover.reason.setFont(font)
    header.popover.others.setFont(font)
    header.set_routing(
        RoutingStatus(State.DEGRADED, Trigger.NOT_REACHING, LONG_REASON, (OTHER_REASON,))
    )
    popover = header.popover
    header.open_popover()
    qtbot.waitExposed(popover)
    for _ in range(3):
        QApplication.processEvents()
    clipped = [
        f.text for f in gallery.cut_off(popover, "test", "popover") if f.kind == "wrapped label"
    ]
    popover.hide()
    assert clipped == []
