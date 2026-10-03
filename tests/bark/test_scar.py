# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The system change ledger (Master plan 9.4)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from verdra.bark import scar
from verdra.soil import atomic

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def ledger(path: Path) -> scar.Ledger:
    return scar.Ledger(path, clock=lambda: NOW)


def test_entries_are_written_before_the_change_and_marked_after(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    book = ledger(path)
    entry = book.begin("ca_roblox_bundle", "/x/cacert.pem", {"mode": 0o644})
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["format"] == "verdra.ledger"
    assert on_disk["version"] == 1
    assert on_disk["entries"][0]["state"] == "pending"
    assert on_disk["entries"][0]["created"] == "2026-10-03T12:00:00Z"
    book.mark(entry.id, "done")
    assert ledger(path).entries()[0].state == "done"
    assert ledger(path).entries()[0].details == {"mode": 0o644}


def test_reset_walks_open_entries_newest_first(tmp_path: Path) -> None:
    book = ledger(tmp_path / "changes.json")
    first = book.begin("autostart", "a", {})
    second = book.begin("uri_handler", "b", {})
    third = book.begin("file_tweak", "c", {})
    book.mark(first.id, "done")
    book.mark(second.id, "removed")
    book.mark(third.id, "failed", error="disk full")
    assert [e.id for e in book.open_entries()] == [third.id, first.id]
    assert book.entries()[2].details == {"error": "disk full"}


def test_a_damaged_ledger_falls_back_to_its_copy(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    book = ledger(path)
    entry = book.begin("autostart", "a", {})
    book.mark(entry.id, "done")  # the second write keeps the first as .bak
    path.write_bytes(b"{ broken")
    assert [e.state for e in ledger(path).entries()] == ["pending"]


def test_a_ledger_without_a_readable_copy_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    path.write_bytes(b"{ broken")
    with pytest.raises(scar.LedgerError):
        ledger(path)
    atomic.backup_path(path).write_bytes(
        b'{"format": "something.else", "version": 1, "entries": []}'
    )
    with pytest.raises(scar.LedgerError):
        ledger(path)


def test_no_file_means_no_entries(tmp_path: Path) -> None:
    assert ledger(tmp_path / "changes.json").entries() == []
    with pytest.raises(KeyError):
        ledger(tmp_path / "changes.json").mark("missing", "done")
