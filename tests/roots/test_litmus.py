# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-11 test 9: diagnostic interception from source (roots/litmus, decision record 0015)."""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import Awaitable, Callable

import pytest

from tests.roots.test_passthrough import replay_all
from tools import fake_roblox
from verdra.roots import hyphae, litmus


def run[T](coroutine: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine(), timeout=120))


@pytest.mark.spec("S-11", 9)
def test_every_host_is_intercepted_unchanged_with_tls_details_in_activity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="verdra.roots.litmus"):
        server = run(lambda: replay_all(intercepted=True, diagnose=litmus.interception))
    assert len(server.requests) == 1000  # all 1,000 byte-identical: replay_all checks each
    lines = [r.getMessage() for r in caplog.records if r.name == "verdra.roots.litmus"]
    for host in fake_roblox.HOSTS:
        client = [line for line in lines if f", {host} (Roblox to Verdra): TLSv1." in line]
        upstream = [line for line in lines if f", {host} (Verdra to the server): TLSv1." in line]
        assert client, host
        assert upstream, host
        assert all("Verdra's certificate, key ECDSA P-256." in line for line in client)
        assert all("the server's certificate verified." in line for line in upstream)


def test_the_diagnostic_set_is_the_10_2_hosts_and_the_cdn() -> None:
    hosts = litmus.DiagnosticHosts()
    assert all(host in hosts for host in fake_roblox.HOSTS)
    assert "T7.RBXCDN.COM" in hosts
    assert "www.roblox.com" not in hosts
    assert "rbxcdn.com.example" not in hosts
    assert 42 not in hosts
    assert sorted(hosts) == sorted(litmus.HOSTS)
    assert len(hosts) == len(litmus.HOSTS)


def test_no_symbiont_runs_in_diagnostic_mode() -> None:
    interception = litmus.interception(None, None)  # type: ignore[arg-type]
    pipeline = interception.pipeline()
    assert (list(pipeline.request), list(pipeline.response)) == ([], [])


class FakeTls:
    """Just enough of ssl.SSLObject for log_tls."""

    def __init__(self, verify: ssl.VerifyMode, *, cipher: bool = True) -> None:
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname = False
        self.context.verify_mode = verify
        self._cipher = cipher

    def version(self) -> str | None:
        return None

    def cipher(self) -> tuple[str, str, int] | None:
        return ("TLS_AES_128_GCM_SHA256", "TLSv1.3", 128) if self._cipher else None


def test_an_unverified_upstream_is_reported_as_such(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="verdra.roots.litmus"):
        litmus.log_tls("apis.roblox.com", "upstream", FakeTls(ssl.CERT_NONE, cipher=False))  # type: ignore[arg-type]
    (line,) = [r.getMessage() for r in caplog.records]
    assert line.endswith("(Verdra to the server): ?, ?, the server's certificate not verified.")


def test_a_failing_tls_observer_never_breaks_the_connection() -> None:
    def broken(_host: str, _side: str, _tls: ssl.SSLObject) -> None:
        raise RuntimeError("observer")

    interception = hyphae.Interception(None, frozenset, None, on_tls=broken)  # type: ignore[arg-type]

    class Writer:
        def get_extra_info(self, _name: str) -> object:
            return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).wrap_bio(
                ssl.MemoryBIO(), ssl.MemoryBIO()
            )

    interception.observe("apis.roblox.com", "client", Writer())  # type: ignore[arg-type]
