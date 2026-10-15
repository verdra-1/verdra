# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-27 in trunk: the review's changes, applying only the chosen ones, and Undo."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import FakeSettings
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import ORDER, PROFILE_KEY, Original, Target


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Messages are translated through Qt."""


def service(folder: Path) -> grafts.Grafts:
    return grafts.Grafts(folder / "profiles", FakeSettings())


def swap(made: grafts.Grafts, profile_id: str, original: int, target: int | str) -> str:
    kind = "asset_id" if isinstance(target, int) else "file"
    added = made.edit(
        "add_replacement",
        profile_id,
        Original(asset_id=original),
        Target(kind=kind, value=str(target)),
        "Image",
    )
    return added.id


def edit(made: grafts.Grafts, profile_id: str, row_id: str, **changes: object) -> None:
    row = next(r for r in made.store.get(profile_id).replacements if r.id == row_id)
    for name, value in changes.items():
        setattr(row, name, value)
    made.edit("edit_replacement", profile_id, row)


def lines(made: grafts.Grafts) -> list[tuple[str, str]]:
    return [(change.kind, change.detail) for change in made.pending_changes()]


@pytest.mark.spec("S-27", 1)
def test_every_kind_of_change_is_listed_once_and_counted_the_same(tmp_path: Path) -> None:
    made = service(tmp_path)
    low = made.edit("create", "Low")
    high = made.edit("create", "High")  # on top
    edited = swap(made, low.id, ABOVE_INT32, 1111111)
    moved = swap(made, low.id, ABOVE_UINT32, 2222222)
    off = swap(made, low.id, 3333333, 4444444)
    deleted = swap(made, low.id, 5555555, 6666666)
    on = swap(made, low.id, 7777777, 8888888)
    edit(made, low.id, on, enabled=False)
    swap(made, high.id, 9999999, 1212121)
    made.publish()
    assert lines(made) == []
    edit(made, low.id, edited, target=Target(kind="asset_id", value="1313131"))
    edit(made, low.id, moved, original=Original(asset_id=1414141))
    edit(made, low.id, off, enabled=False)
    edit(made, low.id, on, enabled=True)
    made.edit("remove_replacement", low.id, deleted)
    edit(made, low.id, edited, note="only a note")  # never a change (rule 2)
    swap(made, low.id, 1515151, 1616161)  # new
    swap(made, low.id, 1717171, str(tmp_path / "gone.png"))  # problem
    made.edit("set_enabled", high.id, False)
    made.edit("reorder", [low.id, high.id])  # no asset in both: no winner changes
    assert lines(made) == [
        ("changed", "Edited: asset 1111111 → asset 1313131"),
        ("changed", f"Stops replacing {ABOVE_UINT32}, starts replacing 1414141."),
        ("off", "Turned off: goes back to the original image."),
        ("deleted", "Deleted: goes back to the original image."),
        ("on", "Turned on: asset 8888888"),
        ("new", "New: asset 1616161"),
        (
            "problem",
            f"The file for this replacement is missing: {tmp_path / 'gone.png'}. Fix it or turn "
            "the row off. It will be skipped.",
        ),
        ("profile_off", "Profile High turning off: 1 replacements go back to the originals."),
        ("order", "Profile order changed; no asset changes."),
    ]
    assert made.waiting() == len(lines(made))


def test_a_reorder_that_changes_a_winner_says_which_asset(tmp_path: Path) -> None:
    made = service(tmp_path)
    low = made.edit("create", "Low")
    high = made.edit("create", "High")
    swap(made, low.id, ABOVE_INT32, 1111111)
    swap(made, high.id, ABOVE_INT32, 2222222)
    made.publish()
    made.edit("reorder", [low.id, high.id])
    assert lines(made) == [("winner", f"Asset {ABOVE_INT32} now comes from profile Low.")]
    assert made.waiting() == 1
    made.apply([ORDER])
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111}


@pytest.mark.spec("S-27", 2)
@pytest.mark.spec("S-27", 3)
def test_applying_the_checked_changes_leaves_the_others_waiting(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    first = swap(made, profile.id, ABOVE_INT32, 1111111)
    second = swap(made, profile.id, ABOVE_UINT32, 2222222)
    made.publish()
    edit(made, profile.id, first, target=Target(kind="asset_id", value="3333333"))
    edit(made, profile.id, second, target=Target(kind="asset_id", value="4444444"))
    made.apply([first])
    assert made.holder.current.swaps() == {ABOVE_INT32: 3333333, ABOVE_UINT32: 2222222}
    states = made.states(made.store.get(profile.id))
    assert states[first].status is grafts.Status.LIVE
    assert states[second].status is grafts.Status.EDITED  # still waiting
    assert [c.key for c in made.pending_changes()] == [second]


def test_a_new_profile_applied_without_the_order_goes_where_it_is(tmp_path: Path) -> None:
    made = service(tmp_path)
    low = made.edit("create", "Low")
    swap(made, low.id, ABOVE_INT32, 1111111)
    made.publish()
    high = made.edit("create", "High")  # on top, never applied
    row = swap(made, high.id, ABOVE_INT32, 2222222)
    made.apply([row])  # its row, not the order
    assert made.holder.current.swaps() == {ABOVE_INT32: 2222222}
    assert made.store.applied_order == [high.id, low.id]
    assert made.pending_changes() == []


@pytest.mark.spec("S-27", 4)
def test_undo_puts_the_applied_set_before_back_and_a_second_apply_ends_it(
    tmp_path: Path,
) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    kept = swap(made, profile.id, ABOVE_INT32, 1111111)
    gone = swap(made, profile.id, ABOVE_UINT32, 2222222)
    made.publish()
    edit(made, profile.id, kept, target=Target(kind="asset_id", value="3333333"))
    made.edit("remove_replacement", profile.id, gone)
    swap(made, profile.id, 5555555, 6666666)
    made.publish()
    applies = made.store.applies
    assert made.holder.current.swaps() == {ABOVE_INT32: 3333333, 5555555: 6666666}
    assert made.undo_apply(applies)
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111, ABOVE_UINT32: 2222222}
    # Saved versions stay: the rows wait again (question N6).
    assert sorted(kind for kind, _detail in lines(made)) == ["changed", "deleted", "new"]
    assert not made.undo_apply(applies)  # one level
    made.publish()
    applies = made.store.applies
    made.publish()  # a second apply
    assert not made.undo_apply(applies)  # M-REVIEW-12


@pytest.mark.spec("S-27", 5)
def test_a_problem_row_is_skipped_and_its_applied_version_stays(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    row = swap(made, profile.id, ABOVE_INT32, 1111111)
    made.publish()
    edit(made, profile.id, row, target=Target(kind="file", value=str(tmp_path / "gone.png")))
    [change] = made.pending_changes()
    assert change.kind == "problem"
    made.apply()
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111}  # still served
    assert "is missing" in made.warnings[row]
    saved = made.store.get(profile.id).replacements[0]
    assert saved.applied is not None and saved.applied.target.value == "1111111"


def test_a_profile_switch_waits_for_its_own_line(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    swap(made, profile.id, ABOVE_INT32, 1111111)
    made.publish()
    made.edit("set_enabled", profile.id, False)
    [change] = made.pending_changes()
    assert change.key == f"{PROFILE_KEY}{profile.id}"
    made.apply([])  # nothing chosen
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111}
    made.apply([change.key])
    assert made.holder.current.swaps() == {}


def test_deleting_an_applied_profile_waits_for_apply(tmp_path: Path) -> None:
    """S-27 (pull request f3): the game keeps a deleted profile until its deletion is applied,
    also across a restart of Verdra."""
    made = service(tmp_path)
    profile = made.edit("create", "Night")
    swap(made, profile.id, ABOVE_INT32, 1111111)
    made.publish()
    made.edit("delete", profile.id)
    assert made.profiles == []  # gone from the list and the header
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111}
    assert lines(made) == [
        ("profile_deleted", "Profile Night deleted: 1 replacements go back to the originals.")
    ]
    restarted = service(tmp_path)
    restarted.publish_applied()
    assert restarted.holder.current.swaps() == {ABOVE_INT32: 1111111}
    assert restarted.profiles == []
    with pytest.raises(grafts.ProfileError, match="Apply its deletion first"):
        restarted.edit("create", "night")
    restarted.apply()
    assert restarted.holder.current.swaps() == {}
    assert not (tmp_path / "profiles" / "Night.json").exists()
    restarted.edit("create", "Night")  # the name is free again


def test_undo_takes_a_waiting_deletion_back(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "Night")
    swap(made, profile.id, ABOVE_INT32, 1111111)
    made.publish()
    kept = made.store.get(profile.id)
    made.edit("delete", profile.id)
    made.edit("restore_profile", kept, 0)  # the toast's Undo (M-PROF-09)
    assert [p.id for p in made.profiles] == [profile.id]
    assert made.pending_changes() == []


def test_a_profile_never_applied_goes_at_once(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "Night")
    swap(made, profile.id, ABOVE_INT32, 1111111)
    made.edit("delete", profile.id)
    assert made.store.profiles == []
    assert made.pending_changes() == []


def test_undo_of_an_apply_brings_a_deleted_profile_back_as_deleted(tmp_path: Path) -> None:
    made = service(tmp_path)
    low = made.edit("create", "Low")
    night = made.edit("create", "Night")
    swap(made, night.id, ABOVE_INT32, 1111111)
    swap(made, low.id, ABOVE_UINT32, 2222222)
    made.publish()
    made.edit("delete", night.id)
    made.apply()
    assert made.holder.current.swaps() == {ABOVE_UINT32: 2222222}
    assert made.undo_apply(made.store.applies)
    assert made.holder.current.swaps() == {ABOVE_INT32: 1111111, ABOVE_UINT32: 2222222}
    assert [p.id for p in made.profiles] == [low.id]  # still deleted: it waits again
    assert [c.kind for c in made.pending_changes()] == ["profile_deleted"]


def test_reordering_the_shown_profiles_keeps_a_deleted_ones_place(tmp_path: Path) -> None:
    made = service(tmp_path)
    a = made.edit("create", "A")
    b = made.edit("create", "B")
    c = made.edit("create", "C")  # order: C, B, A
    swap(made, b.id, ABOVE_INT32, 1111111)
    made.publish()
    made.edit("delete", b.id)
    made.edit("reorder", [a.id, c.id])
    assert [p.id for p in made.store.profiles] == [a.id, b.id, c.id]


def picture(path: Path, width: int, height: int) -> Path:
    from verdra.strata import ochre  # noqa: PLC0415 - only these tests write pictures

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        ochre.to_png(ochre.Pixels(width, height, b"\xff\x00\x00\xff" * width * height))
    )
    return path


def test_the_review_pictures_are_what_the_next_apply_serves(tmp_path: Path) -> None:
    """S-27 (pull request f4): the prepared picture, not a second conversion; scaled is said."""
    made = service(tmp_path)
    profile = made.edit("create", "A")
    small = swap(made, profile.id, ABOVE_INT32, str(picture(tmp_path / "p" / "small.png", 64, 64)))
    wide = swap(made, profile.id, ABOVE_UINT32, str(picture(tmp_path / "p" / "wide.png", 2048, 16)))
    swap(made, profile.id, 3333333, 4444444)  # an ID swap: no picture to show
    found: list[dict[str, grafts.ReviewPicture]] = []
    made.pictures(found.append)
    [pictures] = found
    assert set(pictures) == {small, wide}
    assert (pictures[small].size, pictures[small].scaled) == ((64, 64), False)
    # Within 1024 a side, each side a multiple of 64 (strata/ochre): 2048 x 16 is served 1024 x 64.
    assert (pictures[wide].size, pictures[wide].served) == ((2048, 16), (1024, 64))
    assert pictures[wide].scaled
    made.publish()
    assert made.holder.current.content[ABOVE_INT32].png == pictures[small].png
    families = {c.replacement_id: c.family for c in made.pending_changes()}
    assert families == {}  # all applied now


def test_a_line_names_its_family_for_the_icon(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    row = swap(made, profile.id, ABOVE_INT32, 1111111)  # added as "Image"
    [change] = made.pending_changes()
    assert (change.replacement_id, change.family) == (row, "Image")
