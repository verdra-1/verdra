# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Safe writes: temp file, fsync, rename, .bak rotation.

Every file Verdra writes goes through `write_atomic` (Master plan 9.7, decision record 0005): the
data goes to a temporary file in the same folder, is flushed and fsynced, and replaces the target
with `os.replace`, which is atomic on every supported system. On macOS and Linux the folder is
fsynced too, so the rename itself survives a power cut. A reader therefore sees either the old
file or the new one, never a mix.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

BACKUP_SUFFIX = ".bak"


def backup_path(path: Path) -> Path:
    """Return where the previous version of `path` is kept."""
    return path.with_name(path.name + BACKUP_SUFFIX)


def _fsync_folder(folder: Path) -> None:
    """Flush a folder's entries to disk, where the system allows it."""
    if sys.platform == "win32":
        return  # Windows can't open folders for fsync; NTFS journals the rename.
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(path: Path, data: bytes, *, keep_backup: bool = False) -> None:
    """Replace `path` with `data` so that a crash leaves either the old or the new file.

    Args:
        path: The file to write. Its folder is created if needed.
        data: The complete new contents.
        keep_backup: Keep the current file's contents as `<name>.bak` first (settings, ledger and
            profiles do this). The backup is itself written atomically.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and path.exists():
        write_atomic(backup_path(path), path.read_bytes())
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    _fsync_folder(path.parent)


def move_aside(path: Path, suffix: str) -> Path:
    """Rename a damaged file to `<name>.<suffix>` and return the new path."""
    target = path.with_name(f"{path.name}.{suffix}")
    os.replace(path, target)
    _fsync_folder(path.parent)
    return target


def remove_stale_temporaries(path: Path) -> int:
    """Delete temporary files a crashed write of `path` left behind; return how many."""
    removed = 0
    for stale in path.parent.glob(f".{path.name}.*.tmp"):
        with contextlib.suppress(OSError):
            stale.unlink()
            removed += 1
    return removed
