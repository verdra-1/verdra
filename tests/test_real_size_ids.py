# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Every test file that uses Roblox IDs also uses real-size ones (`tests/ids.py`).

Small invented IDs hid an overflow at the Qt boundary: a signal typed `int` (32 bits) dropped a
real 11-digit asset ID, and Save did nothing. A test file that mentions asset, place, universe
or user IDs must use both `ABOVE_INT32` and `ABOVE_UINT32`, so a new fixture can't use small IDs
alone.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
#: Words that mean a test handles Roblox IDs.
ID_WORDS = re.compile(
    r"asset_?[iI]d|assetId|swaps\(|place_?[iI]d|placeId|/places/|universe|user_?[iI]d|userId"
)
#: Files that name these words without handling an ID, with the reason.
EXEMPT = {
    "tools/test_platform_facts.py": "names placeId only as a word evidence must not contain",
}


def files_with_ids() -> list[str]:
    found = []
    for path in sorted(TESTS.rglob("*.py")):
        relative = path.relative_to(TESTS).as_posix()
        if relative in {"ids.py", "test_real_size_ids.py"} | EXEMPT.keys():
            continue
        if ID_WORDS.search(path.read_text(encoding="utf-8")):
            found.append(relative)
    return found


def test_every_test_with_roblox_ids_uses_real_size_ones() -> None:
    files = files_with_ids()
    assert "canopy/test_replacements_ui.py" in files  # the scan sees what it should
    missing = [
        relative
        for relative in files
        if not all(
            re.search(rf"\b{name}\b", (TESTS / relative).read_text(encoding="utf-8"))
            for name in ("ABOVE_INT32", "ABOVE_UINT32")
        )
    ]
    assert missing == [], (
        "These tests use Roblox IDs but no real-size ones; add cases with "
        "tests.ids.ABOVE_INT32 and ABOVE_UINT32: " + ", ".join(missing)
    )


def test_the_real_size_ids_are_above_the_32_bit_limits() -> None:
    from tests.ids import ABOVE_INT32, ABOVE_UINT32

    assert 2**31 - 1 < ABOVE_INT32 < 2**32 < ABOVE_UINT32


SOURCE = TESTS.parent / "src" / "verdra"


def qt_int_boundaries() -> list[str]:
    """Return every signal or slot that carries a Qt `int`, and every 32-bit number field.

    `Signal(int)` and `@Slot(int)` convert to C++ `int` (32 bits); `QIntValidator` and
    `QSpinBox` stop at 2,147,483,647. None of them may carry an ID; counts and ports go through
    `object` or a bounded settings row instead.
    """
    import ast  # noqa: PLC0415

    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(SOURCE).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            name = node.func.attr if isinstance(node.func, ast.Attribute) else name
            if name in {"Signal", "Slot"} and any(
                isinstance(arg, ast.Name) and arg.id == "int" for arg in node.args
            ):
                found.append(f"{relative}:{node.lineno} {name}(int)")
            if name == "QIntValidator" or (
                name == "QSpinBox" and relative != "canopy/screens/settings.py"
            ):
                found.append(f"{relative}:{node.lineno} {name}")
    return found


def test_no_id_can_cross_the_qt_boundary_as_a_32_bit_int() -> None:
    assert qt_int_boundaries() == []


def test_the_only_number_fields_are_small_bounded_settings(qapp: object) -> None:
    from verdra.canopy.screens import settings  # noqa: PLC0415

    rows = [row for _key, _title, rows in settings.groups() for row in rows if row.kind == "number"]
    assert rows, "the scan should see the settings' number rows"
    assert all(row.maximum <= 65535 for row in rows), [(r.key, r.maximum) for r in rows]
