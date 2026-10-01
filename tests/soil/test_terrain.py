# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""System identifiers are defined once, in soil/terrain.py (Reference R3)."""

import re
from pathlib import Path

import pytest

from verdra.soil import terrain

SRC = Path(terrain.__file__).resolve().parents[1]

# Identifiers distinctive enough that spelling them anywhere else is a mistake.
DISTINCTIVE = [
    terrain.APP_ID,
    terrain.APP_ID_UNDERSCORE,
    terrain.CA_BEGIN_MARKER,
    terrain.HOSTS_MARKER,
    terrain.KEEPER_PROTOCOL,
    terrain.WINDOWS_KEEPER_SERVICE,
    terrain.WINDOWS_WATCHDOG_TASK,
    terrain.LINUX_WATCHDOG_UNIT,
    terrain.SOBER_FLATPAK_ID,
    terrain.PACK_MIME_TYPE,
]


def test_identifiers_are_spelled_only_in_terrain() -> None:
    for path in SRC.rglob("*.py"):
        if path.name == "terrain.py" and path.parent.name == "soil":
            continue
        text = path.read_text(encoding="utf-8")
        for identifier in DISTINCTIVE:
            assert identifier not in text, f"{path.relative_to(SRC)} spells {identifier!r}"


def test_underscore_form_follows_platform_rules() -> None:
    assert terrain.APP_ID.replace("-", "_") == terrain.APP_ID_UNDERSCORE
    assert re.fullmatch(r"[a-z0-9.-]+", terrain.LINUX_POLKIT_ACTION)
    assert re.fullmatch(r"[A-Za-z0-9_.]+", terrain.LINUX_FLATPAK_ID)


def test_user_agent() -> None:
    assert terrain.user_agent("1.2.3") == "Verdra/1.2.3 (+https://github.com/verdra-1/verdra)"


def test_folders_follow_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path))
    assert terrain.config_dir() == tmp_path / "config"
    assert terrain.default_library_dir() == tmp_path / "library"
    assert terrain.logs_dir() == tmp_path / "logs"
    assert terrain.exports_dir() == tmp_path / "exports"


def test_folders_use_plain_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(terrain.HOME_OVERRIDE_VARIABLE, raising=False)
    for folder in (terrain.config_dir(), terrain.default_library_dir(), terrain.logs_dir()):
        assert any(part.lower() == "verdra" for part in folder.parts)
    assert terrain.exports_dir().name == "Verdra"
