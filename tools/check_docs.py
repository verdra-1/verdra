# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Docs gate: provenance entries for every module, tests for every built spec.

Master plan 12.3 ("Docs") and 3.1 (process control 3):

1. Every module under `src/verdra/` is named in `docs/provenance.md`, by its path relative to
   `src/` (`verdra/trunk/rings.py`); a package's `__init__.py` may be named by its folder
   (`verdra/trunk/`). Every entry ends with the date it was written (`| 2026-10-01 |`).
2. Every spec in `docs/specs/` whose status is Built or Verified has each automatable acceptance
   test referenced by a test marked `@pytest.mark.spec("S-02", 3)`.

Usage: python tools/check_docs.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PROVENANCE = ROOT / "docs" / "provenance.md"
SPECS = ROOT / "docs" / "specs"
TESTS = ROOT / "tests"
DATED_ENTRY = re.compile(r"^\|\s*`[^`]+`\s*\|.*\|\s*\d{4}-\d{2}-\d{2}\s*\|$")

STATUS = re.compile(r"^\*\*Status:\*\*\s*(\w+)", re.MULTILINE)
ACCEPTANCE = re.compile(r"^## Acceptance tests\s*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$", re.MULTILINE)


def check_provenance() -> list[str]:
    """Return one problem per module that has no provenance entry."""
    text = PROVENANCE.read_text(encoding="utf-8") if PROVENANCE.exists() else ""
    problems: list[str] = []
    for path in sorted((SRC / "verdra").rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        names = {f"`{relative}`"}
        if path.name == "__init__.py":
            names.add(f"`{path.parent.relative_to(SRC).as_posix()}/`")
        if not any(name in text for name in names):
            problems.append(f"docs/provenance.md: no entry for `{relative}`")
    for line in text.splitlines():
        if line.startswith("| `") and not DATED_ENTRY.match(line.strip()):
            entry = line.split("|")[1].strip()
            problems.append(f"docs/provenance.md: the entry for {entry} has no date")
    return problems


def spec_references() -> set[tuple[str, int]]:
    """Return every (spec ID, test number) pair referenced by a spec marker in the tests."""
    found: set[tuple[str, int]] = set()
    for path in TESTS.rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_marker = isinstance(function, ast.Attribute) and function.attr == "spec"
            if is_marker and len(node.args) >= 2:
                spec, *numbers = node.args
                if isinstance(spec, ast.Constant) and isinstance(spec.value, str):
                    for number in numbers:
                        if isinstance(number, ast.Constant) and isinstance(number.value, int):
                            found.add((spec.value, number.value))
    return found


def check_specs() -> list[str]:
    """Return one problem per automatable acceptance test of a built spec without a test."""
    if not SPECS.exists():
        return []
    referenced = spec_references()
    problems: list[str] = []
    for path in sorted(SPECS.glob("S-*.md")):
        text = path.read_text(encoding="utf-8")
        spec_id = "-".join(path.stem.split("-")[:2])
        status = STATUS.search(text)
        if status is None:
            problems.append(f"{path.relative_to(ROOT).as_posix()}: no **Status:** line")
            continue
        if status.group(1) not in {"Built", "Verified"}:
            continue
        section = ACCEPTANCE.search(text)
        if section is None:
            problems.append(f"{path.relative_to(ROOT).as_posix()}: no acceptance tests section")
            continue
        for number, wording in NUMBERED.findall(section.group(1)):
            if "(manual)" in wording:
                continue
            if (spec_id, int(number)) not in referenced:
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}: acceptance test {number} has no test "
                    f'marked @pytest.mark.spec("{spec_id}", {number})'
                )
    return problems


def main() -> int:
    """Run the gate and return a process exit code."""
    problems = check_provenance() + check_specs()
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
