# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""System identifiers are defined once, in soil/terrain.py (Reference R3)."""

import ast
import re
from pathlib import Path

import pytest

from verdra.soil import terrain

SRC = Path(terrain.__file__).resolve().parents[1]

ROOT = SRC.parent
# Everything that holds Verdra code or build files (review finding M14).
SCANNED = [SRC, ROOT / "tools", ROOT / "packaging"]


def distinctive() -> dict[str, str]:
    """Return every string identifier in terrain that is distinctive enough to scan for.

    Short or generic values ("Verdra", "verdra", a bare port) would match ordinary text; every
    value with a separator, a dot or a marker character is an identifier nobody else spells.
    """
    found = {}
    for name, value in vars(terrain).items():
        if (
            name.isupper()
            and isinstance(value, str)
            and len(value) >= 8
            and re.search(r"[.\-/:#\\{]", value)
        ):
            found[name] = value
    return found


def test_the_scan_covers_r3() -> None:
    names = set(distinctive())
    assert {"APP_ID", "APP_ID_UNDERSCORE", "KEEPER_EXECUTABLE", "CA_BEGIN_MARKER",
            "HOSTS_MARKER", "KEEPER_PROTOCOL", "PACK_MIME_TYPE", "INNO_APP_ID",
            "RELEASES_API_URL", "FORMAT_SETTINGS"} <= names  # fmt: skip
    assert terrain.INNO_APP_ID == "{8F770622-386C-4265-AF56-B019A81EA7BE}"  # decision 0004


def literals(path: Path) -> list[tuple[int, str]]:
    """Return (line, value) for every string literal in a Python file, docstrings left out."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def spells(value: str, identifier: str) -> bool:
    """Return whether a literal spells `identifier`.

    A prefix such as "account-" is only spelled where a literal starts with it: inside other
    text ("/account-security-service", a Roblox path) it is a different word.
    """
    if identifier[-1] in "-/:" and not re.search(r"[.\-/:#\\{]", identifier[:-1]):
        return value.startswith(identifier)
    return identifier in value


def test_a_bare_prefix_is_spelled_only_at_the_start() -> None:
    assert spells(f"{terrain.SECRET_ITEM_ACCOUNT_PREFIX}name", terrain.SECRET_ITEM_ACCOUNT_PREFIX)
    assert not spells("/account-security-service", terrain.SECRET_ITEM_ACCOUNT_PREFIX)
    assert spells(f"x {terrain.HOSTS_MARKER} y", terrain.HOSTS_MARKER)


def test_identifiers_are_spelled_only_in_terrain() -> None:
    identifiers = distinctive()
    problems = []
    for folder in SCANNED:
        if not folder.exists():
            continue
        for path in [*folder.rglob("*.py"), *folder.rglob("*.spec")]:
            if path == Path(terrain.__file__).resolve():
                continue
            for line, value in literals(path):
                for name, identifier in identifiers.items():
                    if spells(value, identifier):
                        problems.append(f"{path.relative_to(ROOT)}:{line} spells terrain.{name}")
    assert problems == []


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
