# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Loopback listener, CONNECT handling, interception decision, TLS termination with leaf
certificates.

This part (spec S-11): the listener on 127.0.0.1 only, with the port fallback of plan 10.1;
`CONNECT host:port` handling; blind tunnels for hosts outside the interception set (bytes copied
both ways, no TLS termination); and the limits of S-11 rule 1 (256 concurrent connections, 30 s
idle). A host in the interception set is answered at once and handed to roots/hyphae, which
terminates TLS with its leaf. Everything runs on one asyncio loop, the proxy's own thread
(plan 8.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Final, Protocol

from PySide6.QtCore import QCoreApplication

from verdra.soil import terrain

log = logging.getLogger(__name__)

#: S-11 rule 1.
MAX_CONNECTIONS: Final = 256
IDLE_TIMEOUT_SECONDS: Final = 30.0
#: The longest request head Verdra reads before giving up on a client.
MAX_HEAD_BYTES: Final = 64 * 1024
_CHUNK: Final = 64 * 1024

Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]
Connector = Callable[[str, int], Awaitable[Streams]]


class Interceptor(Protocol):
    """Serves CONNECT targets in the interception set (roots/hyphae.Interception)."""

    def wants(self, host: str, port: int) -> bool:
        """Return whether host:port is intercepted."""
        ...

    async def serve(
        self, host: str, port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Terminate TLS on the client's connection and serve its requests."""
        ...


class ProxyStartError(RuntimeError):
    """Neither the configured port nor any other loopback port could be used (M-PROXY-01)."""

    def __init__(self, port: int) -> None:
        super().__init__(f"port {port} is in use and no other port was free")
        self.port = port


class Mycelium:
    """The loopback proxy listener."""

    def __init__(
        self,
        port: int,
        connect: Connector,
        *,
        max_connections: int = MAX_CONNECTIONS,
        idle_timeout: float = IDLE_TIMEOUT_SECONDS,
        interceptor: Interceptor | None = None,
        on_connect: Callable[[str, int], None] | None = None,
    ) -> None:
        self.requested_port = port
        #: Told about every CONNECT target, on the proxy's thread (S-14: Roblox traffic seen).
        self.on_connect = on_connect
        self.connect = connect
        self.interceptor = interceptor
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout
        self.port: int | None = None
        self.active = 0
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> int:
        """Listen on 127.0.0.1 and return the port.

        If the configured port is taken, any free loopback port is used for this session and
        M-PROXY-03 goes to Activity (plan 10.1).

        Raises:
            ProxyStartError: no loopback port could be used (M-PROXY-01).
        """
        try:
            self._server = await asyncio.start_server(
                self._accept, terrain.PROXY_HOST, self.requested_port
            )
        except OSError:
            try:
                self._server = await asyncio.start_server(self._accept, terrain.PROXY_HOST, 0)
            except OSError as error:
                raise ProxyStartError(self.requested_port) from error
            port = self._server.sockets[0].getsockname()[1]
            log.info(
                "%s",
                QCoreApplication.translate(
                    "M-PROXY-03",
                    "Port {port} was in use, so Verdra is using port {other} this session.",
                ).format(port=self.requested_port, other=port),
            )
        self.port = int(self._server.sockets[0].getsockname()[1])
        return self.port

    async def stop(self) -> None:
        """Stop listening and close every open connection."""
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.active >= self.max_connections:
            log.debug("Connection refused: %d connections are open", self.active)
            await _close(writer)
            return
        self.active += 1
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._serve(reader, writer)
        except OSError, asyncio.IncompleteReadError, TimeoutError:
            pass
        finally:
            self.active -= 1
            if task is not None:
                self._tasks.discard(task)
            await _close(writer)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=self.idle_timeout)
        if len(head) > MAX_HEAD_BYTES:
            return
        target = _connect_target(head)
        if target is None:
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        host, port = target
        if self.on_connect is not None:
            try:
                self.on_connect(host, port)
            except Exception as error:  # noqa: BLE001 - an observer never breaks a connection
                log.debug("The connect observer failed: %s", type(error).__name__)
        if self.interceptor is not None and self.interceptor.wants(host, port):
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await self.interceptor.serve(host, port, reader, writer)
            return
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                self.connect(host, port), timeout=self.idle_timeout
            )
        except OSError, TimeoutError:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        try:
            await self._tunnel(reader, writer, upstream_reader, upstream_writer)
        finally:
            await _close(upstream_writer)

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        """Copy bytes both ways until either side closes or both stay idle too long."""
        last = [time.monotonic()]

        async def pump(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
            while True:
                try:
                    data = await asyncio.wait_for(source.read(_CHUNK), timeout=self.idle_timeout)
                except TimeoutError:
                    if time.monotonic() - last[0] >= self.idle_timeout:
                        return
                    continue
                if not data:
                    return
                last[0] = time.monotonic()
                sink.write(data)
                await sink.drain()

        tasks = [
            asyncio.create_task(pump(client_reader, upstream_writer)),
            asyncio.create_task(pump(upstream_reader, client_writer)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def _connect_target(head: bytes) -> tuple[str, int] | None:
    """Return (host, port) from a `CONNECT host:port HTTP/1.x` request head, else None."""
    line = head.split(b"\r\n", 1)[0].decode("latin-1")
    parts = line.split(" ")
    if len(parts) != 3 or parts[0] != "CONNECT" or not parts[2].startswith("HTTP/1."):
        return None
    host, _, port = parts[1].rpartition(":")
    host = host.strip("[]")
    if not host or not port.isdigit() or not 0 < int(port) < 65536:
        return None
    return host, int(port)


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(OSError, ConnectionError):
        await writer.wait_closed()
