# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-25: each replacement's status, from its saved and applied versions and the loads."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import FakeSettings
from verdra.strata import ochre
from verdra.trunk.branches import grafts
from verdra.trunk.branches.grafts import Original, Status, Target


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Messages are translated through Qt."""


def service(folder: Path) -> grafts.Grafts:
    return grafts.Grafts(folder / "profiles", FakeSettings())


def swap(made: grafts.Grafts, profile_id: str, original: int, target: int) -> str:
    added = made.edit(
        "add_replacement",
        profile_id,
        Original(asset_id=original),
        Target(kind="asset_id", value=str(target)),
    )
    return added.id


def states(made: grafts.Grafts, profile_id: str) -> dict[str, grafts.RowState]:
    return made.states(made.store.get(profile_id))


def edit(made: grafts.Grafts, profile_id: str, row_id: str, **changes: object) -> None:
    row = next(r for r in made.store.get(profile_id).replacements if r.id == row_id)
    for name, value in changes.items():
        setattr(row, name, value)
    made.edit("edit_replacement", profile_id, row)


@pytest.mark.spec("S-25", 1)
def test_each_status_from_the_transitions_of_the_design(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    row = swap(made, profile.id, ABOVE_INT32, 1111111)
    assert states(made, profile.id)[row].status is Status.NEW  # saved, never applied
    made.publish()
    assert states(made, profile.id)[row].status is Status.LIVE  # applied, not loaded yet
    made.loads.record(ABOVE_INT32, 0)
    seen = states(made, profile.id)[row]
    assert (seen.status, seen.loads) == (Status.SEEN, 1)
    edit(made, profile.id, row, target=Target(kind="asset_id", value="2222222"))
    edited = states(made, profile.id)[row]
    assert (edited.status, edited.waiting) == (Status.EDITED, True)
    made.publish()
    assert states(made, profile.id)[row].status is Status.SEEN  # loads count the original
    edit(made, profile.id, row, enabled=False)
    assert states(made, profile.id)[row].status is Status.EDITED  # off, waiting to be applied
    made.publish()
    assert states(made, profile.id)[row].status is Status.OFF
    edit(made, profile.id, row, enabled=True)
    assert states(made, profile.id)[row].status is Status.NEW  # switched on: not applied yet
    made.edit("remove_replacement", profile.id, row)
    assert states(made, profile.id)[row].status is Status.DELETED


def test_a_row_never_applied_and_switched_off_is_off_and_not_waiting(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    row = swap(made, profile.id, ABOVE_INT32, 1111111)
    edit(made, profile.id, row, enabled=False)
    state = states(made, profile.id)[row]
    assert (state.status, state.waiting) == (Status.OFF, False)


def test_a_note_or_name_alone_is_not_a_change(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    row = swap(made, profile.id, ABOVE_INT32, 1111111)
    made.publish()
    edit(made, profile.id, row, note="lobby wall", name="Wall picture")
    state = states(made, profile.id)[row]
    assert (state.status, state.waiting) == (Status.LIVE, False)
    assert made.waiting() == 0


def test_a_row_that_cant_be_used_is_a_problem_with_its_reason(tmp_path: Path) -> None:
    made = service(tmp_path)
    profile = made.edit("create", "A")
    added = made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ABOVE_UINT32),
        Target(kind="file", value=str(tmp_path / "gone.png")),
    )
    state = states(made, profile.id)[added.id]
    assert state.status is Status.PROBLEM and "gone.png" in state.detail


def picture(path: Path, color: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ochre.to_png(ochre.Pixels(64, 64, color * 64 * 64)))


def test_a_changed_file_is_edited_and_a_missing_one_a_problem(tmp_path: Path) -> None:
    """Owner, question N3: changed → Edited with "the file changed"; missing → Problem."""
    made = service(tmp_path)
    profile = made.edit("create", "A")
    wall = tmp_path / "pictures" / "wall.png"
    picture(wall, b"\xff\x00\x00\xff")
    added = made.edit(
        "add_replacement",
        profile.id,
        Original(asset_id=ABOVE_INT32),
        Target(kind="file", value=str(wall)),
    )
    made.publish()
    assert states(made, profile.id)[added.id].status is Status.LIVE
    picture(wall, b"\x00\x00\xff\xff")
    changed = states(made, profile.id)[added.id]
    assert (changed.status, changed.detail) == (
        Status.EDITED,
        "The file changed after it was applied.",
    )
    wall.unlink()
    missing = states(made, profile.id)[added.id]
    assert missing.status is Status.PROBLEM
    assert missing.detail.startswith("The file for this replacement is missing: wall.png.")


def test_a_live_row_that_loses_a_conflict_says_which_profile_wins(tmp_path: Path) -> None:
    """Owner, question N4."""
    made = service(tmp_path)
    low = made.edit("create", "Low")
    high = made.edit("create", "High")
    losing = swap(made, low.id, ABOVE_INT32, 1111111)
    swap(made, high.id, ABOVE_INT32, 2222222)
    made.publish()
    made.loads.record(ABOVE_INT32, 0)
    state = states(made, low.id)[losing]
    assert state.status is Status.LIVE  # not "seen": the other row was loaded
    assert state.detail == "Another replacement for this asset wins (profile High)."


def test_waiting_counts_rows_profile_switches_and_the_order(tmp_path: Path) -> None:
    made = service(tmp_path)
    low = made.edit("create", "Low")
    high = made.edit("create", "High")
    first = swap(made, low.id, ABOVE_INT32, 1111111)
    swap(made, high.id, ABOVE_UINT32, 2222222)
    assert made.waiting() == 2  # two new rows
    made.publish()
    assert made.waiting() == 0
    edit(made, low.id, first, target=Target(kind="asset_id", value="3333333"))
    made.edit("set_enabled", high.id, False)
    made.edit("reorder", [low.id, high.id])
    assert made.waiting() == 3  # an edited row, a profile switch, the order
    made.publish()
    assert made.waiting() == 0
