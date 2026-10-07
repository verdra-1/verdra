# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-20: replacement profiles (trunk/branches/grafts), and their snapshot (S-21, S-23)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from verdra.roots import rules
from verdra.strata import ochre
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


@pytest.mark.spec("S-20", 1)
def test_real_size_ids_round_trip_compile_and_preview_exactly(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("Big")
    made.add_replacement(profile.id, *swap(ABOVE_UINT32, ABOVE_INT32), asset_type="Image")
    made.add_replacement(profile.id, *swap(ABOVE_INT32, ABOVE_UINT32), asset_type="Image")
    written = (tmp_path / "Big.json").read_bytes()
    assert f'"asset_id": {ABOVE_UINT32}'.encode() in written  # a JSON number, not rounded
    assert grafts.read_profile(tmp_path / "Big.json") == made.get(profile.id)
    snapshot = made.compile().snapshot
    assert snapshot.swaps() == {ABOVE_UINT32: ABOVE_INT32, ABOVE_INT32: ABOVE_UINT32}
    shown = grafts.preview(snapshot)
    assert {row.winner.original for row in shown.groups["Image"]} == {ABOVE_INT32, ABOVE_UINT32}


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


def test_content_targets_that_arent_ready_stay_out_of_the_snapshot(tmp_path: Path) -> None:
    # Routing must decrypt no more than the snapshot needs: a Local file that can't be read and a
    # link that hasn't been downloaded are left out with their reason; Remove is always ready.
    made = store(tmp_path)
    profile = made.create("A")
    left = [
        made.add_replacement(profile.id, Original(asset_id=n), target)
        for n, target in (
            (1, Target(kind="file", value="./a.png")),
            (2, Target(kind="url", value="https://cdn.example/a.png")),
        )
    ]
    made.add_replacement(profile.id, Original(asset_id=3), Target(kind="remove"))
    made.add_replacement(profile.id, *swap(4, 5))
    compiled = made.compile(lambda _url: "not downloaded")
    assert compiled.snapshot.swaps() == {4: 5}
    assert set(compiled.snapshot.content) == {3}
    assert compiled.snapshot.content[3].source == "remove"
    assert compiled.snapshot.hosts() == {rules.ASSET_BATCH_HOST, rules.ASSET_CONTENT_HOST}
    missing = f"The file for this replacement is missing: {tmp_path / 'A' / 'a.png'}."
    assert dict(compiled.left_out) == {left[0].id: missing, left[1].id: "not downloaded"}
    everything = grafts.compile_snapshot(made.profiles, grafts.ALL_KINDS).snapshot
    assert len(everything.grafts) == 4


# --- Target files and links (spec S-22) -----------------------------------------------------------

MP3_FRAME = b"\xff\xfb\x90\x64"  # MPEG-1 layer III, 128 kbit/s, 44.1 kHz


@pytest.mark.spec("S-22", 1)
@pytest.mark.parametrize(
    ("head", "name", "kind"),
    [
        (b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR", "a.obj", "png"),  # content wins over the name
        (b"\xabKTX 20\xbb\r\n\x1a\n", "a.ktx2", "ktx2"),
        (b"\xff\xd8\xff\xe0\0\x10JFIF", "a.jpg", "jpeg"),
        (b"DDS |\0\0\0", "a.dds", "dds"),
        (b"OggS\0\x02", "a.ogg", "ogg"),
        (b"ID3\x04\0\0", "a.mp3", "mp3"),
        (MP3_FRAME + bytes(8), "a.mp3", "mp3"),
        (b"version 2.00\n\x0c\0", "a.mesh", "mesh"),
        (b"version 4.01\n", "a.bin", "mesh"),
        (b"# exported\nv 0 0 0\n", "Model.OBJ", "obj"),
        (b"v 0 0 0\nf 1 2 3\n", "a.txt", None),  # OBJ has no signature: it needs its suffix
        (b"<html>", "a.obj", None),
        (b"\xff\xff\xff\xff", "a.mp3", None),  # not a valid frame header
        (b"\xff\xfb\xf0\x64", "a.mp3", None),  # bitrate index 15 is invalid
        (b"version 9", "a.mesh", None),
        (b"", "a.png", None),
    ],
)
def test_formats_are_told_apart_by_content(head: bytes, name: str, kind: str | None) -> None:
    assert grafts.sniff(head, name) == kind


@pytest.mark.spec("S-22", 1)
def test_a_local_file_must_exist_have_a_supported_format_and_fit_the_limit(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "gone.png"
    assert grafts.file_family(missing) == (
        None,
        f"The file for this replacement is missing: {missing}.",
    )
    assert grafts.file_family(tmp_path)[0] is None  # a folder isn't a file
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    assert grafts.file_family(text) == (
        None,
        "This file type isn't supported. Use PNG, JPEG, KTX2, OBJ, MESH, OGG or MP3.",
    )
    sound = tmp_path / "a.ogg"
    with sound.open("wb") as file:
        file.write(b"OggS")
        file.truncate(50 * 1024 * 1024)  # sparse: exactly the limit is allowed
    assert grafts.file_family(sound) == ("Audio", None)
    with sound.open("r+b") as file:
        file.truncate(50 * 1024 * 1024 + 1)
    assert grafts.file_family(sound) == (None, "This file is too big. The limit is 50 MB.")
    picture = tmp_path / "a.png"
    picture.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert grafts.file_family(picture) == ("Image", None)
    assert grafts.target_problem("file", "", tmp_path) == "Choose a file to use instead."
    assert grafts.target_problem("file", "./a.png", tmp_path) is None
    assert grafts.target_problem("remove", "", tmp_path) is None


@pytest.mark.spec("S-22", 1)
@pytest.mark.parametrize(
    ("link", "allowed"),
    [
        ("https://cdn.example/a.png", True),
        ("HTTPS://cdn.example/a.png", True),
        ("http://cdn.example/a.png", False),
        ("https://", False),
        ("https:///a.png", False),
        ("ftp://cdn.example/a.png", False),
        ("file:///C:/a.png", False),
        ("cdn.example/a.png", False),
    ],
)
def test_only_https_links_with_a_host_are_allowed(link: str, allowed: bool) -> None:  # noqa: FBT001
    problem = grafts.target_problem("url", link, Path())
    assert problem == (None if allowed else "Only HTTPS links are allowed.")


@pytest.mark.spec("S-22", 2)
def test_a_file_inside_the_profile_folder_is_stored_relative(tmp_path: Path) -> None:
    folder = tmp_path / "profiles" / "Night"
    inside = folder / "sky" / "top.png"
    outside = tmp_path / "elsewhere" / "top.png"
    assert grafts.stored_path(inside, folder) == "./sky/top.png"
    assert grafts.resolve("./sky/top.png", folder) == inside
    assert grafts.stored_path(outside, folder) == str(outside)
    assert grafts.resolve(str(outside), folder) == outside
    # A sibling whose name starts with the folder's name is outside it.
    assert grafts.stored_path(tmp_path / "profiles" / "Night2" / "a.png", folder).startswith(
        str(tmp_path)
    )


def test_renaming_moves_the_file_and_the_profiles_folder(tmp_path: Path) -> None:
    made = store(tmp_path)
    profile = made.create("Old")
    (tmp_path / "Old").mkdir()
    (tmp_path / "Old" / "a.png").write_bytes(b"png")
    made.rename(profile.id, "New")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["New", "New.json"]
    assert (tmp_path / "New" / "a.png").read_bytes() == b"png"


@pytest.mark.spec("S-23", 1)
def test_the_preview_is_the_snapshot_with_its_conflicts(tmp_path: Path) -> None:
    made = store(tmp_path)
    low = made.create("Low")
    high = made.create("High")
    made.add_replacement(low.id, *swap(1, 100), asset_type="Image")
    made.add_replacement(low.id, Original(asset_id=2), Target(kind="remove"), asset_type="Mesh")
    made.add_replacement(high.id, *swap(1, 111), asset_type="Image")
    made.add_replacement(high.id, *swap(1, 112), asset_type="Image")  # later in High: wins
    made.add_replacement(
        high.id, Original(asset_id=3, slot="normal"), Target(kind="file", value="./n.png"),
        asset_type="TexturePack",
    )  # fmt: skip
    snapshot = grafts.compile_snapshot(made.profiles, grafts.ALL_KINDS).snapshot
    shown = grafts.preview(snapshot)
    # Same winners as the snapshot the proxy uses, grouped by type.
    winners = {
        (r.winner.original, r.winner.slot): r.winner for g in shown.groups.values() for r in g
    }
    assert winners == dict(snapshot.grafts)
    assert list(shown.groups) == ["Image", "Mesh", "TexturePack"]
    [image] = shown.groups["Image"]
    assert (image.winner.profile, image.winner.value) == ("High", "112")
    assert [(g.profile, g.value) for g in image.overridden] == [("High", "111"), ("Low", "100")]
    # Three originals change; one of them has a conflict (counted once, not twice).
    assert (shown.changes, shown.conflicts) == (3, 1)
    assert grafts.preview(rules.GraftSnapshot()) == grafts.Preview({}, 0, 0)


# --- Local file content, prepared when the snapshot is built (S-21 rule 2) --------------------


def file_graft(value: str, slot: str | None = None) -> rules.Graft:
    return rules.Graft(ABOVE_UINT32, slot, "file", value, "A", "r", "Image")  # type: ignore[arg-type]


def test_a_local_picture_is_prepared_as_png_and_ktx2_with_the_same_pixels(tmp_path: Path) -> None:
    pixels = ochre.Pixels(2, 2, bytes(range(16)))
    (tmp_path / "wall.png").write_bytes(ochre.to_png(pixels))
    content = grafts.prepare_content(file_graft("./wall.png"), tmp_path)
    assert isinstance(content, rules.Content)
    assert content.source == "file"
    assert ochre.read_image(content.png) == pixels
    assert ochre.read_ktx2(content.ktx2) == pixels


@pytest.mark.parametrize(
    ("name", "data", "reason"),
    [
        ("gone.png", None, "The file for this replacement is missing: {path}."),
        (
            "broken.png",
            b"\x89PNG\r\n\x1a\nnot really",
            "This file couldn't be used: the image data",
        ),
        ("model.mesh", b"version 2.00\n", "This part of Verdra isn't built yet."),
        ("sound.ogg", b"OggS\0\x02", "This part of Verdra isn't built yet."),
    ],
)
def test_a_file_that_cant_be_served_is_left_out_with_its_reason(
    tmp_path: Path, name: str, data: bytes | None, reason: str
) -> None:
    if data is not None:
        (tmp_path / name).write_bytes(data)
    problem = grafts.prepare_content(file_graft(f"./{name}"), tmp_path)
    assert isinstance(problem, str)
    assert problem.startswith(reason.format(path=tmp_path / name).split(" {")[0])


def test_a_slot_with_a_file_isnt_served_yet(tmp_path: Path) -> None:
    problem = grafts.prepare_content(file_graft("./a.png", "normal"), tmp_path)
    assert problem == "This part of Verdra isn't built yet. It will arrive in a later version."


def test_a_later_asset_id_replacement_wins_over_a_file_and_drops_its_content(
    tmp_path: Path,
) -> None:
    made = store(tmp_path)
    low, high = made.create("Low"), made.create("High")
    (tmp_path / "Low").mkdir()
    (tmp_path / "Low" / "a.png").write_bytes(ochre.to_png(ochre.Pixels(1, 1, b"\0\0\0\xff")))
    made.add_replacement(
        low.id, Original(asset_id=ABOVE_UINT32), Target(kind="file", value="./a.png")
    )
    assert ABOVE_UINT32 in made.compile().snapshot.content
    made.add_replacement(high.id, *swap(ABOVE_UINT32, ABOVE_INT32))
    compiled = grafts.compile_snapshot([made.get(high.id), made.get(low.id)], folder=tmp_path)
    assert compiled.snapshot.swaps() == {ABOVE_UINT32: ABOVE_INT32}
    assert ABOVE_UINT32 not in compiled.snapshot.content
