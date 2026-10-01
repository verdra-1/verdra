# SPDX-FileCopyrightText: 2026 The Verdra Authors
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
3. A person checks it on a real machine (manual).

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
    assert len(problems) == 1
    assert "acceptance test 2" in problems[0]


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
