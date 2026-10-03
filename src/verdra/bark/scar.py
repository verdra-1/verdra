# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""System change ledger (9.4): write-ahead entries, status, undo descriptors.

Every change Verdra makes outside its own folders is recorded in `changes.json` (format
`verdra.ledger`, version 1) before it is made, as a `pending` entry, and marked `done` after.
Reset everything walks the entries in reverse and undoes each one, including entries a crash
left `pending` (Master plan 9.4). The file is written atomically with a `.bak` copy; if it is
damaged, the copy is used.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import msgspec
from msgspec import Meta, Struct

from verdra.soil import atomic, terrain

FORMAT = terrain.FORMAT_LEDGER
VERSION = 1

Kind = Literal[
    "ca_roblox_bundle",
    "hosts_entries",
    "keeper_install",
    "scheduled_task",
    "launch_agent",
    "launch_daemon",
    "polkit_policy",
    "systemd_unit",
    "autostart",
    "launcher_entry",
    "uri_handler",
    "file_tweak",
    "client_settings_file",
    "frame_rate_setting",
]
State = Literal["pending", "done", "removed", "failed"]
#: States whose change may still be in place, so Reset everything must undo them.
OPEN_STATES: frozenset[State] = frozenset({"pending", "done", "failed"})


class Entry(Struct, kw_only=True, frozen=True):
    """One system change and what undoing it needs."""

    id: str
    kind: Kind
    target: str
    created: Annotated[datetime, Meta(tz=True)]
    state: State
    details: dict[str, Any]


class Document(Struct, kw_only=True):
    """The whole ledger file."""

    format: str
    version: int
    entries: list[Entry]


class LedgerError(RuntimeError):
    """Neither the ledger nor its backup can be read."""


def ledger_path() -> Path:
    """Return the ledger file in the config folder."""
    return terrain.config_dir() / terrain.LEDGER_FILE


class Ledger:
    """The system change ledger file."""

    def __init__(
        self, path: Path | None = None, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.path = path if path is not None else ledger_path()
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._entries = self._read()

    def entries(self) -> list[Entry]:
        """Return every entry, oldest first."""
        return list(self._entries)

    def open_entries(self) -> Iterator[Entry]:
        """Yield the entries Reset everything must undo, newest first."""
        for entry in reversed(self._entries):
            if entry.state in OPEN_STATES:
                yield entry

    def begin(self, kind: Kind, target: str, details: dict[str, Any]) -> Entry:
        """Record a change before it is made and return its `pending` entry."""
        entry = Entry(
            id=uuid.uuid4().hex,
            kind=kind,
            target=target,
            created=self._clock(),
            state="pending",
            details=details,
        )
        self._entries.append(entry)
        self._write()
        return entry

    def mark(self, entry_id: str, state: State, **details: Any) -> Entry:
        """Set an entry's state (and add details) and return the updated entry."""
        for index, entry in enumerate(self._entries):
            if entry.id == entry_id:
                updated = msgspec.structs.replace(
                    entry, state=state, details={**entry.details, **details}
                )
                self._entries[index] = updated
                self._write()
                return updated
        msg = f"no ledger entry {entry_id}"
        raise KeyError(msg)

    def _read(self) -> list[Entry]:
        for candidate in (self.path, atomic.backup_path(self.path)):
            if not candidate.exists():
                continue
            try:
                document = msgspec.json.decode(atomic.read_bytes(candidate), type=Document)
            except msgspec.DecodeError, msgspec.ValidationError, OSError:
                continue
            if document.format == FORMAT and document.version == VERSION:
                return document.entries
        if self.path.exists():
            msg = f"the ledger {self.path} and its backup can't be read"
            raise LedgerError(msg)
        return []

    def _write(self) -> None:
        document = Document(format=FORMAT, version=VERSION, entries=self._entries)
        data = msgspec.json.format(msgspec.json.encode(document), indent=2) + b"\n"
        atomic.write_atomic(self.path, data, keep_backup=True)
