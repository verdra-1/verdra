# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""A fake Roblox client: CONNECT through Verdra's proxy, TLS, then raw HTTP/1.1 requests.

It records the exact bytes of each response it receives, so tests can compare them with what the
server sent. h11 tracks each exchange only to know where a response ends.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl

import h11


class FakeClient:
    """One TLS connection through the proxy to `host`."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self._conn = h11.Connection(h11.CLIENT)

    @classmethod
    async def connect(
        cls, proxy_port: int, host: str, context: ssl.SSLContext, port: int = 443
    ) -> FakeClient:
        """CONNECT to host:port through the proxy and complete TLS with `context`."""
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
        await writer.drain()
        answer = await reader.readuntil(b"\r\n\r\n")
        if not answer.startswith(b"HTTP/1.1 200 "):
            writer.close()
            raise ConnectionError(answer.decode("latin-1").strip())
        await writer.start_tls(context, server_hostname=host)
        return cls(reader, writer)

    async def exchange(self, request: bytes) -> bytes:
        """Send one raw request and return the raw bytes of its response."""
        if self._conn.our_state is h11.DONE:
            self._conn.start_next_cycle()
        method = request.split(b" ", 1)[0]
        self._conn.send(h11.Request(method=method, target=b"/", headers=[(b"Host", b"x")]))
        self._conn.send(h11.EndOfMessage())
        self.writer.write(request)
        await self.writer.drain()
        data = bytearray()
        while True:
            event = self._conn.next_event()
            if event is h11.NEED_DATA:
                chunk = await self.reader.read(65536)
                data += chunk
                self._conn.receive_data(chunk)
            elif isinstance(event, h11.EndOfMessage | h11.ConnectionClosed):
                return bytes(data)

    async def close(self) -> None:
        self.writer.close()
        with contextlib.suppress(OSError, TimeoutError, ssl.SSLError):
            await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
