# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-26: `verdra.profile` version 2, the migration from version 1, and applied copies."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from verdra.soil import terrain
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Target

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Messages are translated through Qt."""


def store(folder: Path) -> grafts.ProfileStore:
    return grafts.ProfileStore(folder, [], now=lambda: NOW)


def v1_file(folder: Path, name: str, replacements: list[dict[str, object]]) -> Path:
    """A profile exactly as a version 1 Verdra wrote it."""
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "format": "verdra.profile",
        "version": 1,
        "id": f"id-{name}",
        "name": name,
        "enabled": True,
        "created": "2026-10-04T12:00:00Z",
        "modified": "2026-10-04T12:00:00Z",
        "replacements": replacements,
    }
    path = folder / f"{name}.json"
    path.write_bytes(json.dumps(data, indent=2).encode() + b"\n")
    return path


def row(asset_id: int, kind: str, value: str = "", *, enabled: bool = True) -> dict[str, object]:
    return {
        "id": f"r{asset_id}",
        "enabled": enabled,
        "original": {"asset_id": asset_id, "slot": None},
        "target": {"kind": kind, "value": value},
        "asset_type": "Image",
        "note": "",
    }


@pytest.mark.spec("S-26", 7)
def test_a_version_1_profile_migrates_with_applied_equal_to_saved(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    picture = profiles / "Walls" / "wall.png"
    picture.parent.mkdir(parents=True)
    picture.write_bytes(PNG)
    path = v1_file(
        profiles,
        "Walls",
        [
            row(1, "asset_id", "100"),
            row(2, "file", "./wall.png"),
            row(3, "file", "./gone.png"),
            row(4, "remove", enabled=False),
        ],
    )
    original_v1 = json.loads(path.read_bytes())
    before = grafts.compile_snapshot([grafts.read_profile(path)])
    made = store(profiles)
    [profile] = made.profiles
    assert profile.version == 2 and profile.applied_enabled is True
    for replacement in profile.replacements:
        applied = replacement.applied
        assert applied is not None
        assert (applied.original, applied.target) == (replacement.original, replacement.target)
        assert applied.enabled == replacement.enabled and applied.at == NOW
    by_id = {r.original.asset_id: r.applied for r in profile.replacements}
    sha = hashlib.sha256(PNG).hexdigest()
    assert by_id[2] is not None and by_id[2].sha256 == sha
    assert (tmp_path / terrain.APPLIED_FOLDER / sha).read_bytes() == PNG
    assert by_id[3] is not None and by_id[3].sha256 is None  # missing file: no copy
    assert by_id[1] is not None and by_id[1].sha256 is None  # an Asset ID needs none
    # The file on disk is version 2 now; the version 1 profile is kept beside it.
    assert json.loads(path.read_bytes())["version"] == 2
    kept = json.loads((profiles / "Walls.json.v1").read_bytes())
    assert kept == original_v1
    # Nothing the game gets changed: the same snapshot as version 1 compiled.
    after = grafts.compile_snapshot(made.profiles)
    assert after.snapshot.grafts == before.snapshot.grafts


def test_migrating_twice_changes_nothing(tmp_path: Path) -> None:
    path = v1_file(tmp_path / "profiles", "A", [row(1, "asset_id", "5")])
    store(tmp_path / "profiles")
    first = path.read_bytes()
    kept = (tmp_path / "profiles" / "A.json.v1").read_bytes()
    store(tmp_path / "profiles")
    assert path.read_bytes() == first
    assert (tmp_path / "profiles" / "A.json.v1").read_bytes() == kept


def test_a_damaged_file_with_a_version_1_copy_migrates_from_the_copy(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    path = v1_file(profiles, "A", [row(1, "asset_id", "5")])
    path.rename(profiles / "A.json.bak")
    path.write_bytes(b"{ broken")
    [profile] = store(profiles).profiles
    assert profile.replacements[0].applied is not None  # migrated, not left unapplied
    assert json.loads(path.read_bytes())["version"] == 2


@pytest.mark.spec("S-26", 8)
def test_a_version_2_file_round_trips_byte_for_byte_with_unknown_view_keys(
    tmp_path: Path,
) -> None:
    made = store(tmp_path)
    profile = made.create("A")
    added = made.add_replacement(profile.id, Original(asset_id=1), Target(kind="remove"))
    added.view = {"try_on": "cube", "later": {"phase": "C", "zoom": 1.5}}
    added.name = "Wall picture"
    made.edit_replacement(profile.id, added)
    path = tmp_path / "A.json"
    written = path.read_bytes()
    loaded = grafts.read_profile(path)
    assert grafts.encode(loaded) == written
    assert loaded.replacements[0].view == {"try_on": "cube", "later": {"phase": "C", "zoom": 1.5}}


def test_view_settings_larger_than_4_kb_are_dropped_not_the_profile(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("A")
    added = made.add_replacement(profile.id, Original(asset_id=1), Target(kind="remove"))
    added.view = {"big": "x" * grafts.MAX_VIEW_BYTES}
    made.edit_replacement(profile.id, added)
    [loaded] = store(tmp_path).profiles
    assert loaded.replacements[0].view == {}
    assert loaded.replacements[0].original.asset_id == 1


@pytest.mark.parametrize("version", [3, 17])
def test_a_file_from_a_newer_verdra_is_left_untouched_and_named(
    tmp_path: Path, version: int, caplog: pytest.LogCaptureFixture
) -> None:
    """S-20 rule 4: never moved aside as broken, never rewritten, not used (M-PROF-11)."""
    newer = tmp_path / "New.json"
    data = {"format": "verdra.profile", "version": version, "id": "x", "name": "New"}
    newer.write_bytes(json.dumps(data).encode())
    before = newer.read_bytes()
    v1_file(tmp_path, "Old", [row(1, "asset_id", "5")])
    made = store(tmp_path)
    assert [p.name for p in made.profiles] == ["Old"]
    [error] = made.newer
    assert (error.path, error.version) == (newer, version)
    assert newer.read_bytes() == before
    assert not list(tmp_path.glob("New.json.broken-*"))
    assert "saved by a newer version of Verdra" in caplog.text


def test_applied_copies_are_shared_limited_and_pruned(tmp_path: Path) -> None:
    copies = grafts.AppliedCopies(tmp_path / "Applied", limit=100)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"A" * 40)
    b.write_bytes(b"A" * 40)  # same bytes: one copy
    first, second = copies.keep(a), copies.keep(b)
    assert first == second == hashlib.sha256(b"A" * 40).hexdigest()
    assert copies.size() == 40
    c = tmp_path / "c.png"
    c.write_bytes(b"C" * 61)  # 40 + 61 > 100
    with pytest.raises(grafts.ProfileError, match="more than 2 GB"):
        copies.keep(c)
    assert copies.size() == 40
    d = tmp_path / "d.png"
    d.write_bytes(b"D" * 10)
    other = copies.keep(d)
    assert copies.prune({first}) == 1
    assert copies.has(first) and not copies.has(other)


def test_applied_hashes_are_what_applied_versions_name(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    picture = profiles / "A" / "wall.png"
    picture.parent.mkdir(parents=True)
    picture.write_bytes(PNG)
    v1_file(profiles, "A", [row(1, "file", "./wall.png"), row(2, "asset_id", "9")])
    made = store(profiles)
    assert grafts.applied_hashes(made.profiles) == {hashlib.sha256(PNG).hexdigest()}


def test_the_v1_copy_is_readable_by_a_version_1_reader(tmp_path: Path) -> None:
    """The kept `.v1` file has only version 1 fields, so an older Verdra can be pointed at it."""
    v1_file(tmp_path, "A", [row(1, "asset_id", "5")])
    store(tmp_path)
    kept = json.loads((tmp_path / "A.json.v1").read_bytes())
    assert kept["version"] == 1
    assert set(kept["replacements"][0]) == {
        "id",
        "enabled",
        "original",
        "target",
        "asset_type",
        "note",
    }


@pytest.mark.parametrize("asset_id", [ABOVE_INT32, ABOVE_UINT32])
def test_real_size_ids_migrate_and_round_trip_exactly(tmp_path: Path, asset_id: int) -> None:
    path = v1_file(tmp_path, "A", [row(asset_id, "asset_id", str(ABOVE_UINT32))])
    [profile] = store(tmp_path).profiles
    applied = profile.replacements[0].applied
    assert applied is not None
    assert applied.original.asset_id == asset_id and applied.target.value == str(ABOVE_UINT32)
    assert grafts.encode(grafts.read_profile(path)) == path.read_bytes()
    kept = json.loads((tmp_path / "A.json.v1").read_bytes())
    assert kept["replacements"][0]["original"]["asset_id"] == asset_id
