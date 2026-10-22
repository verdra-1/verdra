# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Describe the structure of a COPY of Roblox's saved assets, read-only (decision record 0028).

Option A of decision record 0028 would put a replacement into the store the Player reads before
it downloads. Roblox doesn't document that store, so this tool reports only its shape, from a
copy the owner made: never the live folder (refused), never a value from it. It prints:

- the SQLite database's tables, their CREATE statements, row counts, and per column the kinds of
  values seen (integer, text of N hex digits, blob of N bytes…);
- where a given asset ID appears (table and column names only);
- the folder's layout: how deep, how file names look (as a shape such as `hex32`), sizes, and
  the first bytes of each file as a known format name (KTX2, zstd, PNG…), counted;
- whether file names equal a hash of their own bytes (MD5, SHA-1, SHA-256), and whether database
  values name those files (counts only): what a content-addressed store would show.

    uv run python tools/inspect_store.py <copy folder> [--asset ID] [--out report.txt]

The copy folder holds `rbx-storage.db` (with `-wal` and `-shm` if they were there) and the
`rbx-storage` folder. The database is copied again into a temporary folder before it is opened,
so not even the copy changes.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

DATABASE: Final = "rbx-storage.db"
FOLDER: Final = "rbx-storage"
#: Files hashed to test content addressing; enough for a clear answer, quick on a large store.
HASH_SAMPLE: Final = 200
#: Rows read per column to describe its values.
ROW_SAMPLE: Final = 2000
#: Leading bytes of known formats (public format specifications).
MAGIC: Final = (
    (b"\xabKTX 20\xbb\r\n\x1a\n", "KTX2"),
    (b"\xabKTX 11\xbb\r\n\x1a\n", "KTX1"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"\x1f\x8b", "gzip"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"RIFF", "RIFF (WAV/WebP)"),
    (b"OggS", "Ogg"),
    (b"ID3", "MP3"),
    (b"version ", "Roblox mesh (text header)"),
    (b"<roblox", "Roblox XML model"),
    (b"<roblox!", "Roblox binary model"),
    (b"SQLite format 3\x00", "SQLite"),
    (b"\x04\x22\x4d\x18", "LZ4 frame"),
)
_HEX = re.compile(r"[0-9a-f]+")


class LiveStoreError(ValueError):
    """The folder is Roblox's own; only a copy may be inspected."""


@dataclass
class Report:
    """What the inspection found; `lines()` is the text the owner sends."""

    tables: list[str] = field(default_factory=list[str])
    asset: list[str] = field(default_factory=list[str])
    folder: list[str] = field(default_factory=list[str])
    addressing: list[str] = field(default_factory=list[str])

    def lines(self) -> list[str]:
        out = ["Verdra store inspection (structure only; no values, no file contents)", ""]
        for title, part in (
            ("Database", self.tables),
            ("Asset ID", self.asset),
            ("Folder", self.folder),
            ("Content addressing", self.addressing),
        ):
            if part:
                out += [f"## {title}", *part, ""]
        return out


def refuse_live(folder: Path, environment: dict[str, str] | None = None) -> None:
    """Raise LiveStoreError when `folder` is or lies inside Roblox's own folder."""
    environment = dict(os.environ) if environment is None else environment
    local = next((v for k, v in environment.items() if k.upper() == "LOCALAPPDATA"), "")
    if not local:
        return
    live = (Path(local) / "Roblox").resolve()
    resolved = folder.resolve()
    if resolved == live or live in resolved.parents:
        msg = f"{folder} is Roblox's own folder; copy the files elsewhere and inspect the copy"
        raise LiveStoreError(msg)


def shape(value: object) -> str:
    """How a value looks, without the value: `int`, `hex32`, `text12`, `blob16`, `null`."""
    if value is None:
        return "null"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "real"
    if isinstance(value, bytes):
        return f"blob{len(value)}"
    text = str(value)
    if text and _HEX.fullmatch(text.lower()):
        return f"hex{len(text)}"
    return f"text{len(text)}"


def name_shape(name: str) -> str:
    """A file or folder name as a shape: hex digits as `hexN`, other text as `textN`."""
    stem, dot, suffix = name.partition(".")
    return shape(stem) + (f".{suffix}" if dot else "")


def magic(head: bytes) -> str:
    """The format a file's first bytes announce, or `unknown`."""
    return next((label for prefix, label in MAGIC if head.startswith(prefix)), "unknown")


@contextlib.contextmanager
def opened_copy(source: Path) -> Iterator[sqlite3.Connection]:
    """Open a private copy of the database (with its -wal and -shm) read-only."""
    with tempfile.TemporaryDirectory() as scratch:
        for suffix in ("", "-wal", "-shm"):
            part = source.with_name(source.name + suffix)
            if part.is_file():
                shutil.copy2(part, Path(scratch) / part.name)
        target = Path(scratch) / source.name
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            yield connection
        finally:
            connection.close()


def describe_database(
    connection: sqlite3.Connection, asset: int | None
) -> tuple[list[str], list[str], dict[tuple[str, str], set[str]]]:
    """Return the table lines, the asset-ID lines and, per text column, its hex values."""
    tables: list[str] = []
    found: list[str] = []
    hex_values: dict[tuple[str, str], set[str]] = {}
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    for name, sql in rows:
        quoted = '"' + str(name).replace('"', '""') + '"'
        count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]  # noqa: S608
        tables.append(f"- table {name}: {count} rows")
        tables.append(f"  schema: {' '.join(str(sql).split())}")
        cursor = connection.execute(f"SELECT * FROM {quoted} LIMIT {ROW_SAMPLE}")  # noqa: S608
        columns = [d[0] for d in cursor.description]
        shapes: dict[str, Counter[str]] = {c: Counter() for c in columns}
        for row in cursor:
            for column, value in zip(columns, row, strict=True):
                shapes[column][shape(value)] += 1
                if isinstance(value, str) and _HEX.fullmatch(value.lower()):
                    hex_values.setdefault((name, column), set()).add(value.lower())
                if isinstance(value, bytes) and len(value) in (16, 20, 32):
                    hex_values.setdefault((name, column), set()).add(value.hex())
                if asset is not None and _holds(value, asset):
                    found.append(f"- {asset} appears in {name}.{column}")
        for column in columns:
            seen = ", ".join(f"{kind} ×{n}" for kind, n in shapes[column].most_common(4))
            tables.append(f"  column {column}: {seen or 'no rows'}")
    return tables, sorted(set(found)), hex_values


def _holds(value: object, asset: int) -> bool:
    if isinstance(value, int):
        return value == asset
    if isinstance(value, str):
        return str(asset) in value
    if isinstance(value, bytes):
        return str(asset).encode() in value
    return False


def files_in(folder: Path) -> Iterator[Path]:
    """Every file below `folder`, in a stable order."""
    for root, folders, names in os.walk(folder):
        folders.sort()
        for name in sorted(names):
            yield Path(root) / name


def describe_folder(folder: Path) -> tuple[list[str], list[Path]]:
    """Layout, name shapes, sizes and formats of the folder's files (counts only)."""
    files = list(files_in(folder))
    depths = Counter(len(f.relative_to(folder).parts) - 1 for f in files)
    folders = Counter(name_shape(f.parent.name) for f in files if f.parent != folder)
    names = Counter(name_shape(f.name) for f in files)
    formats: Counter[str] = Counter()
    sizes: list[int] = []
    for file in files:
        with file.open("rb") as handle:
            formats[magic(handle.read(16))] += 1
        sizes.append(file.stat().st_size)
    lines = [f"- {len(files)} files, {sum(sizes)} bytes"]
    lines.append("- depth below the folder: " + _counted(depths))
    if folders:
        lines.append("- folder names: " + _counted(folders))
    lines.append("- file names: " + _counted(names))
    lines.append("- formats by first bytes: " + _counted(formats))
    if sizes:
        ordered = sorted(sizes)
        lines.append(
            f"- sizes: smallest {ordered[0]}, median {ordered[len(ordered) // 2]}, "
            f"largest {ordered[-1]} bytes"
        )
    return lines, files


def _counted[T](counter: Counter[T]) -> str:
    return ", ".join(f"{key} ×{n}" for key, n in counter.most_common(8)) or "none"


def describe_addressing(
    files: list[Path], hex_values: dict[tuple[str, str], set[str]]
) -> list[str]:
    """Whether names are hashes of their bytes, and which database columns name the files."""
    sample = files[:HASH_SAMPLE]
    matches: Counter[str] = Counter()
    for file in sample:
        data = file.read_bytes()
        stem = file.name.partition(".")[0].lower()
        for algorithm in ("md5", "sha1", "sha256"):
            if hashlib.new(algorithm, data).hexdigest() == stem:
                matches[algorithm] += 1
    lines = [f"- of {len(sample)} files, the name is the hash of the bytes:"]
    lines += [f"  {algorithm}: {matches[algorithm]}" for algorithm in ("md5", "sha1", "sha256")]
    stems = {f.name.partition(".")[0].lower() for f in files}
    for (table, column), values in sorted(hex_values.items()):
        named = len(values & stems)
        if named:
            lines.append(f"- {table}.{column}: {named} of {len(values)} values name a file")
    if len(lines) == 1 + 3:
        lines.append("- no database value names a file")
    return lines


def inspect(copy: Path, asset: int | None = None) -> Report:
    """Inspect a copy of the store; raises LiveStoreError for Roblox's own folder."""
    refuse_live(copy)
    report = Report()
    hex_values: dict[tuple[str, str], set[str]] = {}
    database = copy / DATABASE
    if database.is_file():
        with opened_copy(database) as connection:
            report.tables, report.asset, hex_values = describe_database(connection, asset)
        if asset is not None and not report.asset:
            report.asset = [f"- {asset} appears in no table"]
    else:
        report.tables = [f"- no {DATABASE} in the copy"]
    folder = copy / FOLDER
    files: list[Path] = []
    if folder.is_dir():
        report.folder, files = describe_folder(folder)
    else:
        report.folder = [f"- no {FOLDER} folder in the copy"]
    report.addressing = describe_addressing(files, hex_values)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("copy", type=Path, help="the folder holding the COPY of the store")
    parser.add_argument("--asset", type=int, help="an asset ID to look for (names only)")
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = inspect(arguments.copy, arguments.asset)
    except LiveStoreError as error:
        print(error, file=sys.stderr)
        return 2
    text = "\n".join(report.lines()) + "\n"
    print(text, end="")
    if arguments.out is not None:
        arguments.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
