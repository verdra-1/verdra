# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Plan 10.2's hosts and plan 16.2's protected endpoints (roots/rules)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.roots.test_hyphae import PROTECTED_SPELLINGS
from verdra.roots import rules


def test_the_hosts_are_exactly_the_list_confirmed_at_m1() -> None:
    expected = {
        "apis.roblox.com",
        "assetdelivery.roblox.com",
        "clientsettings.roblox.com",
        "clientsettingscdn.roblox.com",
        "gamejoin.roblox.com",
        "apis.rbxcdn.com",
        "fts.rbxcdn.com",
        "tr.rbxcdn.com",
        "sc0.rbxcdn.com",
        "sc0ak.rbxcdn.com",
        "sc0aws.rbxcdn.com",
        "sc2.rbxcdn.com",
        "sc5.rbxcdn.com",
    }
    assert expected == rules.ROBLOX_HOSTS
    assert rules.is_roblox_host("FTS.rbxcdn.com.")
    assert not rules.is_roblox_host("c0.rbxcdn.com")
    assert not rules.is_roblox_host("www.roblox.com")


@pytest.mark.spec("S-11", 12)
@pytest.mark.parametrize("target", PROTECTED_SPELLINGS)
def test_a_rule_for_a_protected_endpoint_is_refused(target: bytes) -> None:
    with pytest.raises(rules.ProtectedEndpointError):
        rules.refuse_protected("APIS.roblox.com.", target)
    with pytest.raises(rules.ProtectedEndpointError):
        rules.refuse_protected("apis.roblox.com", target.decode())


@pytest.mark.spec("S-11", 12)
@pytest.mark.parametrize(("host", "path"), sorted(rules.PROTECTED_PATHS))
def test_every_listed_path_and_below_it_is_refused(host: str, path: str) -> None:
    for target in (path, path + "/", path + "/v1/anything", "https://" + host + path):
        with pytest.raises(rules.ProtectedEndpointError):
            rules.refuse_protected(host, target)


@pytest.mark.spec("S-11", 12)
@pytest.mark.parametrize(
    ("host", "target"),
    [
        ("apis.roblox.com", "/validate-machines"),
        ("apis.roblox.com", "/v1/validate-machine"),
        ("apis.roblox.com", "/user-profile-api/v1/user/profiles/get-profiles"),
        ("assetdelivery.roblox.com", "/validate-machine"),
        ("fts.rbxcdn.com", "/sc0/0123abcd"),
    ],
)
def test_neighboring_paths_are_allowed(host: str, target: str) -> None:
    rules.refuse_protected(host, target)


@given(st.text(max_size=40))
def test_anything_that_resolves_to_a_protected_path_is_protected(prefix: str) -> None:
    # One segment, whatever it holds, then "/../" (raw or escaped): a server resolves the target
    # to the protected path.
    segment = prefix
    for character in "/\\?#":
        segment = segment.replace(character, "_")
    for separator in ("/", "%2F", "%252f"):
        target = "/" + segment + separator + "../validate-machine"
        assert rules.is_protected("apis.roblox.com", target), target
