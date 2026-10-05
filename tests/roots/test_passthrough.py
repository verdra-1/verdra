# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-11 test 1: 1,000 replayed responses pass through byte-identical (plan 12.1)."""

from __future__ import annotations

import asyncio
import ssl
import warnings
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from tests.support.client import FakeClient
from tools import fake_roblox
from verdra.bark import resin
from verdra.roots import hyphae, mycelium, taproot

NOW = datetime.now(UTC)
REPLAYS = fake_roblox.responses(1000)


def run[T](coroutine: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine(), timeout=120))


Diagnose = Callable[[hyphae.LeafContexts, hyphae.Opener], hyphae.Interception]


async def replay_all(intercepted: bool, diagnose: Diagnose | None = None) -> fake_roblox.FakeRoblox:
    """Send every replay through Verdra's proxy, one keep-alive connection per host.

    With `diagnose`, that function builds the interception (roots/litmus, spec S-11 test 9).
    """
    authority = resin.create_authority(NOW)
    async with fake_roblox.FakeRoblox(REPLAYS) as server:

        async def open_upstream(host: str, _port: int) -> hyphae.Streams:
            return await taproot.open_tls(
                taproot.Transport("direct"),
                host,
                server.port,
                context=server.client_context(),
                address="127.0.0.1",
            )

        interception = (
            diagnose(hyphae.LeafContexts(authority), open_upstream)
            if diagnose is not None
            else hyphae.Interception(
                hyphae.LeafContexts(authority),
                lambda: frozenset(fake_roblox.HOSTS) if intercepted else frozenset(),
                open_upstream,
            )
        )
        proxy = mycelium.Mycelium(
            0,
            lambda _host, _port: asyncio.open_connection("127.0.0.1", server.port),
            interceptor=interception,
        )
        port = await proxy.start()
        # Intercepted: the client trusts only Verdra's CA, so TLS must end at Verdra. Tunneled:
        # it trusts only the server's test CA, so its own handshake must reach the server.
        if intercepted:
            context = ssl.create_default_context(
                cadata=resin.certificate_pem(authority.certificate).decode()
            )
        else:
            context = server.client_context()
        by_host: dict[str, list[fake_roblox.Replay]] = defaultdict(list)
        for replay in REPLAYS:
            by_host[replay.host].append(replay)

        async def one_host(host: str, replays: list[fake_roblox.Replay]) -> list[int]:
            client = await FakeClient.connect(port, host, context)
            different = [
                replay.index
                for replay in replays
                if await client.exchange(replay.request()) != replay.raw
            ]
            await client.close()
            return different

        try:
            results = await asyncio.gather(*(one_host(h, r) for h, r in by_host.items()))
        finally:
            await proxy.stop()
        assert [index for result in results for index in result] == []
        return server


@pytest.mark.spec("S-11", 1)
@pytest.mark.parametrize("intercepted", [True, False], ids=["intercepted", "tunneled"])
def test_1000_replayed_responses_pass_through_byte_identical(intercepted: bool) -> None:
    server = run(lambda: replay_all(intercepted))
    assert len(server.requests) == 1000
    assert set(server.sni) <= set(fake_roblox.HOSTS)


def test_the_replays_cover_every_fixture_encoding_and_framing() -> None:
    assert len({replay.raw for replay in REPLAYS}) == 1000
    assert {replay.fixture.name for replay in REPLAYS} == {f.name for f in fake_roblox.load()}
    with_body = [replay for replay in REPLAYS if replay.fixture.has_body]
    assert {(r.encoding, r.framing) for r in with_body} == {
        (encoding, framing)
        for encoding in fake_roblox.ENCODINGS
        for framing in fake_roblox.FRAMINGS
    }


def test_every_fixture_states_its_origin_and_a_plan_host() -> None:
    for fixture in fake_roblox.load():
        assert fixture.origin.startswith("hand-written") or fixture.origin.startswith("recorded")
        assert "no real user data" in fixture.origin or fixture.origin.startswith("recorded")
        assert fixture.host in fake_roblox.HOSTS


@pytest.mark.parametrize("mode", ["self_signed", "wrong_host", "tls11"])
def test_the_negative_modes_are_refused_by_verdras_upstream_policy(
    mode: fake_roblox.Mode,
) -> None:
    async def body() -> None:
        async with fake_roblox.FakeRoblox(REPLAYS[:1], mode=mode) as server:
            # The upstream policy (taproot.tls_context) trusting the server's own test CA.
            context = server.client_context()
            # A refused handshake surfaces as an SSL error or a reset connection (both OSError).
            with pytest.raises(OSError):
                await taproot.open_tls(
                    taproot.Transport("direct"),
                    fake_roblox.HOSTS[0],
                    server.port,
                    context=context,
                    address="127.0.0.1",
                )

    run(body)


def test_the_tls11_mode_really_speaks_tls11() -> None:
    """The control for the tls11 case above: a client that allows TLS 1.1 gets through."""

    async def body() -> str | None:
        async with fake_roblox.FakeRoblox(REPLAYS[:1], mode="tls11") as server:
            context = ssl.create_default_context(cadata=server.ca_pem)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                context.minimum_version = ssl.TLSVersion.TLSv1
                context.maximum_version = ssl.TLSVersion.TLSv1_1
            context.set_ciphers("DEFAULT:@SECLEVEL=0")
            _reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.port, ssl=context, server_hostname=fake_roblox.HOSTS[0]
            )
            version = writer.get_extra_info("ssl_object").version()
            writer.close()
            return version

    assert run(body) == "TLSv1.1"


def test_an_unknown_request_gets_404() -> None:
    async def body() -> bytes:
        async with fake_roblox.FakeRoblox(REPLAYS[:1]) as server:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                server.port,
                ssl=server.client_context(),
                server_hostname=fake_roblox.HOSTS[0],
            )
            writer.write(b"GET /nothing HTTP/1.1\r\nHost: x\r\n\r\n")
            await writer.drain()
            answer = await reader.readuntil(b"\r\n\r\n")
            writer.close()
            return answer

    assert run(body).startswith(b"HTTP/1.1 404 ")
