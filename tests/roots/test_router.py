# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The routing lifecycle (roots/gardener.Router): the proxy on its own thread (plan 8.3, 10.1)."""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Iterator

import pytest
from pytestqt.qtbot import QtBot

from tests.roots.test_routing_status import FakeClock
from verdra.roots import gardener, mycelium
from verdra.roots.gardener import RoutingStatusSource, State, Trigger


async def direct(host: str, port: int) -> mycelium.Streams:
    return await asyncio.open_connection(host, port)


def connect_through(port: int, target_port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.sendall(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n\r\n".encode())
        return client.recv(64)


@pytest.fixture
def target() -> Iterator[int]:
    """A listener that accepts and closes, standing in for a server."""
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def serve() -> None:
        try:
            while True:
                accepted, _ = server.accept()
                accepted.close()
        except OSError:
            return

    threading.Thread(target=serve, daemon=True).start()
    yield port
    server.close()


def test_routing_starts_reports_traffic_on_the_qt_thread_and_stops(
    qtbot: QtBot, target: int
) -> None:
    clock = FakeClock()
    status = RoutingStatusSource(clock.schedule)
    router = gardener.Router(status)
    seen: list[tuple[str, bool]] = []
    router.connected.connect(
        lambda host: seen.append((host, threading.current_thread() is threading.main_thread()))
    )
    port = router.start(0, direct)
    try:
        assert router.running and port == router.port
        assert status.current.state is State.ROUTING
        status.launched()
        assert connect_through(port, target).startswith(b"HTTP/1.1 200 ")
        qtbot.waitUntil(lambda: seen == [("127.0.0.1", True)], timeout=5000)
        clock.advance(gardener.LAUNCH_WINDOW_SECONDS)  # traffic came in time: no Degraded
        assert status.current.state is State.ROUTING
        assert router.start(0, direct) == port  # already running: the same proxy
    finally:
        router.stop()
    assert not router.running
    assert status.current.state is State.IDLE
    assert not any(t.name == "verdra-proxy" and t.is_alive() for t in threading.enumerate())


def test_no_free_port_is_error_m_proxy_01(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("in use")

    monkeypatch.setattr(asyncio, "start_server", refuse)
    status = RoutingStatusSource(FakeClock().schedule)
    router = gardener.Router(status)
    with pytest.raises(mycelium.ProxyStartError):
        router.start(49443, direct)
    assert not router.running
    assert status.current.state is State.ERROR
    assert status.current.trigger is Trigger.PROXY_FAILED
    assert "port 49443 is in use" in status.current.reason
    assert not any(t.name == "verdra-proxy" and t.is_alive() for t in threading.enumerate())
