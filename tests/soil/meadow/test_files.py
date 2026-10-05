# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-24: Roblox's download cache on Windows is only the W-06 names recorded as cache."""

from pathlib import Path

import pytest

from verdra.soil.meadow import files


@pytest.mark.spec("S-24", 7)
def test_only_the_cache_names_that_exist_are_listed(tmp_path: Path) -> None:
    roblox = tmp_path / "Roblox"
    for name in ("rbx-storage.db", "rbx-storage.db-wal", "rbx-storage.id", "frm.cfg"):
        (roblox / name).parent.mkdir(parents=True, exist_ok=True)
        (roblox / name).write_bytes(b"x")
    for folder in ("rbx-storage", "rbx-storage-sc", "LocalStorage", "logs", "RobloxStudio"):
        (roblox / folder).mkdir()
    assert files.cache_files(tmp_path) == [
        roblox / "rbx-storage.db-wal",
        roblox / "rbx-storage.db",
        roblox / "rbx-storage",
    ]
    assert files.cache_files(None) == []
    assert files.cache_files(tmp_path / "nowhere") == []


def test_the_cache_list_never_names_settings_logs_local_storage_or_studio() -> None:
    never = ("LocalStorage", "logs", "GlobalBasicSettings", "GlobalSettings", "frm.cfg", "Studio")
    assert not [
        name for name in files.CACHE_NAMES for word in never if word.lower() in name.lower()
    ]
    assert set(files.CACHE_NAMES) == {
        "rbx-storage.db",
        "rbx-storage.db-shm",
        "rbx-storage.db-wal",
        "rbx-storage",
    }
