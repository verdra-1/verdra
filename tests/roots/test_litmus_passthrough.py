# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The pass-through control (spec S-11 test 14, source runs only, 22 October 2026).

On 21 October Roblox closed every decrypted assetdelivery connection right after its handshake.
`--no-intercept <hosts>` tunnels those hosts instead, and Verdra logs the certificate chain
their real servers present; `--send-ca` presents Verdra's CA after each leaf.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.roots.test_hyphae import FakeServer, Proxy, run
from tests.roots.test_taproot import client_context
from verdra.bark import resin
from verdra.roots import gardener, hyphae, litmus, taproot
from verdra.trunk.sapwood import cli

HOST = "assetdelivery.roblox.com"
NOW = datetime.now(UTC)


@pytest.mark.spec("S-11", 14)
def test_the_flags_need_the_source_and_take_host_names(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = cli.parse([cli.NO_INTERCEPT_FLAG, "AssetDelivery.Roblox.com.,fts.rbxcdn.com"])
    assert parsed.no_intercept == ("assetdelivery.roblox.com", "fts.rbxcdn.com")
    assert not parsed.send_ca
    assert cli.parse([cli.SEND_CA_FLAG]).send_ca
    assert cli.parse([]) == cli.Arguments()
    for bad in ("", ",", "not a host", "15553230204"):
        with pytest.raises(SystemExit):
            cli.parse([cli.NO_INTERCEPT_FLAG, bad])
    with pytest.raises(SystemExit):
        cli.parse([cli.NO_INTERCEPT_FLAG])  # the hosts are required
    monkeypatch.setattr(cli, "diagnosis_available", lambda: False)
    for flags in ([cli.NO_INTERCEPT_FLAG, HOST], [cli.SEND_CA_FLAG]):
        with pytest.raises(SystemExit) as frozen:
            cli.parse(flags)
        assert frozen.value.code == 2


@pytest.mark.spec("S-11", 14)
def test_the_probe_logs_the_real_servers_chain_without_a_request(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})

    async def body() -> None:
        port, authority = await server.start()
        context = client_context(authority)

        async def open_upstream(host: str, _port: int) -> hyphae.Streams:
            return await taproot.open_tls(
                taproot.Transport("direct"), host, port, context=context, address="127.0.0.1"
            )

        await litmus.probe_certificates([HOST, "unreachable.roblox.com"], open_upstream)
        server.server.close()

    run(body)
    lines = [r.getMessage() for r in caplog.records if r.name == "verdra.roots.litmus"]
    assert lines[0].startswith(f"The real server for {HOST}: TLSv1.3, TLS_")
    assert lines[0].endswith("ALPN chosen: none, 1 certificates sent")  # the fake has none
    assert lines[1].startswith(f"The real server for {HOST}, certificate 1: subject ")
    assert "signed certificate timestamps: none" in lines[1]
    assert "key pin (SHA-256 of the public key) " in lines[1]
    assert lines[2].startswith("The real certificate of unreachable.roblox.com couldn't be read")
    assert server.received == []  # a handshake only: no request reached the server


def test_a_certificate_description_names_timestamps_and_constraints() -> None:
    authority = resin.create_authority(NOW)
    leaf = resin.issue_leaf(authority, HOST, NOW)
    described = litmus.describe_certificate(leaf.certificate)
    # Verdra's own leaf (bark/resin): ECDSA P-256, one name, no timestamps, no basic constraints.
    assert "key ECDSA secp256r1" in described
    assert "1 DNS names" in described
    assert "signed certificate timestamps: none" in described
    assert "basic constraints: none" in described
    assert "basic constraints: CA" in litmus.describe_certificate(authority.certificate)


@pytest.mark.spec("S-11", 14)
def test_send_ca_presents_the_authority_after_the_leaf(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots")
    server = FakeServer(tmp_path, {})
    chains: list[int] = []

    async def body() -> None:
        async with Proxy(server) as proxy:
            interception = proxy.mycelium.interceptor
            assert isinstance(interception, hyphae.Interception)
            interception.leaves.send_authority = True
            client = await proxy.connect()
            tls = client.writer.get_extra_info("ssl_object")
            assert isinstance(tls, ssl.SSLObject)
            chains.append(len(tls.get_unverified_chain() or ()))
            client.writer.close()
            await asyncio.sleep(0.2)

    run(body)
    assert chains == [2]
    assert any(
        r.getMessage().endswith("chain sent: this certificate, then Verdra's CA")
        for r in caplog.records
    )


def test_run_soon_without_routing_closes_the_coroutine(qapp: object) -> None:
    status = gardener.RoutingStatusSource()
    router = gardener.Router(status)
    ran: list[str] = []

    async def job() -> None:
        ran.append("ran")

    coroutine = job()
    assert router.run_soon(coroutine) is False
    assert coroutine.cr_frame is None  # closed, so never "was never awaited"
    assert ran == []
    router.deleteLater()
    status.deleteLater()
