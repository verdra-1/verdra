# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Plan 10.2's hosts and plan 16.2's protected endpoints (roots/rules)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.ids import ABOVE_INT32, ABOVE_UINT32
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


def graft(
    original: int, kind: str = "asset_id", value: str = "2", slot: str | None = None
) -> rules.Graft:
    return rules.Graft(original, slot, kind, value, "P", f"r{original}")  # type: ignore[arg-type]


def test_a_snapshot_needs_only_the_hosts_its_replacements_use() -> None:
    assert rules.GraftSnapshot().hosts() == frozenset()
    ids = rules.GraftSnapshot({(1, None): graft(1), (2, None): graft(2, value="7")})
    assert ids.hosts() == {"assetdelivery.roblox.com"}
    assert ids.swaps() == {1: 2, 2: 7}
    for content in (
        graft(3, "file", "./a.png"),
        graft(3, "url", "https://x/a"),
        graft(3, "remove", ""),
        graft(3, slot="normal"),
    ):
        snapshot = rules.GraftSnapshot({(1, None): graft(1), (3, content.slot): content})
        assert snapshot.hosts() == {"assetdelivery.roblox.com", "fts.rbxcdn.com"}
        assert snapshot.swaps() == {1: 2}
    assert all(rules.is_roblox_host(host) for host in ids.hosts() | snapshot.hosts())


def test_swaps_keep_real_size_ids_exactly() -> None:
    snapshot = rules.GraftSnapshot(
        {
            (ABOVE_UINT32, None): graft(ABOVE_UINT32, value=str(ABOVE_INT32)),
            (ABOVE_INT32, None): graft(ABOVE_INT32, value=str(ABOVE_UINT32)),
        }
    )
    assert snapshot.swaps() == {ABOVE_UINT32: ABOVE_INT32, ABOVE_INT32: ABOVE_UINT32}


def test_the_holder_swaps_whole_snapshots() -> None:
    holder = rules.SnapshotHolder()
    first = holder.current
    assert first.grafts == {}
    second = rules.GraftSnapshot({(1, None): graft(1)})
    holder.publish(second)
    assert holder.current is second and first.grafts == {}
