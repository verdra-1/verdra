# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/store_swap.py and its undo (decision record 0028): Roblox's own bytes, swapped safely."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path

import pytest
import zstandard

from tools import roblox_store, store_swap
from verdra.bark import scar
from verdra.soil import humus
from verdra.strata import ochre
from verdra.trunk.branches import fallow, sprout

NOW = datetime(2026, 10, 22, 21, 0, tzinfo=UTC)
#: A header of Roblox's own in front of the KTX2 file (its real layout isn't known; any bytes).
HEADER = b"RBXENTRY" + bytes(8)


def ktx2(width: int, keys: dict[str, str]) -> bytes:
    """A minimal valid KTX2 mip pack: header, index, one level, key/value data, the level."""
    kvd = b""
    for key, value in sorted(keys.items()):
        record = key.encode() + b"\x00" + value.encode() + b"\x00"
        kvd += struct.pack("<I", len(record)) + record + bytes(-len(record) % 4)
    kvd_offset = 48 + 32 + 24
    level_offset = kvd_offset + len(kvd)
    level = bytes([width % 251]) * max(64, width // 2)  # large packs spill to disk
    header = struct.pack(
        "<12s9I", ochre.KTX2_IDENTIFIER, 137, 1, width, width, 0, 0, 1, 1, 0
    ) + struct.pack("<4I2Q", 0, 0, kvd_offset, len(kvd), 0, 0)
    index = struct.pack("<3Q", level_offset, len(level), len(level))
    return header + index + kvd + level


def picture_packs(original: int, top: int, hash_: str) -> dict[int, bytes]:
    """Three packs of one picture, as the CDN sends them (keys identical but packIndex)."""
    keys = {"RobloxOriginalWidth": str(original), "RobloxOriginalHeight": str(original)}
    keys |= {"contentHash": hash_, "pack_0": "4,5", "pack_1": "1,3", "pack_2": "0,1"}
    sizes = {0: top // 16, 1: top // 2, 2: top}
    return {p: ktx2(sizes[p], keys | {"packIndex": str(p)}) for p in (0, 1, 2)}


@pytest.fixture
def store(tmp_path: Path) -> store_swap.Store:
    """A store holding the wall picture (500 x 500), a larger and a smaller one, and noise."""
    root = tmp_path / "Roblox"
    folder = root / roblox_store.FOLDER
    folder.mkdir(parents=True)
    connection = sqlite3.connect(root / roblox_store.DATABASE)
    connection.execute(
        "CREATE TABLE files (id BLOB PRIMARY KEY NOT NULL, content BLOB, size INTEGER DEFAULT 0 "
        "NOT NULL, hits INTEGER DEFAULT 0 NOT NULL, atime INTEGER DEFAULT 0 NOT NULL, category "
        "INTEGER DEFAULT 0 NOT NULL, score INTEGER DEFAULT 0 NOT NULL, ttl INTEGER DEFAULT 0 "
        "NOT NULL)"
    )
    entries: list[bytes] = []
    for original, top, hash_ in ((500, 448, "a" * 32), (1024, 1024, "b" * 32), (64, 64, "c" * 32)):
        for pack, data in picture_packs(original, top, hash_).items():
            body = zstandard.ZstdCompressor().compress(data) if pack == 1 else data
            entries.append(HEADER + body)
    entries.append(b"not a picture at all")
    for number, data in enumerate(entries):
        key = hashlib.md5(f"entry {number}".encode()).digest()  # noqa: S324 - a test key
        if len(data) > 400:  # large entries spill to disk, as on the owner's PC
            shard = folder / key.hex()[:2]
            shard.mkdir(exist_ok=True)
            (shard / key.hex()).write_bytes(data)
            connection.execute("INSERT INTO files (id, size) VALUES (?, ?)", (key, len(data)))
        else:
            connection.execute(
                "INSERT INTO files (id, content, size) VALUES (?, ?, ?)", (key, data, len(data))
            )
    connection.commit()
    connection.close()
    return store_swap.Store(root / roblox_store.DATABASE, folder)


class Platform:
    """Only what the swap and its undo ask: running Roblox programs."""

    def __init__(self, *, players: tuple[int, ...] = ()) -> None:
        self.players = players

    def roblox_processes(self) -> humus.RobloxProcesses:
        return humus.RobloxProcesses(players=self.players)


def contents(store: store_swap.Store) -> dict[str, bytes]:
    with store_swap.reading(store) as connection:
        return {e.name: e.data for e in roblox_store.entries(connection, store.folder)}


def run_swap(store: store_swap.Store, tmp_path: Path) -> tuple[scar.Ledger, tuple[object, ...]]:
    ledger = scar.Ledger(tmp_path / "ledger.json")
    found = store_swap.swap(
        store,
        (500, 500),
        platform=Platform(),  # type: ignore[arg-type]
        ledger=ledger,
        backup_root=tmp_path / "backup",
        now=NOW,
    )
    return ledger, found


def test_the_pictures_are_found_behind_headers_and_compression(
    store: store_swap.Store,
) -> None:
    found = store_swap.pictures(store)
    assert [(p.original, sorted(k for k in p.packs if k is not None)) for p in found] == [
        ((1024, 1024), [0, 1, 2]),
        ((500, 500), [0, 1, 2]),
        ((64, 64), [0, 1, 2]),
    ]
    wall, partner = store_swap.choose(found, (500, 500))
    assert (wall.original, partner.original) == ((500, 500), (1024, 1024))
    text = wall.describe()
    assert text.startswith("picture 2: original 500 x 500, format 137, largest pack 448 px")
    assert not any(key in text for key in contents(store))  # no key is printed


@pytest.mark.spec("S-24", 12)
def test_the_swap_exchanges_every_pack_and_reads_back(
    store: store_swap.Store, tmp_path: Path
) -> None:
    before = contents(store)
    ledger, (wall, partner) = run_swap(store, tmp_path)
    after = contents(store)
    for pack in (0, 1, 2):
        one = wall.packs[pack].name  # type: ignore[attr-defined]
        other = partner.packs[pack].name  # type: ignore[attr-defined]
        assert after[one] == before[other]
        assert after[other] == before[one]
    changed = {name for name in before if before[name] != after[name]}
    assert len(changed) == 6  # nothing else touched
    record = store_swap.open_swap(ledger)
    assert record is not None and record.state == "done"
    assert sorted(p.name for p in (tmp_path / "backup").rglob("*") if p.is_file()) == sorted(
        changed
    )
    assert store_swap.check(store, ledger)[0] == (
        "Swapped entries still as the test wrote them: 6 of 6."
    )


@pytest.mark.spec("S-24", 12)
def test_undo_puts_back_what_roblox_did_not_rewrite(
    store: store_swap.Store, tmp_path: Path
) -> None:
    before = contents(store)
    ledger, (wall, _partner) = run_swap(store, tmp_path)
    rewritten = wall.packs[2]  # type: ignore[attr-defined]
    assert rewritten.path is not None  # the largest pack is a file, as on the owner's PC
    rewritten.path.write_bytes(b"Roblox downloaded it again")
    record = store_swap.open_swap(ledger)
    assert record is not None
    assert "Rewritten by Roblox since: 1." in store_swap.check(store, ledger)[1]
    sprout.restore_store_entries(record, ledger, Platform())  # type: ignore[arg-type]
    after = contents(store)
    assert after[rewritten.name] == b"Roblox downloaded it again"  # Roblox's own now
    assert {n: d for n, d in after.items() if n != rewritten.name} == {
        n: d for n, d in before.items() if n != rewritten.name
    }
    assert store_swap.open_swap(ledger) is None
    assert not (tmp_path / "backup").joinpath(NOW.strftime("%Y-%m-%d %H.%M.%S")).exists()


@pytest.mark.spec("S-24", 12)
def test_nothing_is_written_while_roblox_runs(store: store_swap.Store, tmp_path: Path) -> None:
    before = contents(store)
    ledger = scar.Ledger(tmp_path / "ledger.json")
    with pytest.raises(store_swap.SwapRefusedError):
        store_swap.swap(
            store,
            (500, 500),
            platform=Platform(players=(4242,)),  # type: ignore[arg-type]
            ledger=ledger,
            backup_root=tmp_path / "backup",
        )
    assert contents(store) == before
    assert ledger.entries() == []


@pytest.mark.spec("S-24", 12)
def test_undo_waits_until_roblox_is_closed(store: store_swap.Store, tmp_path: Path) -> None:
    ledger, _found = run_swap(store, tmp_path)
    record = store_swap.open_swap(ledger)
    assert record is not None
    with pytest.raises(sprout.RobloxRunningError):
        sprout.restore_store_entries(record, ledger, Platform(players=(4242,)))  # type: ignore[arg-type]
    assert store_swap.open_swap(ledger) is not None


@pytest.mark.spec("S-24", 12)
def test_an_unknown_store_or_an_unclear_picture_is_refused(
    store: store_swap.Store, tmp_path: Path
) -> None:
    with pytest.raises(store_swap.SwapRefusedError, match="0 pictures have"):
        store_swap.choose(store_swap.pictures(store), (300, 300))
    connection = sqlite3.connect(store.database)
    connection.execute("ALTER TABLE files ADD COLUMN extra INTEGER")
    connection.commit()
    connection.close()
    with pytest.raises(roblox_store.UnknownStoreError):
        store_swap.pictures(store)


def test_a_size_column_that_is_not_the_length_is_refused(
    store: store_swap.Store, tmp_path: Path
) -> None:
    connection = sqlite3.connect(store.database)
    connection.execute("UPDATE files SET size = size + 1")
    connection.commit()
    connection.close()
    before = contents(store)
    with pytest.raises(store_swap.SwapRefusedError, match="size column"):
        run_swap(store, tmp_path)
    assert contents(store) == before


def test_reset_everything_knows_the_swap() -> None:
    assert fallow.undo_actions()[store_swap.KIND] is sprout.restore_store_entries
    assert store_swap.KIND in fallow.kind_names()


def test_the_command_needs_yes_before_it_writes(capsys: pytest.CaptureFixture[str]) -> None:
    assert store_swap.main(["swap", "--original", "500x500"]) == 2
    assert "Add --yes to swap" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        store_swap.main(["plan", "--original", "big"])
