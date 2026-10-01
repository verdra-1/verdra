# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Safe writes (Master plan 9.7)."""

import os
from pathlib import Path

import pytest

from verdra.soil import atomic


def test_write_creates_folders_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.json"
    atomic.write_atomic(target, b"one")
    atomic.write_atomic(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["file.json"]


def test_keep_backup_keeps_the_previous_version(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    atomic.write_atomic(target, b"one", keep_backup=True)
    assert not atomic.backup_path(target).exists()
    atomic.write_atomic(target, b"two", keep_backup=True)
    assert atomic.backup_path(target).read_bytes() == b"one"


def test_failed_write_leaves_the_old_file_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "file.json"
    atomic.write_atomic(target, b"old")

    def broken(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        atomic.write_atomic(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


def test_move_aside(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.write_bytes(b"x")
    moved = atomic.move_aside(target, "broken-1")
    assert moved.name == "settings.json.broken-1"
    assert not target.exists()


def test_reads_and_replaces_ride_out_a_sharing_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(atomic, "_RETRY_DELAYS", (0.0, 0.0))
    target = tmp_path / "file.json"
    target.write_bytes(b"data")
    failures = iter([PermissionError("in use"), None])
    original = Path.read_bytes

    def flaky(self: Path) -> bytes:
        if (failure := next(failures, None)) is not None:
            raise failure
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)
    assert atomic.read_bytes(target) == b"data"
    monkeypatch.setattr(
        Path, "read_bytes", lambda _self: (_ for _ in ()).throw(PermissionError("in use"))
    )
    with pytest.raises(PermissionError):
        atomic.read_bytes(target)
