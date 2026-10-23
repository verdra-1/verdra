# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Read Roblox's saved assets, as observed on the owner's PC (decision record 0028).

The owner's store report of 22 October 2026 showed what this module relies on, and nothing
more:
- `rbx-storage.db` holds one table, `files`, keyed by a 16-byte `id`. Its columns are
  `content`, `size`, `hits`, `atime`, `category`, `score` and `ttl`. SQLite's own statistics
  table `sqlite_stat1` may sit beside it (seen 23 October 2026).
- `content` holds an entry's bytes inline, or is NULL when the bytes sit in the `rbx-storage`
  folder: one level deep, in a file named by the id in hex.

`recognize` checks exactly that shape and refuses anything else, so a Roblox update that
changes the store stops the tools instead of misleading them.

A picture entry holds a KTX2 file Roblox's CDN sent (decision record 0022), possibly behind a
header of Roblox's own, possibly zstd-compressed; `picture` finds it by its identifier and reads
the keys that tell pictures and their mip packs apart (RobloxOriginalWidth/Height, packIndex,
contentHash). Used by tools/inspect_store.py and tools/store_swap.py; not part of the app.
"""

from __future__ import annotations

import io
import sqlite3
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import zstandard

from verdra.strata import ochre

DATABASE: Final = "rbx-storage.db"
FOLDER: Final = "rbx-storage"
TABLE: Final = "files"
#: The columns observed on 22 October 2026, in order.
COLUMNS: Final = ("id", "content", "size", "hits", "atime", "category", "score", "ttl")
#: Tables SQLite makes for itself (statistics, autoincrement counters); no program may use it.
SQLITE_PREFIX: Final = "sqlite_"
KEY_LENGTH: Final = 16
ZSTD_MAGIC: Final = b"\x28\xb5\x2f\xfd"
#: How far into an entry its KTX2 file or zstd frame may start (a header of Roblox's own).
SEARCH: Final = 4096
#: How much of a compressed entry is decoded to read its KTX2 header and keys.
HEAD_DECODED: Final = 1024 * 1024
_U32 = struct.Struct("<I")


class UnknownStoreError(ValueError):
    """The store isn't laid out as observed on 22 October 2026; nothing is read or written."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One saved asset: its key, its bytes and where they live."""

    key: bytes
    data: bytes
    #: The file holding the bytes, or None when they are inline in the database.
    path: Path | None
    #: The `size` column.
    size: int

    @property
    def name(self) -> str:
        return self.key.hex()


@dataclass(frozen=True, slots=True)
class Picture:
    """A KTX2 mip pack found inside an entry."""

    #: Where the KTX2 file or its zstd frame starts in the entry (the header's length).
    offset: int
    compressed: bool
    vk_format: int
    width: int
    height: int
    levels: int
    original: tuple[int, int] | None
    pack: int | None
    #: The keys Roblox writes; identical across one picture's packs (8 October 2026).
    group: str


def recognize(connection: sqlite3.Connection) -> None:
    """Raise UnknownStoreError unless the database has the observed table and no other of its own.

    SQLite's own tables (names starting `sqlite_`, which only SQLite may make) don't count:
    `ANALYZE` adds `sqlite_stat1`, as the owner's store had after a join on 23 October 2026.
    """
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        if not str(row[0]).lower().startswith(SQLITE_PREFIX)
    ]
    if tables != [TABLE]:
        msg = f"the database has tables {tables}, not just '{TABLE}'"
        raise UnknownStoreError(msg)
    columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({TABLE})"))
    if columns != COLUMNS:
        msg = f"the '{TABLE}' table has columns {columns}, not {COLUMNS}"
        raise UnknownStoreError(msg)


def disk_files(folder: Path) -> dict[str, Path]:
    """Map each spilled entry's hex name to its file (one level deep, as observed)."""
    found: dict[str, Path] = {}
    if not folder.is_dir():
        return found
    for shard in sorted(folder.iterdir()):
        if not shard.is_dir():
            continue
        for file in sorted(shard.iterdir()):
            if file.is_file():
                found[file.name.lower()] = file
    return found


def entries(connection: sqlite3.Connection, folder: Path) -> Iterator[Entry]:
    """Every entry with its bytes; an entry whose file is missing is skipped."""
    recognize(connection)
    files = disk_files(folder)
    for key, content, size in connection.execute(f"SELECT id, content, size FROM {TABLE}"):  # noqa: S608
        if not isinstance(key, bytes) or len(key) != KEY_LENGTH:
            msg = "an entry's id isn't 16 bytes"
            raise UnknownStoreError(msg)
        if content is not None:
            yield Entry(key, bytes(content), None, int(size))
            continue
        path = files.get(key.hex())
        if path is not None:
            yield Entry(key, path.read_bytes(), path, int(size))


def picture(data: bytes) -> Picture | None:
    """The KTX2 mip pack inside an entry's bytes, or None if it holds none."""
    head = data[:SEARCH]
    offset = head.find(ochre.KTX2_IDENTIFIER)
    compressed = False
    body = data[offset:] if offset >= 0 else b""
    if offset < 0:
        offset = head.find(ZSTD_MAGIC)
        if offset < 0:
            return None
        try:
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data[offset:])) as reader:
                body = reader.read(HEAD_DECODED)  # the header, index and keys are at the start
        except zstandard.ZstdError:
            return None
        if not body.startswith(ochre.KTX2_IDENTIFIER):
            return None
        compressed = True
    try:
        layout = ochre.ktx2_layout(body)
    except ochre.OchreError:
        return None
    values = key_values(body, layout.kvd_offset, layout.kvd_length)
    original = _size(values.get("RobloxOriginalWidth"), values.get("RobloxOriginalHeight"))
    pack = values.get("packIndex")
    group = "\n".join(f"{k}={v}" for k, v in sorted(values.items()) if k not in ("packIndex",))
    return Picture(
        offset=offset,
        compressed=compressed,
        vk_format=layout.vk_format,
        width=layout.width,
        height=layout.height,
        levels=layout.levels,
        original=original,
        pack=int(pack) if pack is not None and pack.isdigit() else None,
        group=group,
    )


def key_values(data: bytes, offset: int, length: int) -> dict[str, str]:
    """A KTX2 file's key/value data (each: length, key NUL value, padding to 4)."""
    found: dict[str, str] = {}
    position, end = offset, min(offset + length, len(data))
    while position + 4 <= end:
        (size,) = _U32.unpack_from(data, position)
        record = data[position + 4 : position + 4 + size]
        key, _, value = record.partition(b"\x00")
        found[key.decode("utf-8", "replace")] = value.rstrip(b"\x00").decode("utf-8", "replace")
        position += 4 + size
        position += -position % 4
    return found


def _size(width: str | None, height: str | None) -> tuple[int, int] | None:
    if width is None or height is None or not width.isdigit() or not height.isdigit():
        return None
    return int(width), int(height)
