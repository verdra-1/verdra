# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Docs gate: module tree, provenance entries for every module, tests for every built spec.

Master plan 12.3 ("Docs"), 3.1 (process control 3) and Reference R1:

1. The module tree in `docs/architecture.md` and the modules under `src/verdra/` match both ways,
   and every module's docstring starts with its job from the tree.
2. Every module under `src/verdra/` is named in `docs/provenance.md`, by its path relative to
   `src/` (`verdra/trunk/rings.py`); a package's `__init__.py` may be named by its folder
   (`verdra/trunk/`). Every entry ends with the date it was written (`| 2026-10-01 |`).
3. Every spec in `docs/specs/` whose status is Built or Verified has each automatable acceptance
   test referenced by a test marked `@pytest.mark.spec("S-02", 3)`. A test that starts with a
   later milestone than the spec's own ("(M6) …" in an M1 spec) is carried to that milestone.

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
ARCHITECTURE = ROOT / "docs" / "architecture.md"
SPECS = ROOT / "docs" / "specs"
TESTS = ROOT / "tests"
DATED_ENTRY = re.compile(r"^\|\s*`[^`]+`\s*\|.*\|\s*\d{4}-\d{2}-\d{2}\s*\|$")

STATUS = re.compile(r"^\*\*Status:\*\*\s*(\w+)", re.MULTILINE)
ACCEPTANCE = re.compile(r"^## Acceptance tests\s*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
NUMBERED = re.compile(r"^(\d+)\.\s+(.*?)(?=^\d+\.\s|\Z)", re.MULTILINE | re.DOTALL)
#: The spec's own milestone, from its "**Milestone:** M1" line.
MILESTONE = re.compile(r"^\*\*Milestone:\*\* M(\d)", re.MULTILINE)
#: An acceptance test carried to a later milestone starts with it: "(M6) …".
LATER = re.compile(r"\(M(\d)\)")
TREE_BLOCK = re.compile(r"^```text\nsrc/verdra/\n(.*?)^```", re.MULTILINE | re.DOTALL)
TREE_LINE = re.compile(r"^([│ ]*)[├└]── (\S+)\s*(.*)$")
# The tree lists the OS adapter modules once, under tundra/; meadow/ and orchard/ have the same.
OS_PACKAGES = ("meadow", "orchard", "tundra")


def squash(text: str) -> str:
    """Collapse runs of whitespace, so wrapped docstrings compare equal to one-line jobs."""
    return " ".join(text.split())


def module_tree() -> dict[str, str]:
    """Return {module path relative to src/: job} from the tree in docs/architecture.md."""
    match = TREE_BLOCK.search(ARCHITECTURE.read_text(encoding="utf-8"))
    if match is None:
        return {}
    tree: dict[str, str] = {}
    stack: list[str] = []
    for line in match.group(1).splitlines():
        entry = TREE_LINE.match(line)
        if entry is None:
            continue
        depth = len(entry.group(1)) // 4
        name, job = entry.group(2), squash(entry.group(3))
        stack = stack[:depth]
        if name.endswith("/"):
            stack.append(name[:-1])
            if stack[0] != "assets":
                tree["/".join(["verdra", *stack, "__init__.py"])] = job
        elif stack[:1] != ["assets"]:
            tree["/".join(["verdra", *stack, name])] = job
    for path, job in list(tree.items()):
        parts = path.split("/")
        if len(parts) == 4 and parts[1:3] == ["soil", "tundra"] and parts[3] != "__init__.py":
            for package in OS_PACKAGES[:2]:
                tree["/".join(["verdra", "soil", package, parts[3]])] = job
    return tree


def check_module_tree() -> list[str]:
    """Return one problem per module missing from either side or with the wrong docstring."""
    tree = module_tree()
    if not tree:
        return ["docs/architecture.md: no module tree found"]
    actual = {path.relative_to(SRC).as_posix(): path for path in (SRC / "verdra").rglob("*.py")}
    problems = [
        f"{name}: listed in docs/architecture.md but missing"
        for name in tree.keys() - actual.keys()
    ]
    problems += [
        f"{name}: not listed in docs/architecture.md" for name in actual.keys() - tree.keys()
    ]
    for name in sorted(tree.keys() & actual.keys()):
        docstring = ast.get_docstring(ast.parse(actual[name].read_text(encoding="utf-8"))) or ""
        if not squash(docstring).startswith(tree[name]):
            problems.append(f"src/{name}: docstring must start with {tree[name]!r}")
    return sorted(problems)


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
        milestone = MILESTONE.search(text)
        own = int(milestone.group(1)) if milestone else None
        for number, wording in NUMBERED.findall(section.group(1)):
            if "(manual" in wording:
                continue
            later = LATER.match(wording.strip())
            if later and own is not None and int(later.group(1)) > own:
                continue
            if (spec_id, int(number)) not in referenced:
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}: acceptance test {number} has no test "
                    f'marked @pytest.mark.spec("{spec_id}", {number})'
                )
    return problems


def main() -> int:
    """Run the gate and return a process exit code."""
    problems = check_module_tree() + check_provenance() + check_specs()
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
