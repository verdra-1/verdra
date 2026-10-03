# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-11: the loopback listener, blind tunnels and limits (tests 2, 6 and 7)."""

import asyncio
import logging
import socket
import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from verdra.bark import resin
from verdra.roots import mycelium

NOW = datetime.now(UTC)


async def direct(host: str, port: int) -> mycelium.Streams:
    return await asyncio.open_connection(host, port)


@asynccontextmanager
async def proxy(
    idle_timeout: float = mycelium.IDLE_TIMEOUT_SECONDS,
) -> AsyncIterator[mycelium.Mycelium]:
    server = mycelium.Mycelium(0, direct, idle_timeout=idle_timeout)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def connect_through(server: mycelium.Mycelium, host: str, port: int) -> mycelium.Streams:
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    await writer.drain()
    status = await reader.readuntil(b"\r\n\r\n")
    assert status.startswith(b"HTTP/1.1 200 ")
    return reader, writer


def tls_server_context(tmp_path: Path, host: str) -> tuple[ssl.SSLContext, resin.Authority]:
    """A stand-in for a Roblox server: its own CA (not Verdra's) and a certificate for `host`."""
    authority = resin.create_authority(NOW)
    leaf = resin.issue_leaf(authority, host, NOW)
    cert = tmp_path / "server.pem"
    key = tmp_path / "server.key"
    cert.write_bytes(resin.certificate_pem(leaf.certificate))
    key.write_bytes(
        leaf.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return context, authority


def run[T](coroutine: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine(), timeout=30))


@pytest.mark.spec("S-11", 6)
def test_the_listener_binds_to_loopback_only() -> None:
    async def body() -> None:
        async with proxy() as server:
            assert server._server is not None
            addresses = {sock.getsockname()[0] for sock in server._server.sockets}
            assert addresses == {"127.0.0.1"}

    run(body)


@pytest.mark.spec("S-11", 6)
def test_a_taken_port_falls_back_to_another_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    taken = blocker.getsockname()[1]

    async def body() -> int:
        server = mycelium.Mycelium(taken, direct)
        port = await server.start()
        await server.stop()
        return port

    try:
        with caplog.at_level(logging.INFO, logger="verdra"):
            port = run(body)
    finally:
        blocker.close()
    assert port != taken
    assert [r.getMessage() for r in caplog.records] == [
        f"Port {taken} was in use, so Verdra is using port {port} this session."
    ]


@pytest.mark.spec("S-11", 6)
def test_no_free_port_means_routing_doesnt_start(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refused(*_args: object, **_kwargs: object) -> asyncio.Server:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(mycelium.asyncio, "start_server", refused)
    with pytest.raises(mycelium.ProxyStartError) as caught:
        run(lambda: mycelium.Mycelium(49443, direct).start())
    assert caught.value.port == 49443


@pytest.mark.spec("S-11", 2)
def test_other_hosts_are_tunneled_without_tls_termination(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    host = "www.roblox.com"
    server_context, server_ca = tls_server_context(tmp_path, host)
    seen: list[str | None] = []
    # The server records the SNI the client sent: Verdra passed the client's handshake on.
    server_context.sni_callback = lambda _sock, name, _ctx: seen.append(name)

    async def body() -> bytes:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            request = await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(request)).encode())
            writer.write(b"\r\n\r\n" + request)
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_context)
        upstream_port = upstream.sockets[0].getsockname()[1]
        async with proxy() as server:
            reader, writer = await connect_through(server, "127.0.0.1", upstream_port)
            # The client completes its own handshake with the server's certificate, which only
            # the server's CA vouches for: Verdra didn't terminate TLS.
            client = ssl.create_default_context(
                cadata=resin.certificate_pem(server_ca.certificate).decode()
            )
            await writer.start_tls(client, server_hostname=host)
            writer.write(b"GET /secret HTTP/1.1\r\nHost: www.roblox.com\r\n\r\n")
            await writer.drain()
            reply = await reader.read()
            writer.close()
        upstream.close()
        await upstream.wait_closed()
        return reply

    with caplog.at_level(logging.DEBUG, logger="verdra"):
        reply = run(body)
    assert reply.endswith(b"GET /secret HTTP/1.1\r\nHost: www.roblox.com\r\n\r\n")
    assert seen == [host]
    assert not any("/secret" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("S-11", 7)
def test_the_257th_connection_is_refused() -> None:
    async def body() -> tuple[bytes, int]:
        async with proxy() as server:
            held = [await asyncio.open_connection("127.0.0.1", server.port) for _ in range(256)]
            await asyncio.sleep(0.2)
            assert server.active == 256
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            refused = await asyncio.wait_for(reader.read(), timeout=5)
            writer.close()
            for _, held_writer in held:
                held_writer.close()
            return refused, server.max_connections

    refused, limit = run(body)
    assert refused == b""
    assert limit == 256


@pytest.mark.spec("S-11", 7)
def test_an_idle_tunnel_closes() -> None:
    async def body() -> float:
        async def silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.read()

        upstream = await asyncio.start_server(silent, "127.0.0.1", 0)
        port = upstream.sockets[0].getsockname()[1]
        async with proxy(idle_timeout=0.5) as server:
            reader, writer = await connect_through(server, "127.0.0.1", port)
            started = time.monotonic()
            assert await reader.read() == b""
            elapsed = time.monotonic() - started
            writer.close()
        upstream.close()
        return elapsed

    elapsed = run(body)
    assert 0.4 <= elapsed < 3
    assert mycelium.IDLE_TIMEOUT_SECONDS == 30.0


def test_a_request_that_isnt_connect_is_refused() -> None:
    async def body() -> bytes:
        async with proxy() as server:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n")
            await writer.drain()
            reply = await reader.read()
            writer.close()
            return reply

    assert run(body).startswith(b"HTTP/1.1 405 ")


def test_an_unreachable_upstream_gives_502() -> None:
    async def body() -> bytes:
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        async with proxy() as server:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            reply = await reader.read()
            writer.close()
            return reply

    assert run(body).startswith(b"HTTP/1.1 502 ")
