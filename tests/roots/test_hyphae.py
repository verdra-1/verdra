# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-11: interception (TLS termination, h11, the symbiont pipeline, limits, 502)."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import socket
import ssl
import struct
import zlib
from collections.abc import Awaitable, Callable
from compression import zstd
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import h11
import pytest

from tests.roots.test_mycelium import tls_server_context
from tests.roots.test_taproot import client_context
from verdra.bark import resin, veil
from verdra.roots import hyphae, mycelium, taproot

HOST = "assetdelivery.roblox.com"
#: A fake-server response that closes the connection without answering.
CLOSE = b"<close>"
NOW = datetime.now(UTC)


@dataclass
class Received:
    method: bytes
    target: bytes
    headers: list[tuple[bytes, bytes]]
    body: bytes


@dataclass
class FakeServer:
    """A TLS server standing in for Roblox. It answers each path with fixed raw bytes."""

    tmp_path: Path
    responses: dict[bytes, bytes]
    host: str = HOST
    received: list[Received] = field(default_factory=list[Received])
    connections: int = 0

    async def start(self) -> tuple[int, resin.Authority]:
        context, authority = tls_server_context(self.tmp_path, self.host)

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            self.connections += 1
            try:
                while True:
                    head = await reader.readuntil(b"\r\n\r\n")
                    lines = head[:-4].split(b"\r\n")
                    method, target, _version = lines[0].split(b" ")
                    headers = [
                        (name, value.strip())
                        for name, _, value in (line.partition(b":") for line in lines[1:])
                    ]
                    length = next((int(v) for n, v in headers if n.lower() == b"content-length"), 0)
                    body = await reader.readexactly(length) if length else b""
                    self.received.append(Received(method, target, headers, body))
                    response = self.responses[target]
                    if response == CLOSE:
                        break
                    writer.write(response)
                    await writer.drain()
                    if b"Connection: close" in response:
                        break
            except asyncio.IncompleteReadError, ConnectionError, ssl.SSLError:
                pass
            writer.close()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
        return int(self.server.sockets[0].getsockname()[1]), authority


class Recorder:
    """A test symbiont that records what it sees and can change or break things."""

    name = "recorder"

    def __init__(
        self,
        *,
        wants_body: bool = False,
        on_request: Callable[[hyphae.Request], object] | None = None,
        on_response: Callable[[hyphae.Response], object] | None = None,
    ) -> None:
        self.wants_body = wants_body
        self.request_hook = on_request
        self.response_hook = on_response
        self.requests: list[hyphae.Request] = []
        self.responses: list[hyphae.Response] = []

    def wants_request_body(self, request: hyphae.Request) -> bool:
        return self.wants_body

    def on_request(self, request: hyphae.Request) -> hyphae.Request | hyphae.Response | None:
        self.requests.append(request)
        return self.request_hook(request) if self.request_hook else None  # type: ignore[return-value]

    def wants_response_body(self, request: hyphae.Request, response: hyphae.Response) -> bool:
        return self.wants_body

    def on_response(
        self, request: hyphae.Request, response: hyphae.Response
    ) -> hyphae.Response | None:
        self.responses.append(response)
        return self.response_hook(response) if self.response_hook else None  # type: ignore[return-value]


class Proxy:
    """Mycelium intercepting the FakeServer's host, upstream to it on 127.0.0.1."""

    def __init__(
        self,
        server: FakeServer,
        pipeline: hyphae.Pipeline | None = None,
        *,
        upstream_context: Callable[[resin.Authority], ssl.SSLContext] | None = client_context,
        max_body: int = hyphae.MAX_BUFFERED_BODY,
    ) -> None:
        self.server = server
        self.pipeline = pipeline or hyphae.Pipeline()
        self.upstream_context = upstream_context
        self.max_body = max_body
        self.authority = resin.create_authority(NOW)
        self.failures: list[tuple[str, str]] = []
        #: What the status heard: ("refused", text) per failed handshake, ("request", host).
        self.reports: list[tuple[str, str]] = []

    async def __aenter__(self) -> Proxy:
        server_port, server_authority = await self.server.start()
        context = self.upstream_context(server_authority) if self.upstream_context else None

        async def open_upstream(host: str, port: int) -> hyphae.Streams:
            return await taproot.open_tls(
                taproot.Transport("direct"), host, server_port, context=context, address="127.0.0.1"
            )

        interception = hyphae.Interception(
            hyphae.LeafContexts(self.authority),
            lambda: {self.server.host},
            open_upstream,
            lambda: self.pipeline,
            on_verification_failure=lambda host, reason: self.failures.append((host, reason)),
            on_handshake_failure=lambda _host, text: self.reports.append(("refused", text)),
            on_request=lambda host: self.reports.append(("request", host)),
            idle_timeout=5,
            max_body=self.max_body,
        )
        self.mycelium = mycelium.Mycelium(
            0, asyncio.open_connection, idle_timeout=5, interceptor=interception
        )
        self.port = await self.mycelium.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.mycelium.stop()
        self.server.server.close()

    async def connect(self, alpn: list[str] | None = None) -> Client:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        host = self.server.host
        writer.write(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        await writer.drain()
        assert await reader.readuntil(b"\r\n\r\n") == b"HTTP/1.1 200 Connection established\r\n\r\n"
        context = ssl.create_default_context(
            cadata=resin.certificate_pem(self.authority.certificate).decode()
        )
        if alpn is not None:
            context.set_alpn_protocols(alpn)
        await writer.start_tls(context, server_hostname=host)
        return Client(reader, writer)


class Client:
    """Sends raw requests through the proxy and returns each response's raw bytes."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.conn = h11.Connection(h11.CLIENT)

    async def send(self, raw: bytes, *, method: bytes = b"GET") -> tuple[bytes, list[object]]:
        if self.conn.our_state is h11.DONE:
            self.conn.start_next_cycle()
        # Let h11 track the request so it knows how to frame the response.
        self.conn.send(h11.Request(method=method, target=b"/", headers=[(b"Host", HOST.encode())]))
        self.conn.send(h11.EndOfMessage())
        self.writer.write(raw)
        await self.writer.drain()
        data = bytearray()
        events: list[object] = []
        while True:
            event = self.conn.next_event()
            if event is h11.NEED_DATA:
                chunk = await self.reader.read(65536)
                data += chunk
                self.conn.receive_data(chunk)
                continue
            events.append(event)
            if isinstance(event, h11.EndOfMessage | h11.ConnectionClosed):
                return bytes(data), events


def run[T](coroutine: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine(), timeout=30))


def get(path: bytes, extra: bytes = b"") -> bytes:
    return b"GET " + path + b" HTTP/1.1\r\nHost: " + HOST.encode() + b"\r\n" + extra + b"\r\n"


def body_of(events: list[object]) -> bytes:
    return b"".join(e.data for e in events if isinstance(e, h11.Data))


PLAIN = (
    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nX-Mixed-Case: Yes\r\n"
    b"Content-Length: 5\r\n\r\nhello"
)
GZIPPED_BODY = gzip.compress(b'{"name": "original"}')
GZIPPED = (
    b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Type: application/json\r\n"
    b"Content-Length: " + str(len(GZIPPED_BODY)).encode() + b"\r\n\r\n" + GZIPPED_BODY
)
CHUNKED = (
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    b"5\r\nhello\r\n1a\r\n" + b"x" * 26 + b"\r\n0\r\nX-Trailer: done\r\n\r\n"
)
LARGE = b"HTTP/1.1 200 OK\r\nContent-Length: 300000\r\n\r\n" + b"y" * 300000


def test_unmodified_responses_arrive_byte_identical_on_one_connection(tmp_path: Path) -> None:
    server = FakeServer(
        tmp_path,
        {b"/plain": PLAIN, b"/gzip": GZIPPED, b"/chunked": CHUNKED, b"/large": LARGE},
    )
    recorder = Recorder()

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline([recorder], [recorder])) as proxy:
            client = await proxy.connect()
            for path, expected in (
                (b"/plain", PLAIN),
                (b"/gzip", GZIPPED),
                (b"/chunked", CHUNKED),
                (b"/large", LARGE),
                (b"/plain", PLAIN),
            ):
                raw, _events = await client.send(get(path, b"Cookie: a=b\r\n"))
                assert raw == expected
        assert server.connections == 1  # keep-alive upstream too
        assert [r.target for r in server.received][:2] == [b"/plain", b"/gzip"]
        assert (b"Cookie", b"a=b") in server.received[0].headers
        assert recorder.responses[0].body is None  # nobody asked for the body

    run(body)


@pytest.mark.spec("S-11", 4)
def test_a_symbiont_that_raises_does_not_fail_the_request(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def explode(_message: object) -> object:
        raise ValueError("bad cookie Cookie: secret-value")

    server = FakeServer(tmp_path, {b"/gzip": GZIPPED})
    broken = Recorder(wants_body=True, on_request=explode, on_response=explode)
    after = Recorder(wants_body=True)

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline([broken, after], [broken, after])) as proxy:
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/gzip"))
            assert raw == GZIPPED

    with caplog.at_level(logging.WARNING, logger="verdra.roots.hyphae"):
        run(body)
    assert after.responses[0].body == b'{"name": "original"}'  # the next symbiont still ran
    failures = [
        r.getMessage() for r in caplog.records if "Part of a feature failed" in r.getMessage()
    ]
    assert len(failures) == 2
    assert all("secret-value" not in line and veil.REDACTED in line for line in failures)


def test_a_modified_response_is_sent_decoded_with_its_length(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {b"/gzip": GZIPPED})
    rewrite = Recorder(
        wants_body=True,
        on_response=lambda r: replace(r, body=r.body.replace(b"original", b"changed")),  # type: ignore[union-attr, arg-type]
    )

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline((), [rewrite])) as proxy:
            client = await proxy.connect()
            raw, events = await client.send(get(b"/gzip"))
            head = raw.split(b"\r\n\r\n")[0]
            assert b"Content-Encoding" not in head
            assert b"Content-Length: 19" in head
            assert b"Content-Type: application/json" in head
            assert body_of(events) == b'{"name": "changed"}'

    run(body)


def test_a_modified_response_can_be_sent_as_zstd(tmp_path: Path) -> None:
    """The asset CDN answers pictures with Content-Encoding: zstd; a replacement can be too."""
    server = FakeServer(tmp_path, {b"/gzip": GZIPPED})
    rewrite = Recorder(
        wants_body=True,
        on_response=lambda r: replace(r, body=b"replaced" * 100, coding="zstd"),  # type: ignore[arg-type]
    )

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline((), [rewrite])) as proxy:
            client = await proxy.connect()
            raw, events = await client.send(get(b"/gzip"))
            head = raw.split(b"\r\n\r\n")[0]
            sent = body_of(events)
            assert head.count(b"Content-Encoding") == 1  # the upstream's gzip is gone
            assert b"Content-Encoding: zstd" in head
            assert f"Content-Length: {len(sent)}".encode() in head
            assert b"Content-Type: application/json" in head
            assert sent.startswith(b"\x28\xb5\x2f\xfd")
            assert zstd.decompress(sent) == b"replaced" * 100

    run(body)


def test_request_symbionts_can_change_or_answer_a_request(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {b"/plain": PLAIN})

    def change(request: hyphae.Request) -> object:
        if request.target == b"/local":
            return hyphae.Response(200, ((b"Content-Type", b"text/plain"),), b"OK", b"served")
        return replace(request, body=b"new body")

    symbiont = Recorder(wants_body=True, on_request=change)

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline([symbiont])) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(get(b"/local"))
            assert body_of(events) == b"served"
            post = b"POST /plain HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\n\r\nold"
            raw, _ = await client.send(post, method=b"POST")
            assert raw == PLAIN
        assert [r.target for r in server.received] == [b"/plain"]  # /local never went upstream
        assert server.received[0].body == b"new body"
        assert (b"Content-Length", b"8") in server.received[0].headers
        assert symbiont.requests[1].body == b"old"

    run(body)


@pytest.mark.spec("S-11", 7)
def test_a_body_over_the_limit_is_streamed_unbuffered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeServer(tmp_path, {b"/large": LARGE})
    reader = Recorder(wants_body=True, on_response=lambda r: replace(r, body=b"never"))
    plain = Recorder()

    async def body() -> None:
        async with Proxy(server, hyphae.Pipeline((), [reader, plain]), max_body=100_000) as proxy:
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/large"))
            assert raw == LARGE

    with caplog.at_level(logging.INFO, logger="verdra.roots.hyphae"):
        run(body)
    assert reader.responses == []  # skipped: it needed a body that was too large
    assert plain.responses[0].body is None
    assert any("was over 64 MB" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("S-11", 3)
def test_an_upstream_that_fails_verification_gives_502(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # No test context: the real OS trust store, which doesn't know the fake server's own CA.
    server = FakeServer(tmp_path, {b"/plain": PLAIN})

    async def body() -> list[tuple[str, str]]:
        async with Proxy(server, upstream_context=None) as proxy:
            client = await proxy.connect()
            raw, events = await client.send(get(b"/plain"))
            assert raw.startswith(b"HTTP/1.1 502 Bad Gateway\r\n")
            assert isinstance(events[0], h11.Response)
            assert server.received == []
            return proxy.failures

    with caplog.at_level(logging.WARNING, logger="verdra.roots.hyphae"):
        failures = run(body)
    assert [host for host, _reason in failures] == [HOST]
    assert any(
        f"couldn't be verified ({HOST}). That request was blocked." in r.getMessage()
        for r in caplog.records
    )


def test_an_unreachable_upstream_gives_502(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        async with Proxy(server) as proxy:
            proxy.server.server.close()
            await proxy.server.server.wait_closed()
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/plain"))
            assert raw.startswith(b"HTTP/1.1 502 Bad Gateway\r\n")
        assert proxy.failures == []

    run(body)


def test_a_malformed_request_gets_400(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            client.writer.write(b"NOT HTTP AT ALL\r\n\r\n")
            await client.writer.drain()
            assert (await client.reader.read()).startswith(b"HTTP/1.1 400 ")

    run(body)


def test_hosts_outside_the_set_are_not_intercepted() -> None:
    interception = hyphae.Interception(
        hyphae.LeafContexts(resin.create_authority(NOW)),
        lambda: frozenset({HOST}),
        taproot.open_tls,  # type: ignore[arg-type]
    )
    assert interception.wants("AssetDelivery.Roblox.com", 443)
    assert not interception.wants("www.roblox.com", 443)


def test_leaves_are_reused_then_renewed_before_they_expire() -> None:
    clock = [NOW]
    leaves = hyphae.LeafContexts(resin.create_authority(NOW), lambda: clock[0])
    first = leaves.context_for(HOST)
    assert leaves.context_for(HOST) is first
    clock[0] = NOW + resin.LEAF_VALIDITY - timedelta(minutes=30)
    assert leaves.context_for(HOST) is not first


@pytest.mark.parametrize(
    ("coding", "encoded"),
    [
        (b"gzip", gzip.compress(b"data")),
        (b"deflate", zlib.compress(b"data")),
        (b"deflate", zlib.compress(b"data", wbits=-15)),
        (b"zstd", zstd.compress(b"data")),
        (b"identity", b"data"),
        (b"gzip, identity", gzip.compress(b"data")),
    ],
)
def test_supported_encodings_decode(coding: bytes, encoded: bytes) -> None:
    decoded = hyphae.decode(((b"Content-Encoding", coding),), encoded)
    assert decoded.body == b"data"
    assert decoded.coding == ("" if coding == b"identity" else coding.decode())


@pytest.mark.parametrize(
    ("coding", "encoded", "problem"),
    [
        (b"br", b"data", "compressed as br, which Verdra can't read"),
        (b"gzip", b"not gzip", "damaged gzip data"),
        (b"gzip", gzip.compress(b"data")[:-3], "damaged gzip data"),  # cut short
        (b"zstd", zstd.compress(b"data")[:-2], "damaged zstd data"),
        (
            b"gzip",
            gzip.compress(b"d" * 100_000),
            "gzip data that would be too large once decompressed",
        ),
        (
            b"zstd",
            zstd.compress(b"d" * 10_000),
            "zstd data that would be too large once decompressed",
        ),
    ],
)
def test_unsupported_broken_or_oversized_encodings_are_left_alone(
    coding: bytes, encoded: bytes, problem: str
) -> None:
    decoded = hyphae.decode(((b"Content-Encoding", coding),), encoded)
    assert decoded.body is None
    assert decoded.problem == problem


def test_decoding_keeps_within_the_ratio_and_the_limit() -> None:
    """Plan 10.7: at most 100 times the received size, and never over the buffer limit."""
    gz = ((b"Content-Encoding", b"gzip"),)
    exactly = gzip.compress(b"x" * 500)
    assert hyphae.decode(gz, exactly).body == b"x" * 500  # 500 bytes from fewer: within 100:1
    big = gzip.compress(json.dumps(list(range(2000))).encode())  # about 4:1
    assert hyphae.decode(gz, big, limit=100).body is None
    assert hyphae.decode(gz, big).body is not None
    # Several gzip members and zstd frames, one after another, are one body (RFC 1952, 8878).
    assert hyphae.decode(gz, gzip.compress(b"ab") + gzip.compress(b"cd")).body == b"abcd"
    zs = ((b"Content-Encoding", b"zstd"),)
    assert hyphae.decode(zs, zstd.compress(b"ab") + zstd.compress(b"cd")).body == b"abcd"
    # An uncompressed body has no ratio to keep.
    assert hyphae.decode((), b"").body == b""


def test_an_upstream_that_closes_is_reopened_for_the_next_request(tmp_path: Path) -> None:
    closing = PLAIN.replace(b"Content-Length: 5", b"Connection: close\r\nContent-Length: 5")
    server = FakeServer(tmp_path, {b"/closing": closing, b"/plain": PLAIN})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/closing"))
            assert raw == closing
            # The client's connection closes with it (h11 passes Connection: close on).
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/plain"))
            assert raw == PLAIN
        assert server.connections == 2

    run(body)


def test_an_upstream_that_closes_without_answering_gives_502(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {b"/gone": CLOSE})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            raw, _ = await client.send(get(b"/gone"))
            assert raw.startswith(b"HTTP/1.1 502 Bad Gateway\r\n")

    run(body)


def test_expect_100_continue_is_answered_before_the_body(tmp_path: Path) -> None:
    server = FakeServer(tmp_path, {b"/plain": PLAIN})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            client.writer.write(
                b"POST /plain HTTP/1.1\r\nHost: x\r\nExpect: 100-continue\r\n"
                b"Content-Length: 4\r\n\r\n"
            )
            await client.writer.drain()
            # The body is sent only after the 100 arrives, as a waiting client does.
            assert await client.reader.readuntil(b"\r\n\r\n") == b"HTTP/1.1 100 Continue\r\n\r\n"
            client.writer.write(b"data")
            await client.writer.drain()
            rest = await client.reader.readuntil(b"hello")
        assert rest.endswith(PLAIN)
        assert server.received[0].body == b"data"

    run(body)


def test_a_client_that_leaves_mid_response_is_not_logged_as_an_upstream_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Roblox drops a video segment it no longer needs (seen on sc5.rbxcdn.com, Stage 2).
    size = 32 * 1024 * 1024
    large = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(size).encode() + b"\r\n\r\n" + b"v" * size
    server = FakeServer(tmp_path, {b"/segment": large})

    def closed() -> list[str]:
        return [r.getMessage() for r in caplog.records if "Closed a connection" in r.getMessage()]

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            client.writer.write(get(b"/segment"))
            await client.writer.drain()
            await client.reader.readuntil(b"\r\n\r\n")
            client.writer.transport.abort()
            while not closed():
                await asyncio.sleep(0.01)

    with caplog.at_level(logging.DEBUG, logger="verdra.roots.hyphae"):
        run(body)
    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if m.startswith("Upstream")], messages
    assert any(m.startswith(f"The client left {HOST} mid-response") for m in messages), messages
    assert closed() == [f"Closed a connection to {HOST}: the client left"]


#: The protected path under every spelling a client or a rule could use (plan 16.2).
PROTECTED_SPELLINGS = (
    b"/validate-machine",
    b"/VALIDATE-MACHINE",
    b"//validate-machine",
    b"/%76alidate-machine",
    b"/%2576alidate-machine",
    b"/x/../validate-machine",
    b"/./validate-machine/",
    b"/validate-machine;v=1",
    b"/validate-machine?a=1",
    b"/rm3-evidence-filter/v1/upload-screenshot",
)


@pytest.mark.spec("S-11", 11)
def test_protected_endpoints_are_never_touched(tmp_path: Path) -> None:
    def changing(request: hyphae.Request) -> object:
        return replace(request, body=b"changed")

    def answering(request: hyphae.Request) -> object:
        return hyphae.Response(200, ((b"Content-Length", b"6"),), b"OK", b"forged")

    changer = Recorder(
        wants_body=True,
        on_request=changing,
        on_response=lambda response: replace(response, body=b"changed"),
    )
    answerer = Recorder(on_request=answering)
    server = FakeServer(tmp_path, dict.fromkeys(PROTECTED_SPELLINGS, PLAIN), host="apis.roblox.com")
    pipeline = hyphae.Pipeline(request=[changer, answerer], response=[changer])
    sent = b"POST {target} HTTP/1.1\r\nHost: apis.roblox.com\r\nContent-Length: 4\r\n\r\n"

    async def body() -> None:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            for target in PROTECTED_SPELLINGS:
                raw, _ = await client.send(sent.replace(b"{target}", target) + b"data")
                assert raw == PLAIN, target

    run(body)
    assert [(r.target, r.body) for r in server.received] == [
        (target, b"data") for target in PROTECTED_SPELLINGS
    ]
    assert (changer.requests, changer.responses, answerer.requests) == ([], [], [])


def test_a_handshake_roblox_refuses_is_logged_once_per_host_with_the_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """15 October 2026: the release ZIP's handshakes all failed and its log said nothing."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})
    stranger = resin.create_authority(NOW)  # a CA the client trusts instead of Verdra's

    async def refused(proxy: Proxy) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        host = proxy.server.host
        writer.write(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        context = ssl.create_default_context(
            cadata=resin.certificate_pem(stranger.certificate).decode()
        )
        with pytest.raises(ssl.SSLError):
            await writer.start_tls(context, server_hostname=host)
        writer.close()

    reports: list[tuple[str, str]] = []

    async def body() -> None:
        async with Proxy(server) as proxy:
            await refused(proxy)
            await refused(proxy)
            await asyncio.sleep(0.2)  # the proxy side finishes its handshake
            reports.extend(proxy.reports)

    run(body)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    # The status hears of every one, with the same plain text, and of no request.
    assert reports == [("refused", warnings[0])] * 2
    assert warnings[0].startswith(
        f"Roblox couldn't open a secure connection to Verdra for {server.host} ("
    )
    assert any("failed again" in r.getMessage() for r in caplog.records)


def test_each_decrypted_request_is_reported_to_the_status(tmp_path: Path) -> None:
    """15 October 2026: the status must know whether Roblox's requests reach Verdra at all."""
    server = FakeServer(tmp_path, {b"/plain": PLAIN})
    reports: list[tuple[str, str]] = []

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            assert proxy.reports == []  # a handshake alone isn't a request
            await client.send(get(b"/plain"))
            await client.send(get(b"/plain"))
            reports.extend(proxy.reports)

    run(body)
    assert reports == [("request", server.host)] * 2


def test_a_connection_reset_before_its_first_request_is_a_warning_naming_the_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Retest (g), 16 October 2026: one "A proxy connection ended: ConnectionResetError" at
    Debug, with no host, was all the log had; it couldn't say whether assets broke there."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})

    async def reset(proxy: Proxy) -> None:
        client = await proxy.connect()
        raw = client.writer.get_extra_info("socket")
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        client.writer.transport.abort()  # a reset, not a clean close

    async def body() -> None:
        async with Proxy(server) as proxy:
            await reset(proxy)
            await asyncio.sleep(0.3)
            await reset(proxy)
            await asyncio.sleep(0.3)

    run(body)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        f"A secure connection from Roblox to {server.host} ended before Roblox asked for "
        "anything (ConnectionResetError)."
    ]
    assert any("ended again before its first request" in r.getMessage() for r in caplog.records)


def test_a_clean_close_before_any_request_is_only_a_debug_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect()
            client.writer.close()
            await asyncio.sleep(0.3)

    run(body)
    assert not [
        r for r in caplog.records if r.levelno >= logging.WARNING and r.name.startswith("verdra")
    ]
    assert any(
        f"closed a secure connection to {server.host} before its first request" in r.getMessage()
        for r in caplog.records
    )


def debug_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "verdra.roots.hyphae"]


def closes(lines: list[str]) -> list[str]:
    return [line for line in lines if "before its first request" in line]


@pytest.mark.spec("S-11", 13)
@pytest.mark.parametrize(
    ("offered", "chosen"),
    [(["h2", "http/1.1"], "http/1.1"), (["h2"], "none"), (None, "none")],
)
def test_detailed_logging_shows_the_alpn_roblox_offered_and_what_verdra_chose(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    offered: list[str] | None,
    chosen: str,
) -> None:
    """Retest (g), 21 October 2026: Roblox closed every assetdelivery connection after the
    handshake, and the log couldn't say which protocol it wanted or how it closed."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect(offered)
            client.writer.close()  # asyncio sends a TLS close_notify first
            await asyncio.sleep(0.3)

    run(body)
    lines = debug_lines(caplog)
    handshake = next(line for line in lines if line.startswith("TLS with Roblox for "))
    alpn = ", ".join(offered) if offered is not None else "no ALPN"
    assert handshake.startswith(f"TLS with Roblox for {server.host}: TLSv1.3, TLS_")
    assert f"ALPN chosen: {chosen}. Roblox offered TLS 1.3, TLS 1.2; ALPN {alpn}; groups " in (
        handshake
    )
    assert closes(lines) == [
        f"Roblox closed a secure connection to {server.host} before its first request "
        "(Roblox sent a TLS close_notify (an orderly close))"
    ]
    library = next(line for line in lines if line.startswith("Verdra's TLS server for Roblox: "))
    assert ssl.OPENSSL_VERSION in library
    assert "source run" in library
    leaf = next(line for line in lines if line.startswith("Verdra's certificate for "))
    assert leaf.startswith(
        f"Verdra's certificate for {server.host}: key ECDSA secp256r1, names {server.host}, valid "
    )
    assert leaf.endswith("chain sent: this certificate alone")


@pytest.mark.spec("S-11", 13)
def test_a_plain_tcp_close_after_the_handshake_is_told_apart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect(["http/1.1"])
            await asyncio.sleep(0.1)  # read Verdra's session tickets, or the close is a reset
            client.writer.transport.abort()  # no close_notify: the socket just closes
            await asyncio.sleep(0.3)

    run(body)
    assert closes(debug_lines(caplog)) == [
        f"Roblox closed a secure connection to {server.host} before its first request "
        "(the connection ended without a TLS close_notify (a plain TCP close))"
    ]


@pytest.mark.spec("S-11", 13)
def test_an_alert_that_ends_a_handshake_is_named_with_what_roblox_offered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})
    stranger = resin.create_authority(NOW)

    def refuse(port: int) -> None:
        # A blocking client: unlike asyncio's, it sends its alert before it closes.
        host = server.host
        with socket.create_connection(("127.0.0.1", port)) as raw:
            raw.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
            assert raw.recv(4096).startswith(b"HTTP/1.1 200")
            context = ssl.create_default_context(
                cadata=resin.certificate_pem(stranger.certificate).decode()
            )
            context.set_alpn_protocols(["h2"])
            with pytest.raises(ssl.SSLError):
                context.wrap_socket(raw, server_hostname=host)

    async def body() -> None:
        async with Proxy(server) as proxy:
            await asyncio.to_thread(refuse, proxy.port)
            await asyncio.sleep(0.3)

    run(body)
    alerts = [line for line in debug_lines(caplog) if line.startswith("TLS alert for ")]
    assert len(alerts) == 1
    assert alerts[0].startswith(f"TLS alert for {server.host}: Roblox sent unknown_ca. ")
    assert "ALPN h2;" in alerts[0]


@pytest.mark.spec("S-11", 13)
def test_without_detailed_logging_nothing_is_traced(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="verdra.roots")
    server = FakeServer(tmp_path, {})
    contexts: list[ssl.SSLContext] = []

    async def body() -> None:
        async with Proxy(server) as proxy:
            client = await proxy.connect(["h2", "http/1.1"])
            client.writer.close()
            await asyncio.sleep(0.3)
            interception = proxy.mycelium.interceptor
            assert isinstance(interception, hyphae.Interception)
            contexts.append(interception.leaves.context_for(server.host))
            assert not interception.leaves.tracer.traces

    run(body)
    assert getattr(contexts[0], "_msg_callback", None) is None
    assert debug_lines(caplog) == []


def test_the_close_reason_names_each_alert_roblox_sent() -> None:
    trace = hyphae.TlsTrace()
    assert "plain TCP close" in trace.close_reason()
    trace.alerts.append(("write", "close_notify"))  # Verdra's own close doesn't count
    assert "plain TCP close" in trace.close_reason()
    trace.alerts.append(("read", "bad_certificate"))
    assert trace.close_reason() == "Roblox sent the TLS alert bad_certificate"
    assert hyphae.alert_name(0) == "close_notify"
    assert hyphae.alert_name(48) == "unknown_ca"
    assert hyphae.alert_name(250) == "alert 250"


def test_a_broken_hello_never_breaks_the_hook() -> None:
    tracer = hyphae.TlsTracer()
    connection = hyphae.TlsTrace()  # any object that takes a weak reference
    tracer(connection, "read", None, 22, 1, b"\x01\x00")  # cut short
    tracer(connection, "read", None, 21, 0, b"\x02\x28")
    assert tracer.trace(connection) is None
    assert tracer.trace(42) is None  # no weak reference to an int
