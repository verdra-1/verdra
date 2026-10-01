# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Every R2 range and type, at its boundaries (spec S-02; review finding H2).

The table below is written from Reference R2 (as settled in decision records 0008 and 0010),
not from the schema, so that a schema change that widens or narrows a range fails here.
"""

import json
from pathlib import Path
from typing import Any

import msgspec
import pytest

from verdra.trunk.almanac import schema, store
from verdra.trunk.almanac.store import SettingsStore

#: key → (accepted values, rejected values). Boundaries ±1, wrong types and strictness.
RANGES: dict[str, tuple[list[Any], list[Any]]] = {
    "routing.proxy_port": ([1024, 49443, 65535], [1023, 65536, 0, "49443", 49443.0, True]),
    "routing.upstream.port": ([0, 1, 65535], [-1, 65536, "1", 1.0]),
    "library.size_cap_gb": ([1, 5, 100], [0, 101, "5", 5.0, False]),
    "advanced.worker_threads": ([2, 4, 8], [1, 9, "4", 4.0]),
    "appearance.text_scale": ([90, 100, 115, 130], [89, 110, 131, 120, "100", 100.0]),
    "tweaks.frame_rate_cap": ([None, "unlimited", 30, 1000], [29, 1001, 0, "60", 60.0, "max"]),
    "accounts.launch_account": ([None, 1, 2**40], [0, -1, "1", 1.0]),
    "accounts.displayed_name": (["", "x" * 20], ["x" * 21, 5]),
    "routing.mode": (["per_app", "hosts_file"], ["hosts", "", None]),
    "routing.upstream.kind": (["system", "direct", "http", "socks5"], ["https", "SOCKS5"]),
    "general.update_channel": (["stable", "beta"], ["nightly", "Stable"]),
    "appearance.theme": (["system", "light", "dark"], ["auto", "Dark"]),
    "appearance.reduce_motion": (["system", "on", "off"], [True, "yes"]),
    "appearance.density": (["comfortable", "compact"], ["dense"]),
    "general.close_to_tray": ([True, False], [1, 0, "true", None]),
}


@pytest.fixture
def settings(tmp_path: Path) -> SettingsStore:
    loaded = SettingsStore(tmp_path / "settings.json")
    loaded.load()
    return loaded


def default(key: str) -> Any:
    """Return the schema default of a dotted key."""
    value: Any = schema.Settings()
    for part in key.split("."):
        value = getattr(value, part)
    return value


def test_every_ranged_key_is_covered() -> None:
    for key in RANGES:
        default(key)  # raises AttributeError for a key the schema doesn't have


@pytest.mark.spec("S-02", 7)
@pytest.mark.parametrize(
    ("key", "value"), [(key, value) for key, (good, _) in RANGES.items() for value in good]
)
def test_values_inside_the_range_are_accepted(
    settings: SettingsStore, key: str, value: Any
) -> None:
    settings.set(key, value)
    assert settings.value(key) == value


@pytest.mark.spec("S-02", 7)
@pytest.mark.parametrize(
    ("key", "value"), [(key, value) for key, (_, bad) in RANGES.items() for value in bad]
)
def test_values_outside_the_range_are_rejected(
    settings: SettingsStore, key: str, value: Any
) -> None:
    before = settings.value(key)
    with pytest.raises(msgspec.ValidationError):
        settings.set(key, value)
    assert settings.value(key) == before


@pytest.mark.parametrize(("key", "value"), [(key, bad[0]) for key, (_, bad) in RANGES.items()])
def test_a_bad_value_in_the_file_falls_back_to_its_default(key: str, value: Any) -> None:
    document: dict[str, Any] = {}
    target = document
    *groups, name = key.split(".")
    for group in groups:
        target = target.setdefault(group, {})
    target[name] = value
    decoded = store.decode(document)
    current: Any = decoded.settings
    for part in key.split("."):
        current = getattr(current, part)
    assert current == default(key)
    assert any(problem.startswith(key) for problem in decoded.problems)


@pytest.mark.spec("S-02", 7)
@pytest.mark.parametrize(
    ("key", "good", "bad"),
    [
        ("tweaks.active_flag_profile", ["", "Smooth.json", "my flags.json"],
         ["../../evil", "a/b.json", "a\\b.json", "C:x.json", "..", "."]),
        ("library.location", ["", "/home/me/Library", "C:\\Users\\me\\Library", "D:/Lib",
          "\\\\server\\share\\lib"], ["relative/path", "Library", "~/Library"]),
    ],
)  # fmt: skip
def test_names_and_paths_are_checked(
    settings: SettingsStore, key: str, good: list[str], bad: list[str]
) -> None:
    # Review finding M6: R2 says "name of a file in climate/" and "path".
    for value in good:
        settings.set(key, value)
    for value in bad:
        with pytest.raises(msgspec.ValidationError):
            settings.set(key, value)


def test_one_unknown_risk_acceptance_keeps_the_others() -> None:
    # Review finding M5: a newer Verdra's feature must not wipe every acceptance.
    accepted = {"accepted_at": "2026-10-01T00:00:00Z", "app_version": "0.0.1"}
    document = {"privacy": {"risk_acceptances": {"accounts": accepted, "future_thing": accepted}}}
    decoded = store.decode(document)
    assert list(decoded.settings.privacy.risk_acceptances) == ["accounts"]
    assert decoded.unknown == {"privacy": {"risk_acceptances": {"future_thing": accepted}}}
    encoded = json.loads(store.encode(decoded.settings, decoded.unknown))
    assert set(encoded["privacy"]["risk_acceptances"]) == {"accounts", "future_thing"}
    broken = {
        "privacy": {"risk_acceptances": {"accounts": {"accepted_at": 5}, "subplaces": accepted}}
    }
    assert list(store.decode(broken).settings.privacy.risk_acceptances) == ["subplaces"]
