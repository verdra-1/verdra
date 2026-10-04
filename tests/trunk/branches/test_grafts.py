# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-20: replacement profiles (trunk/branches/grafts), and their snapshot (S-21, S-23)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import pytest
from PySide6.QtWidgets import QApplication

from verdra.trunk.almanac import schema
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Target

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "docs" / "schemas" / "verdra.profile.schema.json"


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Messages are translated through Qt."""


def store(folder: Path, order: list[str] | None = None) -> grafts.ProfileStore:
    return grafts.ProfileStore(folder, order or [], now=lambda: NOW)


def swap(original: int, target: int) -> tuple[Original, Target]:
    return Original(asset_id=original), Target(kind="asset_id", value=str(target))


@pytest.mark.spec("S-20", 1)
def test_every_field_round_trips_byte_for_byte(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("Clean UI")
    made.add_replacement(profile.id, *swap(1234567890, 9876543210), asset_type="Image", note="n")
    made.add_replacement(
        profile.id,
        Original(asset_id=55, slot="normal"),
        Target(kind="file", value="./bricks/normal.png"),
        asset_type="TexturePack",
    )
    made.add_replacement(
        profile.id, Original(asset_id=56), Target(kind="url", value="https://x.example/a.png")
    )
    made.add_replacement(profile.id, Original(asset_id=57), Target(kind="remove"))
    path = tmp_path / "Clean UI.json"
    written = path.read_bytes()
    assert written.endswith(b"}\n") and b'\n  "format": "verdra.profile",\n' in written
    loaded = grafts.read_profile(path)
    assert loaded == made.get(profile.id)
    assert grafts.encode(loaded) == written
    data = json.loads(written)
    assert list(data) == [
        "format", "version", "id", "name", "enabled", "created", "modified", "replacements"
    ]  # fmt: skip
    assert data["created"] == "2026-10-04T12:00:00Z"
    assert data["replacements"][0] == {
        "id": data["replacements"][0]["id"],
        "enabled": True,
        "original": {"asset_id": 1234567890, "slot": None},
        "target": {"kind": "asset_id", "value": "9876543210"},
        "asset_type": "Image",
        "note": "n",
    }


def test_the_published_schema_names_every_field() -> None:
    published = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(published["properties"]) == set(grafts.Profile.__struct_fields__)
    item = published["$defs"]["replacement"]["properties"]
    assert set(item) == set(grafts.Replacement.__struct_fields__)
    assert set(item["original"]["properties"]) == set(grafts.Original.__struct_fields__)
    assert set(item["target"]["properties"]) == set(grafts.Target.__struct_fields__)
    assert published["properties"]["replacements"]["maxItems"] == grafts.MAX_REPLACEMENTS


@pytest.mark.spec("S-20", 3)
def test_a_higher_profile_wins_and_within_a_profile_the_later_replacement(tmp_path: Path) -> None:
    made = store(tmp_path)
    low = made.create("Low")
    high = made.create("High")  # created last: at the top
    made.add_replacement(low.id, *swap(1, 100))
    made.add_replacement(low.id, *swap(2, 200))
    made.add_replacement(high.id, *swap(1, 111))
    made.add_replacement(high.id, *swap(3, 300))
    made.add_replacement(high.id, *swap(3, 333))  # later in the same profile
    off = made.add_replacement(low.id, *swap(4, 400))
    edited = made.get(low.id).replacements[-1]
    edited.enabled = False
    made.edit_replacement(low.id, edited)
    compiled = made.compile()
    assert compiled.snapshot.swaps() == {1: 111, 2: 200, 3: 333}
    winners = {key: (g.profile, g.value) for key, g in compiled.snapshot.grafts.items()}
    assert winners[(1, None)] == ("High", "111")
    overridden = {
        key: [(g.profile, g.value) for g in value]
        for key, value in compiled.snapshot.overridden.items()
    }
    assert overridden == {(1, None): [("Low", "100")], (3, None): [("High", "300")]}
    assert off.id not in {g.replacement for g in compiled.snapshot.grafts.values()}
    # Moving Low to the top changes the winner.
    made.reorder([low.id, high.id])
    assert made.compile().snapshot.swaps()[1] == 100
    # A disabled profile adds nothing.
    made.set_enabled(low.id, False)
    assert made.compile().snapshot.swaps() == {1: 111, 3: 333}


def test_the_order_is_kept_in_the_setting_and_used_on_load(tmp_path: Path) -> None:
    orders: list[list[str]] = []
    made = grafts.ProfileStore(tmp_path, [], on_order=orders.append, now=lambda: NOW)
    a = made.create("A")
    b = made.create("B")
    assert orders[-1] == [b.id, a.id]
    made.reorder([a.id, b.id])
    assert orders[-1] == [a.id, b.id]
    assert [p.name for p in store(tmp_path, orders[-1]).profiles] == ["A", "B"]
    assert [p.name for p in store(tmp_path, [b.id]).profiles] == ["B", "A"]  # unknown ones last
    assert schema.defaults()["replacements.profile_order"] == []


@pytest.mark.spec("S-20", 4)
def test_undo_and_redo_across_every_kind_of_edit(tmp_path: Path) -> None:
    made = store(tmp_path)

    def files() -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(tmp_path.glob("*.json"))}

    states = [files()]
    a = made.create("A")
    states.append(files())
    b = made.create("B")
    states.append(files())
    item = made.add_replacement(a.id, *swap(1, 2))
    states.append(files())
    item.target.value = "3"
    made.edit_replacement(a.id, item)
    states.append(files())
    made.reorder([a.id, b.id])
    states.append(files())
    made.set_enabled(b.id, False)
    states.append(files())
    made.rename(a.id, "A2")
    states.append(files())
    made.remove_replacement(a.id, item.id)
    states.append(files())
    made.delete(b.id)
    states.append(files())
    order = [p.id for p in made.profiles]
    for state in reversed(states[:-1]):
        made.undo()
        assert files() == state
    assert not made.can_undo
    for state in states[1:]:
        made.redo()
        assert files() == state
    assert [p.id for p in made.profiles] == order
    assert not made.can_redo


def test_undo_keeps_the_last_50_edits_and_a_new_edit_clears_redo(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("A")
    for n in range(60):
        made.add_replacement(profile.id, *swap(n + 1, 1))
    for _ in range(50):
        made.undo()
    assert not made.can_undo
    assert len(made.get(profile.id).replacements) == 10
    made.add_replacement(profile.id, *swap(999, 1))
    assert not made.can_redo


@pytest.mark.spec("S-20", 5)
@pytest.mark.parametrize(
    "name",
    ["", "  ", "a/b", "a\\b", "a:b", 'a"b', "a<b", "a>b", "a|b", "a?b", "a*b", "tab\there",
     "CON", "con.txt", "COM1", "lpt9", "ends.", "ends ", "x" * 101],
)  # fmt: skip
def test_names_that_cant_be_file_names_are_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(grafts.ProfileError):
        store(tmp_path).create(name)
    assert grafts.name_problem(name) is not None


@pytest.mark.spec("S-20", 5)
def test_names_differing_only_in_case_clash(tmp_path: Path) -> None:
    made = store(tmp_path)
    first = made.create("Clean UI")
    with pytest.raises(grafts.ProfileError, match="A profile named clean ui already exists."):
        made.create("clean ui")
    made.rename(first.id, "CLEAN UI")  # its own name in another case is fine
    assert grafts.name_problem("Café — Night 2") is None


@pytest.mark.spec("S-20", 6)
def test_a_damaged_profile_falls_back_to_its_copy(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("A")
    made.add_replacement(profile.id, *swap(1, 2))  # the second write keeps the first as .bak
    (tmp_path / "A.json").write_bytes(b"{ broken")
    [loaded] = store(tmp_path).profiles
    assert (loaded.name, loaded.replacements) == ("A", [])


@pytest.mark.spec("S-20", 6)
def test_a_profile_with_no_readable_copy_is_set_aside_and_the_others_load(
    tmp_path: Path,
) -> None:
    made = store(tmp_path)
    made.create("Good")
    (tmp_path / "Bad.json").write_bytes(b"{ broken")
    reopened = store(tmp_path)
    assert [p.name for p in reopened.profiles] == ["Good"]
    [error] = reopened.unreadable
    assert error.moved.name.startswith("Bad.json.broken-")
    assert error.moved.exists() and not (tmp_path / "Bad.json").exists()


@pytest.mark.spec("S-20", 7)
def test_more_than_10_000_replacements_is_refused_on_save_and_load(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("Big")
    full = made.get(profile.id)
    full.replacements = [
        grafts.Replacement(
            id=str(n), original=Original(asset_id=n + 1), target=Target(kind="remove")
        )
        for n in range(grafts.MAX_REPLACEMENTS)
    ]
    grafts.write_profile(tmp_path / "Big.json", full)
    reopened = store(tmp_path)
    with pytest.raises(grafts.ProfileError, match="at most 10,000 replacements"):
        reopened.add_replacement(profile.id, *swap(1, 2))
    full.replacements.append(full.replacements[0])
    with pytest.raises(grafts.ProfileError):
        grafts.write_profile(tmp_path / "Big.json", full)
    over = json.loads((tmp_path / "Big.json").read_bytes())
    over["replacements"].append(over["replacements"][0])
    with pytest.raises(msgspec.ValidationError):
        grafts.decode(json.dumps(over).encode())


def test_unusable_replacements_are_left_out_with_their_reason(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("A")
    bad_id = made.add_replacement(
        profile.id, Original(asset_id=1), Target(kind="asset_id", value="x")
    )
    http = made.add_replacement(
        profile.id, Original(asset_id=2), Target(kind="url", value="http://x")
    )
    made.add_replacement(profile.id, *swap(3, 4))
    compiled = made.compile()
    assert compiled.snapshot.swaps() == {3: 4}
    assert dict(compiled.left_out) == {
        bad_id.id: "No asset with ID x was found.",
        http.id: "Only HTTPS links are allowed.",
    }


def test_renaming_moves_the_file_and_the_profiles_folder(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("Old")
    (tmp_path / "Old").mkdir()
    (tmp_path / "Old" / "a.png").write_bytes(b"png")
    made.rename(profile.id, "New")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["New", "New.json"]
    assert (tmp_path / "New" / "a.png").read_bytes() == b"png"
