# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-15 (per-app mode): the signs of another routing tool (roots/gardener)."""

from __future__ import annotations

import time

import pytest

from verdra.roots import gardener
from verdra.soil import humus

OWN = {49443}


def roblox(pid: int, proxies: dict[str, str] | None, error: str = "") -> humus.RunningClient:
    return humus.RunningClient(pid, "RobloxPlayerBeta.exe", proxies, error)


@pytest.mark.spec("S-15", 1)
def test_a_roblox_with_another_proxy_is_a_sign_and_verdras_own_or_none_isnt() -> None:
    other = roblox(
        10, {"HTTPS_PROXY": "http://127.0.0.1:8888", "HTTP_PROXY": "http://127.0.0.1:8888"}
    )
    found = gardener.check_coexistence([other], OWN, "")
    assert not found.clear
    assert found.signs == (
        "Another routing tool: RobloxPlayerBeta.exe (process 10) uses the proxy "
        "http://127.0.0.1:8888.",
    )
    for proxies in (
        {"HTTPS_PROXY": "http://127.0.0.1:49443"},
        {"HTTPS_PROXY": "localhost:49443"},
        {},
    ):
        assert gardener.check_coexistence([roblox(11, proxies)], OWN, "").clear


def test_a_proxy_address_is_shown_without_its_user_name_or_password() -> None:
    found = gardener.check_coexistence(
        [roblox(12, {"HTTPS_PROXY": "http://alice:secret@proxy.example:3128"})], OWN, ""
    )
    assert "alice" not in found.signs[0] and "secret" not in found.signs[0]
    assert "http://proxy.example:3128" in found.signs[0]


@pytest.mark.spec("S-15", 3)
def test_roblox_hosts_in_the_hosts_file_without_verdras_marker_are_signs() -> None:
    text = "\n".join(
        [
            "# 127.0.0.1 assetdelivery.roblox.com",  # a comment
            "127.0.0.1 localhost",
            "127.0.0.1 assetdelivery.roblox.com",  # line 3
            "10.1.2.3   gamejoin.roblox.com  # someone else's",  # line 4, any address
            "127.0.0.1 assetdelivery.roblox.com # verdra:route",  # Verdra's own
            "127.0.0.1 fts.rbxcdn.com",  # line 6, a CDN host
            "127.0.0.1 roblox.com.example.org",
        ]
    )
    assert gardener.hosts_signs(text) == [
        (3, "assetdelivery.roblox.com"),
        (4, "gamejoin.roblox.com"),
        (6, "fts.rbxcdn.com"),
    ]
    found = gardener.check_coexistence([], OWN, text)
    assert found.signs[0] == (
        "Another routing tool: line 3 of the hosts file maps assetdelivery.roblox.com."
    )


@pytest.mark.spec("S-15", 6)
def test_what_cant_be_read_is_incomplete_not_a_sign() -> None:
    found = gardener.check_coexistence([roblox(13, None, "AccessDenied")], OWN, None)
    assert found.clear
    assert found.incomplete == ("RobloxPlayerBeta.exe (13): AccessDenied", "hosts")
    unlisted = gardener.check_coexistence(None, OWN, "", unreadable="processes: unconfirmed")
    assert unlisted.clear and unlisted.incomplete == ("processes: unconfirmed",)


@pytest.mark.spec("S-15", 7)
def test_the_check_is_fast_with_200_processes_and_2000_hosts_lines() -> None:
    running = [roblox(n, {"HTTPS_PROXY": "http://127.0.0.1:49443"}) for n in range(200)]
    text = "\n".join(f"10.0.{n // 250}.{n % 250} host{n}.example.org" for n in range(2000))
    started = time.perf_counter()
    assert gardener.check_coexistence(running, OWN, text).clear
    assert time.perf_counter() - started < 2.0
