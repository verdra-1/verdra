# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Tests for the docs gate."""

from pathlib import Path

import pytest

from tools import check_docs

SPEC = """# S-99 Example

**Status:** Built

## Acceptance tests

1. The first thing works.
2. The second thing works.
3. A person checks it on a real machine
   and records the result (manual, at the gate).
4. A wrapped automatable test
   on two lines.

## Lives in
"""

TEST = """
import pytest

@pytest.mark.spec("S-99", 1)
def test_first(): ...
"""


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "verdra" / "trunk").mkdir(parents=True)
    monkeypatch.setattr(check_docs, "SRC", tmp_path / "src")
    monkeypatch.setattr(check_docs, "SPECS", tmp_path / "docs" / "specs")
    monkeypatch.setattr(check_docs, "TESTS", tmp_path / "tests")
    monkeypatch.setattr(check_docs, "PROVENANCE", tmp_path / "docs" / "provenance.md")
    monkeypatch.setattr(check_docs, "ROOT", tmp_path)
    return tmp_path


def test_missing_acceptance_test_is_reported(repo: Path) -> None:
    (repo / "docs" / "specs" / "S-99-example.md").write_text(SPEC, encoding="utf-8")
    (repo / "tests" / "test_example.py").write_text(TEST, encoding="utf-8")
    problems = check_docs.check_specs()
    assert len(problems) == 2
    assert "acceptance test 2" in problems[0]
    assert "acceptance test 4" in problems[1]


def test_draft_specs_need_no_tests(repo: Path) -> None:
    text = SPEC.replace("Built", "Agreed")
    (repo / "docs" / "specs" / "S-99-example.md").write_text(text, encoding="utf-8")
    assert check_docs.check_specs() == []


def test_modules_need_provenance(repo: Path) -> None:
    (repo / "src" / "verdra" / "trunk" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "verdra" / "trunk" / "rings.py").write_text("", encoding="utf-8")
    (repo / "docs" / "provenance.md").write_text(
        "| `verdra/trunk/` | R1 | — | 2026-10-01 |", encoding="utf-8"
    )
    assert check_docs.check_provenance() == [
        "docs/provenance.md: no entry for `verdra/trunk/rings.py`"
    ]


def test_provenance_entries_need_a_date(repo: Path) -> None:
    (repo / "docs" / "provenance.md").write_text(
        "| Module | Built from | Libraries | Date |\n| `verdra/` | R1 | — |\n", encoding="utf-8"
    )
    assert check_docs.check_provenance() == [
        "docs/provenance.md: the entry for `verdra/` has no date"
    ]


TREE = """# Architecture

```text
src/verdra/
├── trunk/                   App services and state.
│   └── rings.py             Logging: rotating files.
└── soil/                    Platform adapters.
    └── tundra/              Linux and Sober.
        └── files.py         Roblox trust file paths for this OS.
```
"""


def test_module_tree_expands_os_packages(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "docs" / "architecture.md").write_text(TREE, encoding="utf-8")
    monkeypatch.setattr(check_docs, "ARCHITECTURE", repo / "docs" / "architecture.md")
    tree = check_docs.module_tree()
    assert tree["verdra/trunk/rings.py"] == "Logging: rotating files."
    assert tree["verdra/soil/meadow/files.py"] == "Roblox trust file paths for this OS."
    assert "verdra/soil/orchard/files.py" in tree


def test_real_tree_matches_the_source() -> None:
    assert check_docs.check_module_tree() == []


def test_a_test_carried_to_a_later_milestone_waits_for_it(repo: Path) -> None:
    text = SPEC.replace("**Status:** Built", "**Status:** Built\n**Milestone:** M1 (part)")
    text = text.replace("2. The second", "2. (M6) The second").replace(
        "4. A wrapped", "4. (M1) A wrapped"
    )
    (repo / "docs" / "specs" / "S-99-example.md").write_text(text, encoding="utf-8")
    (repo / "tests" / "test_example.py").write_text(TEST, encoding="utf-8")
    problems = check_docs.check_specs()
    # Test 2 waits for M6; test 4 names the spec's own milestone, so it is still due.
    assert len(problems) == 1
    assert "acceptance test 4" in problems[0]


def test_a_later_milestone_needs_the_specs_own_milestone(repo: Path) -> None:
    text = SPEC.replace("2. The second", "2. (M6) The second")
    (repo / "docs" / "specs" / "S-99-example.md").write_text(text, encoding="utf-8")
    (repo / "tests" / "test_example.py").write_text(TEST, encoding="utf-8")
    assert len(check_docs.check_specs()) == 2  # no Milestone line: nothing is carried over
