# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Upstream side: verified TLS, SNI, transports (direct, system, HTTP CONNECT, SOCKS5), connection
pool.

Plan 10.4: certificates are verified against the OS trust store (truststore), the hostname is
checked, TLS 1.2 is the minimum and SNI is the real host name even when the connection goes to
a pre-resolved address. There is no way to turn verification off. Transports: direct, the
system proxy, a manual HTTP CONNECT proxy and a manual SOCKS5 proxy (RFC 1928) with optional
username and password (RFC 1929; the password comes from the secret store).
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import ssl
import struct
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlsplit

import truststore

Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]
Kind = Literal["system", "direct", "http", "socks5"]

_SOCKS_VERSION: Final = 5
_MAX_HEAD_BYTES: Final = 64 * 1024


class UpstreamError(OSError):
    """The upstream connection couldn't be made through the transport."""


class UpstreamVerificationError(UpstreamError):
    """The server's certificate didn't verify (M-PROXY-02)."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"{host}: {reason}")
        self.host = host
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Transport:
    """How Verdra reaches the internet (Reference R2, `routing.upstream.*`)."""

    kind: Kind = "system"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""


def tls_context() -> ssl.SSLContext:
    """Return the client context for Roblox's servers: OS trust store, TLS 1.2+, hostname check."""
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.set_alpn_protocols(["http/1.1"])
    return context


def resolve_system(
    proxy_port: int, getproxies: Callable[[], dict[str, str]] | None = None
) -> Transport:
    """Return the system's HTTPS proxy as a transport, or direct if there is none.

    A system proxy that points at Verdra's own listener is ignored (it would loop).
    """
    proxies = (getproxies or urllib.request.getproxies)()
    url = proxies.get("https") or proxies.get("all") or ""
    if not url:
        return Transport("direct")
    parts = urlsplit(url if "://" in url else f"http://{url}")
    host = parts.hostname or ""
    port = parts.port or (1080 if parts.scheme.startswith("socks") else 8080)
    if not host or (_is_loopback(host) and port == proxy_port):
        return Transport("direct")
    kind: Kind = "socks5" if parts.scheme.startswith("socks") else "http"
    return Transport(kind, host, port, parts.username or "", parts.password or "")


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def open_tunnel(transport: Transport, host: str, port: int, proxy_port: int = 0) -> Streams:
    """Return a raw TCP connection to host:port through the transport."""
    if transport.kind == "system":
        transport = resolve_system(proxy_port)
    if transport.kind == "direct":
        return await asyncio.open_connection(host, port)
    reader, writer = await asyncio.open_connection(transport.host, transport.port)
    try:
        if transport.kind == "http":
            await _http_connect(reader, writer, transport, host, port)
        else:
            await _socks5_connect(reader, writer, transport, host, port)
    except BaseException:
        writer.close()
        raise
    return reader, writer


async def open_tls(
    transport: Transport,
    host: str,
    port: int,
    *,
    context: ssl.SSLContext | None = None,
    address: str | None = None,
    proxy_port: int = 0,
) -> Streams:
    """Return a verified TLS connection to host:port through the transport.

    `address` connects to a pre-resolved address while SNI and the hostname check still use
    `host`. A certificate that doesn't verify raises UpstreamVerificationError.
    """
    context = context or tls_context()
    reader, writer = await open_tunnel(transport, address or host, port, proxy_port)
    try:
        await writer.start_tls(context, server_hostname=host)
    except ssl.SSLCertVerificationError as error:
        writer.close()
        raise UpstreamVerificationError(host, error.verify_message or str(error)) from error
    except BaseException:
        writer.close()
        raise
    return reader, writer


async def _http_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    transport: Transport,
    host: str,
    port: int,
) -> None:
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"]
    if transport.username:
        token = base64.b64encode(f"{transport.username}:{transport.password}".encode()).decode()
        lines.append(f"Proxy-Authorization: Basic {token}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    if len(head) > _MAX_HEAD_BYTES:
        raise UpstreamError("the HTTP proxy's reply is too long")
    status = head.split(b"\r\n", 1)[0].split(b" ")
    if len(status) < 2 or not status[0].startswith(b"HTTP/1.") or not status[1].startswith(b"2"):
        raise UpstreamError(
            f"the HTTP proxy refused the connection: {head.split(b'\r\n', 1)[0].decode('latin-1')}"
        )


async def _socks5_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    transport: Transport,
    host: str,
    port: int,
) -> None:
    methods = b"\x00\x02" if transport.username else b"\x00"
    writer.write(bytes([_SOCKS_VERSION, len(methods)]) + methods)
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != _SOCKS_VERSION or method == 0xFF:
        raise UpstreamError("the SOCKS5 proxy accepts none of the offered methods")
    if method == 0x02:
        user = transport.username.encode()
        password = transport.password.encode()
        if len(user) > 255 or len(password) > 255:
            raise UpstreamError("the SOCKS5 username or password is too long")
        writer.write(bytes([1, len(user)]) + user + bytes([len(password)]) + password)
        await writer.drain()
        _, status = await reader.readexactly(2)
        if status != 0:
            raise UpstreamError("the SOCKS5 proxy refused the username or password")
    elif method != 0x00:
        raise UpstreamError("the SOCKS5 proxy chose a method Verdra doesn't offer")
    try:
        address = ipaddress.ip_address(host)
        target = (b"\x01" if address.version == 4 else b"\x04") + address.packed
    except ValueError:
        name = host.encode("idna")
        target = b"\x03" + bytes([len(name)]) + name
    writer.write(bytes([_SOCKS_VERSION, 1, 0]) + target + struct.pack("!H", port))
    await writer.drain()
    version, reply, _, kind = await reader.readexactly(4)
    if version != _SOCKS_VERSION or reply != 0:
        raise UpstreamError(f"the SOCKS5 proxy couldn't connect (reply {reply})")
    length = {1: 4, 4: 16}.get(kind)
    if length is None:
        (length,) = await reader.readexactly(1)
    await reader.readexactly(length + 2)
