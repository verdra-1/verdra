# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-14: the one routing status (roots/gardener.RoutingStatusSource), on a fake clock."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from verdra.roots import gardener
from verdra.roots.gardener import RoutingStatus, RoutingStatusSource, State, Trigger


class FakeClock:
    """A `Schedule` whose time only moves when the test says so."""

    def __init__(self) -> None:
        self.now = 0.0
        self.pending: list[tuple[float, Callable[[], None]]] = []

    def schedule(self, seconds: float, callback: Callable[[], None]) -> Callable[[], None]:
        entry = (self.now + seconds, callback)
        self.pending.append(entry)
        return lambda: self.pending.remove(entry) if entry in self.pending else None

    def advance(self, seconds: float) -> None:
        end = self.now + seconds
        while due := sorted((e for e in self.pending if e[0] <= end), key=lambda e: e[0]):
            entry = due[0]
            self.pending.remove(entry)
            self.now = entry[0]
            entry[1]()
        self.now = end


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def source(qapp: QApplication, clock: FakeClock) -> Iterator[RoutingStatusSource]:
    made = RoutingStatusSource(clock.schedule)
    yield made
    made.deleteLater()


def published(source: RoutingStatusSource) -> list[RoutingStatus]:
    seen: list[RoutingStatus] = []
    source.changed.connect(seen.append)
    return seen


def test_each_trigger_moves_the_status_and_clears(
    source: RoutingStatusSource, clock: FakeClock
) -> None:
    assert source.current == RoutingStatus(State.IDLE)
    source.started()
    assert source.current.state is State.ROUTING
    # (a) a launch with no Roblox traffic within 20 s, cleared by the first connection
    source.launched()
    clock.advance(19.9)
    assert source.current.state is State.ROUTING
    clock.advance(0.2)
    assert source.current.state is State.DEGRADED
    assert source.current.trigger is Trigger.NOT_ROUTED
    assert source.current.reason == "Roblox isn't routed through Verdra yet. Restart it from here."
    source.traffic_seen()
    assert source.current.state is State.ROUTING
    # traffic within the window: never Degraded
    source.launched()
    clock.advance(5)
    source.traffic_seen()
    clock.advance(60)
    assert source.current.state is State.ROUTING
    # (b) an upstream certificate failure, cleared after 2 minutes without another
    source.certificate_failed("A Roblox server's certificate couldn't be verified (x).")
    assert source.current.trigger is Trigger.UPSTREAM_CERTIFICATE
    clock.advance(100)
    source.certificate_failed("A Roblox server's certificate couldn't be verified (y).")
    clock.advance(100)
    assert source.current.state is State.DEGRADED  # the second failure restarted the window
    clock.advance(21)
    assert source.current.state is State.ROUTING
    # (c) a missing CA block, cleared by the repair
    source.ca_missing("Verdra's certificate is missing from Roblox version-2.")
    assert source.current.trigger is Trigger.CA_MISSING
    source.ca_repaired()
    assert source.current.state is State.ROUTING
    # Error, and stopping
    source.error(Trigger.OTHER_TOOL, "Another tool routes Roblox.")
    assert source.current.state is State.ERROR
    source.error_cleared(Trigger.OTHER_TOOL)
    source.stopped()
    assert source.current == RoutingStatus(State.IDLE)


def test_a_proxy_that_couldnt_start_is_an_error_even_while_off(
    source: RoutingStatusSource,
) -> None:
    source.error(Trigger.PROXY_FAILED, "Verdra couldn't start its proxy.")
    assert source.current.state is State.ERROR
    source.started()  # starting again clears it
    assert source.current.state is State.ROUTING
    with pytest.raises(ValueError, match="not an error trigger"):
        source.error(Trigger.CA_MISSING, "x")


@pytest.mark.spec("S-14", 3)
def test_error_beats_degraded_and_falls_back_to_it(source: RoutingStatusSource) -> None:
    source.started()
    source.ca_missing("Missing block.")
    source.certificate_failed("Unverified certificate.")
    assert source.current == RoutingStatus(
        State.DEGRADED, Trigger.UPSTREAM_CERTIFICATE, "Unverified certificate.", ("Missing block.",)
    )
    source.error(Trigger.OTHER_TOOL, "Another tool.")
    assert source.current.state is State.ERROR
    assert source.current.reason == "Another tool."
    assert source.current.others == ("Unverified certificate.", "Missing block.")
    source.error_cleared(Trigger.OTHER_TOOL)
    assert source.current == RoutingStatus(
        State.DEGRADED, Trigger.UPSTREAM_CERTIFICATE, "Unverified certificate.", ("Missing block.",)
    )


@pytest.mark.spec("S-14", 4)
def test_each_change_is_one_activity_record_and_holding_a_state_adds_none(
    source: RoutingStatusSource, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    seen = published(source)
    with caplog.at_level(logging.INFO, logger=gardener.__name__):
        source.started()
        source.started()  # no change: nothing published, nothing logged
        source.launched()
        clock.advance(20)
        clock.advance(300)  # five minutes in Degraded
        source.traffic_seen()
        source.error(Trigger.OTHER_TOOL, "Another tool routes Roblox.")
        clock.advance(300)
        source.stopped()
    records = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert records == [
        (logging.INFO, "Routing status changed from Idle to Routing."),
        (
            logging.WARNING,
            "Routing status changed from Routing to Degraded: Roblox isn't routed through "
            "Verdra yet. Restart it from here.",
        ),
        (logging.INFO, "Routing status changed from Degraded to Routing."),
        (
            logging.ERROR,
            "Routing status changed from Routing to Error: Another tool routes Roblox.",
        ),
    ]
    assert [s.state for s in seen] == [State.ROUTING, State.DEGRADED, State.ROUTING, State.ERROR]


def test_a_new_reason_in_the_same_state_is_published_but_not_logged_again(
    source: RoutingStatusSource, caplog: pytest.LogCaptureFixture
) -> None:
    source.started()
    seen = published(source)
    caplog.clear()  # count only what happens from here
    with caplog.at_level(logging.INFO, logger=gardener.__name__):
        source.ca_missing("First.")
        source.certificate_failed("Second.")
    assert [s.reason for s in seen] == ["First.", "Second."]
    assert len(caplog.records) == 1


@pytest.mark.spec("S-14", 6)
def test_with_routing_on_and_nothing_happening_no_timer_runs(
    source: RoutingStatusSource, clock: FakeClock
) -> None:
    source.started()
    assert clock.pending == []  # status is driven by events; idle routing schedules nothing
    source.launched()
    assert [round(when) for when, _ in clock.pending] == [20]
    source.traffic_seen()
    assert clock.pending == []
    source.certificate_failed("x")
    source.stopped()
    assert clock.pending == []  # stopping cancels the windows


def test_the_qt_timers_fire_and_cancel(qtbot: QtBot) -> None:
    owner = RoutingStatusSource()
    fired: list[str] = []
    schedule = gardener.qt_schedule(owner)
    schedule(0.01, lambda: fired.append("first"))
    cancel = schedule(0.01, lambda: fired.append("canceled"))
    cancel()
    cancel()  # twice is harmless
    qtbot.waitUntil(lambda: fired == ["first"], timeout=2000)
    qtbot.wait(50)
    assert fired == ["first"]
    owner.deleteLater()


UNREADABLE = "Some asset requests couldn't be read, so replacements may not apply."


@pytest.mark.spec("S-14", 1)
def test_an_unreadable_asset_batch_is_degraded_with_a_plain_reason(
    source: RoutingStatusSource, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    """(d), after the second swap test: a batch the grafter couldn't read is never silent."""
    source.started()
    with caplog.at_level(logging.INFO, logger="verdra.roots.gardener"):
        source.assets_unreadable()
    assert source.current == RoutingStatus(State.DEGRADED, Trigger.ASSETS_UNREADABLE, UNREADABLE)
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [
        f"Routing status changed from Routing to Degraded: {UNREADABLE}"
    ]
    clock.advance(100)
    source.assets_unreadable()  # another one restarts the window
    clock.advance(100)
    assert source.current.trigger is Trigger.ASSETS_UNREADABLE
    clock.advance(21)
    assert source.current.state is State.ROUTING
    source.assets_unreadable()
    source.stopped()  # routing off: nothing left to warn about
    assert source.current == RoutingStatus(State.IDLE)
    source.started()
    assert source.current.state is State.ROUTING
    assert clock.pending == []


def test_the_router_reports_an_unreadable_batch_from_any_thread(
    source: RoutingStatusSource, qtbot: QtBot
) -> None:
    router = gardener.Router(source)
    source.started()
    thread = threading.Thread(target=router.report_unreadable_assets, args=("damaged gzip data",))
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: source.current.trigger is Trigger.ASSETS_UNREADABLE, timeout=2000)
    assert source.current.reason == UNREADABLE
    router.deleteLater()


def test_with_replacements_a_launch_without_a_decrypted_request_is_degraded_after_a_minute(
    source: RoutingStatusSource, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    # M2 final test (g), 15 October 2026: Roblox connected, nothing was replaced, and the
    # status said Routing the whole time.
    source.started()
    source.launched(intercepting=True)
    clock.advance(5)
    source.traffic_seen()  # CONNECTs alone don't count
    with caplog.at_level(logging.WARNING, logger=gardener.__name__):
        clock.advance(gardener.INTERCEPT_WINDOW_SECONDS - 5.1)
        assert source.current.state is State.ROUTING
        clock.advance(0.2)
    assert source.current.state is State.DEGRADED
    assert source.current.trigger is Trigger.NOT_REACHING
    assert source.current.reason == gardener.not_reaching_text()
    assert source.current.reason.startswith("Roblox isn't reaching Verdra: ")
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert gardener.not_reaching_text() in caplog.records[0].getMessage()
    source.request_seen()
    assert source.current.state is State.ROUTING


def test_a_decrypted_request_in_time_or_no_replacements_means_no_warning(
    source: RoutingStatusSource, clock: FakeClock
) -> None:
    source.started()
    source.launched(intercepting=True)
    clock.advance(30)
    source.traffic_seen()
    source.request_seen()
    clock.advance(120)
    assert source.current.state is State.ROUTING
    source.launched()  # nothing to replace: nothing to decrypt
    source.traffic_seen()
    clock.advance(120)
    assert source.current.state is State.ROUTING
    assert clock.pending == []


def test_a_refused_handshake_is_degraded_at_once_until_a_request_gets_through(
    source: RoutingStatusSource, clock: FakeClock
) -> None:
    source.started()
    source.launched(intercepting=True)
    source.handshake_failed("Roblox couldn't open a secure connection to Verdra for x (y).")
    assert source.current.trigger is Trigger.NOT_REACHING
    assert source.current.reason.startswith("Roblox couldn't open a secure connection")
    assert all(callback != source._intercept_window_over for _, callback in clock.pending)
    source.request_seen()
    assert source.current.state is State.ROUTING
    source.handshake_failed("again")
    source.stopped()
    source.started()
    assert source.current.state is State.ROUTING


def test_the_router_reports_refused_handshakes_and_requests_from_any_thread(
    source: RoutingStatusSource, qtbot: QtBot
) -> None:
    router = gardener.Router(source)
    times = iter([100.0, 100.5, 101.6])
    router.clock = lambda: next(times)
    reached: list[str] = []
    router.reached.connect(reached.append)
    source.started()
    thread = threading.Thread(target=router.report_handshake_failure, args=("h", "refused"))
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: source.current.trigger is Trigger.NOT_REACHING, timeout=2000)
    assert source.current.reason == "refused"
    for host in ("a", "b", "c"):  # the second comes within a second of the first: not sent
        thread = threading.Thread(target=router.report_request, args=(host,))
        thread.start()
        thread.join()
    qtbot.waitUntil(lambda: source.current.state is State.ROUTING, timeout=2000)
    qtbot.waitUntil(lambda: reached == ["a", "c"], timeout=2000)
    router.deleteLater()
