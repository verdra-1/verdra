# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-16: the system changes Settings lists (trunk/branches/fallow)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from verdra.bark import scar
from verdra.soil import atomic
from verdra.trunk.branches import fallow

START = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def ledger_with_entries(path: Path) -> scar.Ledger:
    times = iter(START + timedelta(minutes=n) for n in range(10))
    ledger = scar.Ledger(path, clock=lambda: next(times))
    first = ledger.begin("ca_roblox_bundle", "/roblox/1/cacert.pem", {"mode": 0o644})
    ledger.mark(first.id, "done")
    gone = ledger.begin("ca_roblox_bundle", "/roblox/0/cacert.pem", {"mode": 0o644})
    ledger.mark(gone.id, "removed")
    ledger.begin("uri_handler", "roblox-player", {})
    failed = ledger.begin("ca_roblox_bundle", "/roblox/2/cacert.pem", {"mode": 0o444})
    ledger.mark(failed.id, "failed", error="Permission denied")
    return ledger


def test_every_change_still_in_place_is_listed_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    ledger_with_entries(path)
    changes = fallow.system_changes(path)
    assert [(c.kind, c.target, c.state, c.reason) for c in changes] == [
        ("ca_roblox_bundle", "/roblox/2/cacert.pem", "failed", "Permission denied"),
        ("uri_handler", "roblox-player", "pending", None),
        ("ca_roblox_bundle", "/roblox/1/cacert.pem", "done", None),
    ]
    assert changes[-1].created == START


def test_a_failed_change_without_a_recorded_error_has_no_reason(tmp_path: Path) -> None:
    ledger = scar.Ledger(tmp_path / "changes.json")
    entry = ledger.begin("uri_handler", "roblox-player", {})
    ledger.mark(entry.id, "failed")
    assert [c.reason for c in fallow.system_changes(ledger.path)] == [None]


def test_no_ledger_means_no_changes(tmp_path: Path) -> None:
    assert fallow.system_changes(tmp_path / "changes.json") == []


def test_a_damaged_ledger_is_read_from_its_backup(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    ledger_with_entries(path)
    atomic.backup_path(path).write_bytes(path.read_bytes())
    path.write_text("{ damaged", encoding="utf-8")
    assert len(fallow.system_changes(path)) == 3


def test_a_ledger_that_cant_be_read_is_reported_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    path.write_text("{ damaged", encoding="utf-8")
    with pytest.raises(fallow.LedgerUnreadableError) as raised:
        fallow.system_changes(path)
    assert raised.value.path == path
