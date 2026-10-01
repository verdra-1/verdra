# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""System identifiers are defined once, in soil/terrain.py (Reference R3)."""

import re
from pathlib import Path

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
