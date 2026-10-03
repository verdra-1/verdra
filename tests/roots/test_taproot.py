# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-11: upstream transports and verified TLS (plan 10.4; tests 3 and 8)."""

import asyncio
import ipaddress
import ssl
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from tests.roots.test_mycelium import tls_server_context
from verdra.bark import resin
from verdra.roots import taproot

HOST = "assetdelivery.roblox.com"


def run[T](coroutine: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine(), timeout=30))


def client_context(authority: resin.Authority) -> ssl.SSLContext:
    """The same policy as taproot.tls_context(), trusting the test CA instead of the OS store."""
    context = ssl.create_default_context(
        cadata=resin.certificate_pem(authority.certificate).decode()
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class Upstream:
    """A TLS server standing in for Roblox; it records the SNI it gets and echoes a path."""

    def __init__(self, tmp_path: Path, host: str = HOST) -> None:
        self.context, self.authority = tls_server_context(tmp_path, host)
        self.sni: list[str | None] = []
        self.context.sni_callback = lambda _sock, name, _ctx: self.sni.append(name)
        self.server: asyncio.Server | None = None

    async def __aenter__(self) -> int:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                line = await reader.readuntil(b"\r\n")
                writer.write(b"echo " + line)
                await writer.drain()
            except ConnectionError, asyncio.IncompleteReadError, ssl.SSLError:
                pass
            writer.close()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=self.context)
        return int(self.server.sockets[0].getsockname()[1])

    async def __aexit__(self, *_exc: object) -> None:
        assert self.server is not None
        self.server.close()


async def http_proxy(log: list[bytes]) -> asyncio.Server:
    """A minimal HTTP CONNECT proxy that records each request head."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        log.append(head)
        host, _, port = head.split(b" ")[1].decode().rpartition(":")
        up_reader, up_writer = await asyncio.open_connection(host.strip("[]"), int(port))
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        await pipe(reader, writer, up_reader, up_writer)

    return await asyncio.start_server(handle, "127.0.0.1", 0)


async def socks5_proxy(
    log: list[tuple[str, int, bytes]], credentials: tuple[bytes, bytes] | None
) -> asyncio.Server:
    """A minimal SOCKS5 proxy (RFC 1928/1929) that records the target and the auth method."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        _, count = await reader.readexactly(2)
        offered = await reader.readexactly(count)
        method = 2 if credentials else 0
        if bytes([method]) not in offered:
            writer.write(b"\x05\xff")
            await writer.drain()
            writer.close()
            return
        writer.write(bytes([5, method]))
        if credentials:
            _, ulen = await reader.readexactly(2)
            user = await reader.readexactly(ulen)
            (plen,) = await reader.readexactly(1)
            password = await reader.readexactly(plen)
            ok = (user, password) == credentials
            writer.write(b"\x01" + (b"\x00" if ok else b"\x01"))
            if not ok:
                await writer.drain()
                writer.close()
                return
        _, _, _, kind = await reader.readexactly(4)
        if kind == 3:
            (length,) = await reader.readexactly(1)
            host = (await reader.readexactly(length)).decode()
        else:
            host = str(ipaddress.ip_address(await reader.readexactly(4 if kind == 1 else 16)))
        (port,) = struct.unpack("!H", await reader.readexactly(2))
        log.append((host, port, bytes([method])))
        up_reader, up_writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"\x05\x00\x00\x01" + bytes(4) + b"\x00\x00")
        await writer.drain()
        await pipe(reader, writer, up_reader, up_writer)

    return await asyncio.start_server(handle, "127.0.0.1", 0)


async def pipe(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
    async def copy(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
        while data := await source.read(65536):
            sink.write(data)
            await sink.drain()
        sink.close()

    await asyncio.gather(copy(a_reader, b_writer), copy(b_reader, a_writer), return_exceptions=True)


async def fetch(transport: taproot.Transport, port: int, context: ssl.SSLContext) -> bytes:
    reader, writer = await taproot.open_tls(
        transport, HOST, port, context=context, address="127.0.0.1"
    )
    writer.write(b"GET /asset HTTP/1.1\r\n")
    await writer.drain()
    reply = await reader.readuntil(b"\r\n")
    writer.close()
    return reply


@pytest.mark.spec("S-11", 8)
def test_direct_keeps_sni_and_the_hostname_check(tmp_path: Path) -> None:
    upstream = Upstream(tmp_path)

    async def body() -> bytes:
        async with upstream as port:
            return await fetch(
                taproot.Transport("direct"), port, client_context(upstream.authority)
            )

    assert run(body) == b"echo GET /asset HTTP/1.1\r\n"
    assert upstream.sni == [HOST]  # SNI is the real name although the address was given


@pytest.mark.spec("S-11", 8)
@pytest.mark.parametrize("with_credentials", [False, True], ids=["anonymous", "basic auth"])
def test_http_connect(tmp_path: Path, with_credentials: bool) -> None:
    upstream = Upstream(tmp_path)
    heads: list[bytes] = []

    async def body() -> bytes:
        async with upstream as port:
            proxy = await http_proxy(heads)
            proxy_port = proxy.sockets[0].getsockname()[1]
            user, password = ("ana", "s3cret") if with_credentials else ("", "")
            transport = taproot.Transport("http", "127.0.0.1", proxy_port, user, password)
            reply = await fetch(transport, port, client_context(upstream.authority))
            proxy.close()
            return reply

    assert run(body) == b"echo GET /asset HTTP/1.1\r\n"
    assert heads[0].startswith(b"CONNECT 127.0.0.1:")
    assert (b"Proxy-Authorization: Basic YW5hOnMzY3JldA==" in heads[0]) == with_credentials
    assert upstream.sni == [HOST]


@pytest.mark.spec("S-11", 8)
@pytest.mark.parametrize("credentials", [None, (b"ana", b"s3cret")], ids=["no auth", "username"])
def test_socks5(tmp_path: Path, credentials: tuple[bytes, bytes] | None) -> None:
    upstream = Upstream(tmp_path)
    log: list[tuple[str, int, bytes]] = []

    async def body() -> bytes:
        async with upstream as port:
            proxy = await socks5_proxy(log, credentials)
            proxy_port = proxy.sockets[0].getsockname()[1]
            user, password = (c.decode() for c in credentials) if credentials else ("", "")
            transport = taproot.Transport("socks5", "127.0.0.1", proxy_port, user, password)
            reply = await fetch(transport, port, client_context(upstream.authority))
            proxy.close()
            return reply

    assert run(body) == b"echo GET /asset HTTP/1.1\r\n"
    assert log[0][0] == "127.0.0.1"
    assert log[0][2] == (b"\x02" if credentials else b"\x00")
    assert upstream.sni == [HOST]


def test_socks5_refuses_wrong_credentials(tmp_path: Path) -> None:
    async def body() -> None:
        proxy = await socks5_proxy([], (b"ana", b"s3cret"))
        proxy_port = proxy.sockets[0].getsockname()[1]
        transport = taproot.Transport("socks5", "127.0.0.1", proxy_port, "ana", "wrong")
        try:
            await taproot.open_tunnel(transport, HOST, 443)
        finally:
            proxy.close()

    with pytest.raises(taproot.UpstreamError, match="username or password"):
        run(body)


@pytest.mark.spec("S-11", 8)
def test_the_system_proxy_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = Upstream(tmp_path)
    heads: list[bytes] = []

    async def body() -> bytes:
        async with upstream as port:
            proxy = await http_proxy(heads)
            proxy_port = proxy.sockets[0].getsockname()[1]
            monkeypatch.setattr(
                taproot.urllib.request,
                "getproxies",
                lambda: {"https": f"http://127.0.0.1:{proxy_port}"},
            )
            reply = await fetch(
                taproot.Transport("system"), port, client_context(upstream.authority)
            )
            proxy.close()
            return reply

    assert run(body) == b"echo GET /asset HTTP/1.1\r\n"
    assert len(heads) == 1


def test_the_system_proxy_is_read_safely() -> None:
    def proxies(value: dict[str, str]) -> Callable[[], dict[str, str]]:
        return lambda: value

    assert taproot.resolve_system(49443, proxies({})).kind == "direct"
    assert (
        taproot.resolve_system(49443, proxies({"https": "http://127.0.0.1:49443"})).kind == "direct"
    )
    assert (
        taproot.resolve_system(49443, proxies({"https": "http://localhost:49443"})).kind == "direct"
    )
    http = taproot.resolve_system(49443, proxies({"https": "http://u:p@proxy.example:3128"}))
    assert (http.kind, http.host, http.port, http.username, http.password) == (
        "http",
        "proxy.example",
        3128,
        "u",
        "p",
    )
    socks = taproot.resolve_system(49443, proxies({"all": "socks5://proxy.example"}))
    assert (socks.kind, socks.port) == ("socks5", 1080)
    bare = taproot.resolve_system(49443, proxies({"https": "proxy.example:8000"}))
    assert (bare.kind, bare.port) == ("http", 8000)


@pytest.mark.spec("S-11", 3)
def test_a_self_signed_upstream_is_refused(tmp_path: Path) -> None:
    upstream = Upstream(tmp_path)

    async def body() -> None:
        async with upstream as port:
            # The real policy: the OS trust store, which doesn't know this server's CA.
            await fetch(taproot.Transport("direct"), port, taproot.tls_context())

    with pytest.raises(taproot.UpstreamVerificationError) as caught:
        run(body)
    assert caught.value.host == HOST


@pytest.mark.spec("S-11", 3)
def test_a_certificate_for_another_host_is_refused(tmp_path: Path) -> None:
    upstream = Upstream(tmp_path, host="other.roblox.com")

    async def body() -> None:
        async with upstream as port:
            await fetch(taproot.Transport("direct"), port, client_context(upstream.authority))

    with pytest.raises(taproot.UpstreamVerificationError, match="Hostname mismatch|hostname"):
        run(body)


def test_the_policy_is_tls_12_or_newer_with_verification() -> None:
    context = taproot.tls_context()
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
