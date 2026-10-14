# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-26 rules 1 to 4: only what was applied reaches the game.

Before this, three paths published whatever was saved: Verdra's start, a finished link download
and Apply now. Now startup and downloads publish the applied versions, and Apply now makes the
saved versions applied first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import FakeSettings
from verdra.roots import rules
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Target

ORIGINAL = ABOVE_INT32


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Messages are translated through Qt."""


def service(folder: Path, settings: Any = None) -> grafts.Grafts:
    return grafts.Grafts(folder / "profiles", settings or FakeSettings())


def swaps(made: grafts.Grafts) -> dict[int, int]:
    return made.holder.current.swaps()


def picture(path: Path, color: bytes) -> Path:
    from verdra.strata import ochre  # noqa: PLC0415 - only these tests write pictures

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ochre.to_png(ochre.Pixels(64, 64, color * 64 * 64)))
    return path


def first_row(made: grafts.Grafts) -> tuple[str, grafts.Replacement]:
    profile = made.profiles[0]
    return profile.id, made.store.get(profile.id).replacements[0]


@pytest.mark.spec("S-26", 3)
def test_startup_publishes_what_was_applied_not_what_was_saved_since(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.publish()  # Apply now
    profile_id, row = first_row(made)
    row.target = Target(kind="asset_id", value=str(ABOVE_UINT32))
    made.edit("edit_replacement", profile_id, row)  # saved, not applied
    restarted = service(tmp_path)  # Verdra starts again
    restarted.publish_applied()
    assert swaps(restarted) == {ORIGINAL: 1111111}


@pytest.mark.spec("S-26", 3)
def test_a_finished_download_publishes_the_applied_set_only(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.publish()
    profile_id, row = first_row(made)
    row.target = Target(kind="asset_id", value="2222222")
    made.edit("edit_replacement", profile_id, row)  # saved, not applied
    made._downloaded("https://x.example/a.png")  # noqa: SLF001 - a link elsewhere finished
    assert swaps(made) == {ORIGINAL: 1111111}


@pytest.mark.spec("S-26", 1)
def test_apply_now_makes_the_saved_version_live(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.publish()
    profile_id, row = first_row(made)
    row.target = Target(kind="asset_id", value="2222222")
    made.edit("edit_replacement", profile_id, row)
    assert swaps(made) == {ORIGINAL: 1111111}  # edited and saved: the game keeps the old one
    made.publish()
    assert swaps(made) == {ORIGINAL: 2222222}


@pytest.mark.spec("S-26", 4)
def test_an_applied_file_keeps_serving_its_copy_when_the_file_changes_or_goes(
    tmp_path: Path,
) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    wall = picture(tmp_path / "pictures" / "wall.png", b"\xff\x00\x00\xff")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="file", value=str(wall)),
    )
    made.publish()
    served = made.holder.current.content[ORIGINAL].png
    picture(wall, b"\x00\x00\xff\xff")  # the user's file changes
    restarted = service(tmp_path)
    restarted.publish_applied()
    assert restarted.holder.current.content[ORIGINAL].png == served
    wall.unlink()  # and goes
    again = service(tmp_path)
    again.publish_applied()
    assert again.holder.current.content[ORIGINAL].png == served


def test_a_file_missing_at_apply_keeps_the_previous_version_and_says_why(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    wall = picture(tmp_path / "pictures" / "wall.png", b"\xff\x00\x00\xff")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="file", value=str(wall)),
    )
    made.publish()
    served = made.holder.current.content[ORIGINAL].png
    profile_id, row = first_row(made)
    row.target = Target(kind="file", value=str(tmp_path / "pictures" / "gone.png"))
    made.edit("edit_replacement", profile_id, row)
    made.publish()
    assert made.holder.current.content[ORIGINAL].png == served
    assert "is missing" in made.warnings[row.id]


def test_undo_after_apply_changes_saved_versions_only(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    profile_id, row = first_row(made)
    row.target = Target(kind="asset_id", value="2222222")
    made.edit("edit_replacement", profile_id, row)
    made.publish()  # 2222222 is live
    made.edit("undo")  # the saved target goes back to 1111111
    _, saved = first_row(made)
    assert saved.target.value == "1111111"
    assert saved.applied is not None and saved.applied.target.value == "2222222"
    made.publish_applied()
    assert swaps(made) == {ORIGINAL: 2222222}


def test_a_deleted_live_replacement_stays_live_until_applied(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.publish()
    profile_id, row = first_row(made)
    made.edit("remove_replacement", profile_id, row.id)
    [kept] = made.store.get(profile_id).replacements
    assert kept.deleted
    restarted = service(tmp_path)
    restarted.publish_applied()
    assert swaps(restarted) == {ORIGINAL: 1111111}
    assert restarted.preview().changes == 0  # the next apply removes it
    restarted.publish()
    assert swaps(restarted) == {}
    assert restarted.store.get(profile_id).replacements == []


def test_a_replacement_never_applied_is_removed_at_once(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    profile_id, row = first_row(made)
    made.edit("remove_replacement", profile_id, row.id)
    assert made.store.get(profile_id).replacements == []


def test_a_profile_switch_and_order_wait_for_apply(tmp_path: Path) -> None:
    settings = FakeSettings()
    made = service(tmp_path, settings)
    low = made.edit("create", "Low")
    high = made.edit("create", "High")  # on top
    made.edit(
        "add_replacement",
        low.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.edit(
        "add_replacement",
        high.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="2222222"),
    )
    made.publish()
    assert swaps(made) == {ORIGINAL: 2222222}
    assert settings.values["replacements.applied_order"] == [high.id, low.id]
    made.edit("reorder", [low.id, high.id])  # Low on top: not applied yet
    made.edit("set_enabled", high.id, False)
    restarted = service(tmp_path, settings)
    restarted.publish_applied()
    assert swaps(restarted) == {ORIGINAL: 2222222}
    restarted.publish()
    assert swaps(restarted) == {ORIGINAL: 1111111}
    assert settings.values["replacements.applied_order"] == [low.id, high.id]


@pytest.mark.spec("S-26", 9)
def test_applying_prunes_copies_no_applied_version_names(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    red = picture(tmp_path / "pictures" / "red.png", b"\xff\x00\x00\xff")
    blue = picture(tmp_path / "pictures" / "blue.png", b"\x00\x00\xff\xff")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="file", value=str(red)),
    )
    made.publish()
    copies = made.store.copies
    assert len(list(copies.folder.iterdir())) == 1
    profile_id, row = first_row(made)
    row.target = Target(kind="file", value=str(blue))
    made.edit("edit_replacement", profile_id, row)
    [kept] = copies.folder.iterdir()  # saved, not applied: the live copy stays
    assert kept.read_bytes() == red.read_bytes()
    made.publish()
    # Red is still the applied set before, which this apply's Undo puts back (S-27, N6).
    assert sorted(p.read_bytes() for p in copies.folder.iterdir()) == sorted(
        [red.read_bytes(), blue.read_bytes()]
    )
    made.publish()  # the next apply: Undo can only go back to blue now
    [left] = copies.folder.iterdir()
    assert left.read_bytes() == blue.read_bytes()


def test_the_snapshot_holder_starts_empty_before_anything_is_applied(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1111111"),
    )
    made.publish_applied()  # nothing applied yet: saved isn't live
    assert made.holder.current == rules.GraftSnapshot()


@pytest.mark.spec("S-26", 6)
def test_undo_and_redo_cover_every_edit_and_never_touch_an_applied_version(
    tmp_path: Path,
) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    other = made.edit("create", "B")
    for original, target in ((ORIGINAL, 1111111), (ABOVE_UINT32, 2222222), (3333333, 4444444)):
        made.edit(
            "add_replacement",
            profile.id,
            Original(asset_id=original),
            Target(kind="asset_id", value=str(target)),
        )
    made.publish()

    def applied() -> list[object]:
        return [
            (p.id, r.id, r.applied)
            for p in made.store.profiles
            for r in p.replacements
            if r.applied is not None
        ]

    live = applied()
    first, second, third = (r.id for r in made.store.get(profile.id).replacements)
    row = made.store.get(profile.id).replacements[0]
    row.target = Target(kind="asset_id", value="5555555")
    made.edit("edit_replacement", profile.id, row)  # edit
    made.edit("set_replacements_enabled", profile.id, [second], False)  # switch
    made.edit("remove_replacements", profile.id, [third])  # delete
    made.edit("duplicate_replacement", profile.id, first)  # duplicate
    made.edit("move_replacements", profile.id, [second], other.id)  # move
    edited = [r.id for p in made.store.profiles for r in p.replacements]
    for _ in range(5):
        made.edit("undo")
        assert applied() == live
    assert [r.target.value for r in made.store.get(profile.id).replacements] == [
        "1111111",
        "2222222",
        "4444444",
    ]
    assert made.store.get(other.id).replacements == []
    for _ in range(5):
        made.edit("redo")
        assert applied() == live
    assert [r.id for p in made.store.profiles for r in p.replacements] == edited
    assert swaps(made) == {ORIGINAL: 1111111, ABOVE_UINT32: 2222222, 3333333: 4444444}


def test_fifty_steps_of_undo(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ORIGINAL),
        Target(kind="asset_id", value="1"),
    )
    made.publish()
    for value in range(2, 62):
        _, row = first_row(made)
        row.target = Target(kind="asset_id", value=str(value))
        made.edit("edit_replacement", profile.id, row)
    undone = 0
    while made.store.can_undo:
        made.edit("undo")
        undone += 1
    assert undone == 50  # S-20: the last 50 edits
    _, row = first_row(made)
    assert row.target.value == "11"
    assert row.applied is not None and row.applied.target.value == "1"
