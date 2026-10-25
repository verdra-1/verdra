# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The store-swap test of decision record 0028: does the Player check what it reads from disk?

Approved by the owner on 22 October 2026. It uses only bytes Roblox itself saved, in a store
Apply now has just emptied (the real one is in Verdra's backup):

    plan    read-only: list the pictures in the store and say which two would be swapped
    swap    swap every mip pack of the wall picture with another picture's packs
    check   read-only, after the next join: are the swapped bytes still there?
    undo    put the original bytes back (Reset everything does the same)

The wall picture is the one whose KTX2 keys give the original size passed with `--original`
(15553230204 is 500 x 500, decision record 0022's evidence); the asset ID isn't in the store.
The partner is the largest other picture with the same packs.

Safety, as decision record 0028 sets out:
- `swap` refuses while a Roblox Player or Studio runs, and refuses a store that isn't laid out
  as observed (tools/roblox_store).
- Before writing, each touched entry's bytes go to a backup folder, and the change is in the
  ledger as `roblox_store_swapped`, so Reset everything and `undo` put them back
  (trunk/branches/sprout).
- Every write is read back. The tool prints only sizes, formats and counts, never content.

    uv run python -m tools.store_swap plan --original 500x500
    uv run python -m tools.store_swap swap --original 500x500 --yes
    uv run python -m tools.store_swap check
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # run as a file (`python tools\store_swap.py`), not only with -m

from tools import roblox_store  # noqa: E402
from verdra.bark import scar  # noqa: E402
from verdra.soil import atomic, humus, terrain  # noqa: E402
from verdra.trunk.branches import sprout  # noqa: E402

KIND: Final = "roblox_store_swapped"
#: Where the swapped entries' original bytes are kept, next to the cache backups.
BACKUP_FOLDER: Final = "Roblox store swap test"


class SwapRefusedError(RuntimeError):
    """The swap can't be done safely; nothing was written."""


@dataclass(frozen=True, slots=True)
class Store:
    """Where Roblox's saved assets are."""

    database: Path
    folder: Path


@dataclass(frozen=True, slots=True)
class PictureEntries:
    """One picture: its mip packs' entries, keyed by pack number (None for a single one)."""

    number: int
    original: tuple[int, int] | None
    vk_format: int
    largest: int
    packs: dict[int | None, roblox_store.Entry]

    def describe(self) -> str:
        size = f"{self.original[0]} x {self.original[1]}" if self.original else "unknown size"
        kinds = sorted("file" if e.path else "inline" for e in self.packs.values())
        packs = ", ".join(str(p) for p in sorted(p for p in self.packs if p is not None))
        return (
            f"picture {self.number}: original {size}, format {self.vk_format}, "
            f"largest pack {self.largest} px, packs {packs or 'one'} ({', '.join(kinds)})"
        )


def live_store(platform: humus.Platform | None = None) -> Store:
    """Return the store the platform reports (S-24's cache names)."""
    files = (platform or humus.current()).roblox_cache_files()
    if isinstance(files, humus.Unsupported) or not files:
        msg = "Roblox's saved assets weren't found"
        raise SwapRefusedError(msg)
    by_name = {path.name: path for path in files}
    database = by_name.get(roblox_store.DATABASE)
    if database is None:
        msg = f"there is no {roblox_store.DATABASE}"
        raise SwapRefusedError(msg)
    return Store(database, database.with_name(roblox_store.FOLDER))


@contextlib.contextmanager
def reading(store: Store) -> Iterator[sqlite3.Connection]:
    """A read-only connection to a private copy of the database (the live one isn't touched)."""
    with tempfile.TemporaryDirectory() as scratch:
        for suffix in ("", "-wal", "-shm"):
            part = store.database.with_name(store.database.name + suffix)
            if part.is_file():
                shutil.copy2(part, Path(scratch) / part.name)
        target = Path(scratch) / store.database.name
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            yield connection
        finally:
            connection.close()


def pictures(store: Store) -> list[PictureEntries]:
    """Every picture in the store, largest first."""
    groups: dict[str, list[tuple[roblox_store.Entry, roblox_store.Picture]]] = {}
    with reading(store) as connection:
        for entry in roblox_store.entries(connection, store.folder):
            found = roblox_store.picture(entry.data)
            if found is not None:
                groups.setdefault(found.group, []).append((entry, found))
    result: list[PictureEntries] = []
    for members in groups.values():
        packs = {found.pack: entry for entry, found in members}
        if len(packs) != len(members):
            continue  # two entries claim one pack: not a picture this test understands
        first = members[0][1]
        result.append(
            PictureEntries(
                0,
                first.original,
                first.vk_format,
                max(found.width for _entry, found in members),
                packs,
            )
        )
    result.sort(key=lambda p: (-p.largest, sorted(e.name for e in p.packs.values())))
    return [
        PictureEntries(n, p.original, p.vk_format, p.largest, p.packs)
        for n, p in enumerate(result, 1)
    ]


def choose(found: list[PictureEntries], original: tuple[int, int]) -> tuple[PictureEntries, ...]:
    """The wall picture (the one of that original size) and its partner, or a refusal."""
    walls = [p for p in found if p.original == original]
    if len(walls) != 1:
        msg = (
            f"{len(walls)} pictures have the original size {original[0]} x {original[1]}; "
            "exactly one is needed"
        )
        raise SwapRefusedError(msg)
    wall = walls[0]
    partners = [p for p in found if p is not wall and set(p.packs) == set(wall.packs)]
    if not partners:
        msg = "no other picture has the same packs as the wall picture"
        raise SwapRefusedError(msg)
    return wall, partners[0]


def swap(
    store: Store,
    original: tuple[int, int],
    *,
    platform: humus.Platform | None = None,
    ledger: scar.Ledger | None = None,
    backup_root: Path | None = None,
    now: datetime | None = None,
) -> tuple[PictureEntries, PictureEntries]:
    """Swap the wall picture's packs with its partner's; return the two pictures."""
    running = (platform or humus.current()).roblox_processes()
    if isinstance(running, humus.Unsupported) or running.any:
        msg = "close every Roblox Player and Roblox Studio first"
        raise SwapRefusedError(msg)
    wall, partner = choose(pictures(store), original)
    pairs = [(wall.packs[p], partner.packs[p]) for p in wall.packs]
    for entry in (e for pair in pairs for e in pair):
        if entry.size != len(entry.data):
            msg = "the size column isn't the entry's length; the store isn't understood"
            raise SwapRefusedError(msg)
    moment = now or datetime.now(UTC)
    root = backup_root or terrain.config_dir() / BACKUP_FOLDER
    backup = root / moment.strftime("%Y-%m-%d %H.%M.%S")
    backup.mkdir(parents=True)
    writes: list[tuple[roblox_store.Entry, bytes]] = []
    for one, other in pairs:
        writes += [(one, other.data), (other, one.data)]
    for entry, _data in writes:
        (backup / entry.name).write_bytes(entry.data)
    ledger = ledger or scar.Ledger()
    record = ledger.begin(
        KIND,
        str(store.database),
        {
            "database": str(store.database),
            "backup": str(backup),
            "entries": [
                {
                    "key": entry.name,
                    "path": str(entry.path) if entry.path else None,
                    "written": hashlib.sha256(data).hexdigest(),
                }
                for entry, data in writes
            ],
        },
    )
    _write(store, writes)
    for entry, data in writes:
        if _current(store, entry) != data:
            ledger.mark(record.id, "failed", error="a write didn't read back")
            msg = "a write didn't read back as written; run undo"
            raise SwapRefusedError(msg)
    ledger.mark(record.id, "done")
    return wall, partner


def _write(store: Store, writes: list[tuple[roblox_store.Entry, bytes]]) -> None:
    connection = sqlite3.connect(store.database)
    try:
        with connection:
            for entry, data in writes:
                if entry.path is None:
                    connection.execute(
                        "UPDATE files SET content = ?, size = ? WHERE id = ?",
                        (data, len(data), entry.key),
                    )
                else:
                    atomic.write_atomic(entry.path, data)
                    connection.execute(
                        "UPDATE files SET size = ? WHERE id = ?", (len(data), entry.key)
                    )
    finally:
        connection.close()


def _current(store: Store, entry: roblox_store.Entry) -> bytes | None:
    if entry.path is not None:
        return entry.path.read_bytes() if entry.path.is_file() else None
    connection = sqlite3.connect(f"file:{store.database.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT content FROM files WHERE id = ?", (entry.key,)).fetchone()
    finally:
        connection.close()
    return bytes(row[0]) if row and row[0] is not None else None


def open_swap(ledger: scar.Ledger) -> scar.Entry | None:
    """The newest swap Reset everything would still undo, if any."""
    return next((e for e in ledger.open_entries() if e.kind == KIND), None)


def check(store: Store, ledger: scar.Ledger) -> list[str]:
    """Read-only: how many swapped entries still hold what the test wrote."""
    record = open_swap(ledger)
    if record is None:
        return ["No store-swap test is in place."]
    kept = rewritten = gone = 0
    with reading(store) as connection:
        present = {e.name: e for e in roblox_store.entries(connection, store.folder)}
    for item in record.details["entries"]:
        entry = present.get(item["key"])
        if entry is None:
            gone += 1
        elif hashlib.sha256(entry.data).hexdigest() == item["written"]:
            kept += 1
        else:
            rewritten += 1
    total = len(record.details["entries"])
    return [
        f"Swapped entries still as the test wrote them: {kept} of {total}.",
        f"Rewritten by Roblox since: {rewritten}. No longer in the store: {gone}.",
    ]


def _size(text: str) -> tuple[int, int]:
    width, _, height = text.lower().partition("x")
    if not width.strip().isdigit() or not height.strip().isdigit():
        msg = "give the original size as WIDTHxHEIGHT, for example 500x500"
        raise argparse.ArgumentTypeError(msg)
    return int(width), int(height)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=("plan", "swap", "check", "undo"))
    parser.add_argument("--original", type=_size, default=(500, 500))
    parser.add_argument("--yes", action="store_true", help="confirm the swap (it writes)")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return _run(arguments.command, arguments.original, confirmed=arguments.yes)
    except (SwapRefusedError, roblox_store.UnknownStoreError, sprout.RobloxRunningError) as error:
        print(f"Nothing was changed: {error}.", file=sys.stderr)
        return 2


def _run(command: str, original: tuple[int, int], *, confirmed: bool) -> int:
    ledger = scar.Ledger()
    if command == "undo":
        record = open_swap(ledger)
        if record is None:
            print("No store-swap test is in place.")
            return 0
        sprout.restore_store_entries(record, ledger)
        print("The swapped entries hold their own bytes again.")
        return 0
    if command == "swap" and not confirmed:
        print("Add --yes to swap (it writes into Roblox's saved assets).", file=sys.stderr)
        return 2
    store = live_store()
    if command == "check":
        print("\n".join(check(store, ledger)))
        return 0
    if command == "plan":
        found = pictures(store)
        print(f"{len(found)} pictures in the store:")
        print("\n".join(p.describe() for p in found))
        wall, partner = choose(found, original)
        print(f"Would swap picture {wall.number} (the wall) with picture {partner.number}.")
        return 0
    wall, partner = swap(store, original, ledger=ledger)
    print(wall.describe())
    print(partner.describe())
    print(
        f"Swapped {len(wall.packs)} packs of picture {wall.number} with picture "
        f"{partner.number}; every write read back as written."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
