# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Roblox trust file, cache, client-settings and tweak target paths for this OS.

Cache (fact W-06, docs/platforms/windows.md; spec S-24): Roblox's download cache in
`%LOCALAPPDATA%\\Roblox` is the asset storage database `rbx-storage.db` with its SQLite
write-ahead files `rbx-storage.db-wal` and `rbx-storage.db-shm`, and the `rbx-storage` folder
beside it. Nothing else in that folder is ever named here: not `rbx-storage.id` or
`rbx-storage-sc` (their purpose isn't known), not `LocalStorage`, `logs`, the settings files
(`GlobalBasicSettings_13.xml`, `GlobalSettings_13.xml`, `frm.cfg`, `AnalysticsSettings.xml`) or
anything of Studio's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: W-06: the Roblox folder under `%LOCALAPPDATA%`.
ROBLOX_FOLDER: Final = "Roblox"
#: W-06: the download cache, in the order it is moved (the write-ahead files before the
#: database they belong to, so a crash part-way never leaves them without it).
CACHE_NAMES: Final = ("rbx-storage.db-shm", "rbx-storage.db-wal", "rbx-storage.db", "rbx-storage")


def cache_files(local_appdata: Path | None) -> list[Path]:
    """Return the cache files and folders that exist under `%LOCALAPPDATA%\\Roblox`."""
    if local_appdata is None:
        return []
    folder = local_appdata / ROBLOX_FOLDER
    return [folder / name for name in CACHE_NAMES if (folder / name).exists()]
