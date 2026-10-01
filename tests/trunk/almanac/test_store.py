# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-02: settings store."""

import json
import logging
import random
import subprocess
import sys
import textwrap
from pathlib import Path

import msgspec
import pytest
from pytestqt.qtbot import QtBot

from verdra.soil import atomic
from verdra.trunk.almanac import migrate, schema
from verdra.trunk.almanac.store import ReadOnlyError, SettingsStore, StateStore, encode, parse

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "settings"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "config" / "settings.json"


def write(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def loaded(path: Path) -> SettingsStore:
    store = SettingsStore(path)
    store.load()
    return store


def test_missing_file_means_defaults_and_no_notice(path: Path) -> None:
    store = loaded(path)
    assert store.settings == schema.Settings()
    assert store.notices == []
    assert not path.exists()


@pytest.mark.spec("S-02", 1)
def test_kill_during_write_leaves_a_valid_file(path: Path) -> None:
    store = SettingsStore(path)
    # A large document makes each write take long enough to be interrupted mid-way.
    store.settings.traffic.rules = [
        schema.TrafficRule(host=f"h{i}.roblox.com", where="json", find="a" * 200, replace="b")
        for i in range(2000)
    ]
    data = encode(store.settings, {})
    atomic.write_atomic(path, data)
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from verdra.soil.atomic import write_atomic
        data = Path({str(path)!r}).read_bytes()
        flip = data.replace(b'"close_to_tray": true', b'"close_to_tray": false')
        while True:
            write_atomic(Path({str(path)!r}), flip, keep_backup=True)
            write_atomic(Path({str(path)!r}), data, keep_backup=True)
        """
    )
    for _ in range(8):
        process = subprocess.Popen([sys.executable, "-c", script])  # noqa: S603
        try:
            process.wait(timeout=random.uniform(0.3, 0.8))  # noqa: S311
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        document = parse(atomic.read_bytes(path))
        assert len(document["traffic"]["rules"]) == 2000
    store.load()
    assert store.notices == []
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.spec("S-02", 2)
def test_corrupt_file_restores_the_backup(path: Path) -> None:
    write(path, {"format": "verdra.settings", "version": 1, "appearance": {"theme": "dark"}})
    atomic.write_atomic(path, b"{not json", keep_backup=True)
    store = loaded(path)
    assert [notice.message_id for notice in store.notices] == ["M-SET-01"]
    assert store.settings.appearance.theme == "dark"
    assert parse(path.read_bytes())["appearance"]["theme"] == "dark"


@pytest.mark.spec("S-02", 3)
def test_both_corrupt_means_defaults_and_the_file_moved_aside(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00garbage")
    atomic.backup_path(path).write_bytes(b"[]")
    store = loaded(path)
    assert store.settings == schema.Settings()
    (notice,) = store.notices
    assert notice.message_id == "M-SET-02"
    (moved,) = path.parent.glob("settings.json.broken-*")
    assert moved.name in notice.text
    assert moved.read_bytes() == b"\x00garbage"
    assert not path.exists()


@pytest.mark.spec("S-02", 4)
def test_every_fixture_version_migrates() -> None:
    fixtures = sorted(FIXTURES.glob("v*.json"))
    versions = {int(fixture.stem[1:]) for fixture in fixtures}
    # One fixture per version from 1 to the current one, and one step per older version.
    assert versions == set(range(1, schema.VERSION + 1))
    assert set(migrate.SETTINGS_STEPS) == set(range(1, schema.VERSION))
    for fixture in fixtures:
        document = migrate.migrate(
            json.loads(fixture.read_text(encoding="utf-8")), migrate.SETTINGS_STEPS, schema.VERSION
        )
        assert document["version"] == schema.VERSION
    store = loaded(FIXTURES / "v1.json")
    assert store.settings.general.close_to_tray is False
    assert store.settings.routing.upstream.kind == "socks5"
    assert store.settings.appearance.text_scale == 115
    assert store.settings.advanced.worker_threads == 6


def test_migration_chain_runs_each_step_in_order() -> None:
    steps = {
        1: lambda doc: {key: v for key, v in doc.items() if key != "old"} | {"renamed": doc["old"]},
        2: lambda doc: {**doc, "added": True},
    }
    result = migrate.migrate({"version": 1, "old": 5}, steps, 3)
    assert result == {"version": 3, "renamed": 5, "added": True}
    with pytest.raises(migrate.MigrationError):
        migrate.migrate({"version": 1}, {}, 2)
    with pytest.raises(migrate.MigrationError):
        migrate.migrate({"version": 4}, steps, 3)


@pytest.mark.spec("S-02", 5)
def test_newer_file_opens_read_only(path: Path) -> None:
    write(path, {"format": "verdra.settings", "version": 99, "appearance": {"theme": "dark"}})
    before = path.read_bytes()
    store = loaded(path)
    assert store.read_only
    assert [notice.message_id for notice in store.notices] == ["M-SET-03"]
    assert store.settings.appearance.theme == "dark"
    with pytest.raises(ReadOnlyError):
        store.set("appearance.theme", "light")
    store.flush()
    assert path.read_bytes() == before


@pytest.mark.spec("S-02", 6)
def test_unknown_keys_are_kept_and_reported(path: Path, caplog: pytest.LogCaptureFixture) -> None:
    write(
        path,
        {
            "format": "verdra.settings",
            "version": 1,
            "future": {"x": 1},
            "general": {"close_to_tray": False, "new_thing": "yes"},
        },
    )
    with caplog.at_level(logging.WARNING):
        store = loaded(path)
    reports = [record.getMessage() for record in caplog.records if "unknown" in record.getMessage()]
    assert len(reports) == 2
    store.set("appearance.theme", "dark")
    store.flush()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["future"] == {"x": 1}
    assert saved["general"]["new_thing"] == "yes"
    assert saved["general"]["close_to_tray"] is False


@pytest.mark.spec("S-02", 7)
def test_wrong_values_fall_back_to_defaults(path: Path, caplog: pytest.LogCaptureFixture) -> None:
    write(
        path,
        {
            "format": "verdra.settings",
            "version": 1,
            "general": {"close_to_tray": "yes", "update_channel": "nightly"},
            "routing": {"proxy_port": 80},
            "library": {"size_cap_gb": 5000, "capture": False},
            "appearance": "dark",
        },
    )
    with caplog.at_level(logging.WARNING):
        store = loaded(path)
    assert store.settings.general.close_to_tray is True
    assert store.settings.general.update_channel == "stable"
    assert store.settings.routing.proxy_port == 49443
    assert store.settings.library.size_cap_gb == 5
    assert store.settings.library.capture is False
    assert store.settings.appearance == schema.Appearance()
    assert len([r for r in caplog.records if "default" in r.getMessage()]) == 5


@pytest.mark.spec("S-02", 8)
def test_changes_within_300_ms_are_written_once(
    path: Path, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = loaded(path)
    writes: list[Path] = []
    original = atomic.write_atomic

    def counting(target: Path, data: bytes, *, keep_backup: bool = False) -> None:
        if target == path:
            writes.append(target)
        original(target, data, keep_backup=keep_backup)

    monkeypatch.setattr(atomic, "write_atomic", counting)
    for value in range(10):
        store.set("advanced.worker_threads", value + 1)
    assert writes == []
    qtbot.waitUntil(lambda: len(writes) == 1, timeout=1000)
    qtbot.wait(400)
    assert len(writes) == 1
    assert parse(path.read_bytes())["advanced"]["worker_threads"] == 10


@pytest.mark.spec("S-02", 10)
def test_every_r2_key_has_its_default() -> None:
    keys = schema.keys()
    expected = {
        "general.start_with_system": False,
        "general.start_minimised": True,
        "general.close_to_tray": True,
        "general.route_on_launch": True,
        "general.check_updates": True,
        "general.update_channel": "stable",
        "general.language": "system",
        "general.onboarding_done": False,
        "routing.mode": "per_app",
        "routing.proxy_port": 49443,
        "routing.handle_roblox_links": True,
        "routing.close_roblox_on_quit": False,
        "routing.upstream.kind": "system",
        "routing.upstream.host": "",
        "routing.upstream.port": 0,
        "routing.upstream.username": "",
        "library.capture": True,
        "library.size_cap_gb": 5,
        "library.location": "",
        "appearance.theme": "system",
        "appearance.text_scale": 100,
        "appearance.reduce_motion": "system",
        "appearance.density": "comfortable",
        "privacy.risk_acceptances": {},
        "privacy.keep_traffic": False,
        "advanced.advanced_mode": False,
        "advanced.detailed_logging": False,
        "advanced.worker_threads": 4,
        "tweaks.custom_flags_enabled": False,
        "tweaks.active_flag_profile": "",
        "tweaks.flag_hotkeys": [],
        "tweaks.frame_rate_cap": None,
        "accounts.launch_account": None,
        "accounts.multi_instance": False,
        "accounts.subplaces": False,
        "accounts.displayed_name": "",
        "accounts.privacy_mode": False,
        "traffic.editing": False,
        "traffic.rules": [],
    }
    for key, default in expected.items():
        assert keys[key] == default, key
    # The only key beyond R2 records when detailed logging was turned on (spec S-03).
    assert set(keys) - set(expected) == {"advanced.detailed_logging_since"}


def test_set_validates_and_signals(path: Path, qtbot: QtBot) -> None:
    store = loaded(path)
    with qtbot.waitSignal(store.changed) as signal:
        store.set("appearance.theme", "dark")
    assert signal.args == ["appearance.theme", "dark"]
    with pytest.raises(msgspec.ValidationError):
        store.set("appearance.text_scale", 110)
    with pytest.raises(msgspec.ValidationError):
        store.set("accounts.displayed_name", "x" * 21)
    with pytest.raises(KeyError):
        store.set("appearance.nope", 1)
    store.set("tweaks.frame_rate_cap", "unlimited")
    store.set("tweaks.frame_rate_cap", 144)
    with pytest.raises(msgspec.ValidationError):
        store.set("tweaks.frame_rate_cap", 10)


def test_reset_group_resets_only_that_group(path: Path) -> None:
    store = loaded(path)
    store.set("appearance.theme", "dark")
    store.set("appearance.density", "compact")
    store.set("general.close_to_tray", False)
    store.reset_group("appearance")
    assert store.settings.appearance == schema.Appearance()
    assert store.settings.general.close_to_tray is False


def test_saved_file_format(path: Path) -> None:
    store = loaded(path)
    store.set("appearance.theme", "dark")
    store.flush()
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "format": "verdra.settings",\n  "version": 1,')
    assert text.endswith("}\n")
    store.set("appearance.theme", "light")
    store.flush()
    assert parse(atomic.backup_path(path).read_bytes())["appearance"]["theme"] == "dark"


def test_state_store_round_trip_and_damage(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.load()
    assert state.get("window") is None
    state.set("window", {"width": 1200})
    state.save()
    again = StateStore(tmp_path / "state.json")
    again.load()
    assert again.get("window") == {"width": 1200}
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    again.load()
    assert again.get("window", "fallback") == "fallback"
