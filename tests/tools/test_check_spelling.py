# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The spelling gate: US spelling in user-facing text."""

from pathlib import Path

import pytest
from tools.check_spelling import british, check_text, prose

from tools import check_spelling


@pytest.mark.parametrize(
    "word",
    [
        "behaviour", "Behaviours", "colour", "colours", "licence", "Licence", "cancelled",
        "cancelling", "recognises", "organise", "minimised", "favourite", "centre", "analyse",
        "catalogue", "honour", "customise", "travelled", "grey", "whilst", "programme",
        "artefact", "dialogue",
    ],
)  # fmt: skip
def test_british_spellings_are_found(word: str) -> None:
    assert british(word) is not None


@pytest.mark.parametrize(
    "word",
    [
        "behavior", "color", "license", "licensed", "licenses", "canceled", "cancellation",
        "recognizes", "organize", "minimized", "favorite", "center", "analyze", "analysis",
        "catalog", "dialog", "program", "your", "four", "otherwise", "advise", "raise",
        "concise", "precise", "premise", "promise", "expertise", "exercise", "surprise",
    ],
)  # fmt: skip
def test_us_spellings_and_ordinary_words_pass(word: str) -> None:
    assert british(word) is None


def test_allowlisted_words_pass() -> None:
    assert check_text("See the licence", "x", allow={"licence"}) == []
    assert [f.word for f in check_text("See the licence", "x", allow=set())] == ["licence"]


def test_markdown_code_and_links_are_not_prose() -> None:
    text = "Read the `licence` file.\n```\nlicence\n```\n[link](https://x/colour) colour"
    lines = prose(text)
    words = [word for _, line in lines for word in line.split()]
    assert "licence" not in " ".join(words)
    assert "colour" in words
    assert [number for number, line in lines if "colour" in line] == [5]


def test_catalog_and_documents_are_checked(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.verdra.spelling]\nallow = { "programme" = "a quoted name" }\n', encoding="utf-8"
    )
    catalog = tmp_path / "verdra_en.ts"
    catalog.write_text(
        "<TS><context><name>M-JOB-01</name><message><source>{task} cancelled.</source>"
        "</message></context></TS>",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("Pick a colour.\nThe programme.\n", encoding="utf-8")
    findings = check_spelling.check(catalog, (readme,), tmp_path)
    assert [str(f) for f in findings] == [
        "verdra_en.ts [M-JOB-01]: British spelling 'cancelled'; use the US form "
        "(canceled, canceling)",
        "README.md:1: British spelling 'colour'; use the US form (color)",
    ]


def test_the_repository_passes() -> None:
    assert check_spelling.check() == []


def test_identifiers_flags_and_file_names_are_checked(tmp_path: Path) -> None:
    """Decision record 0011: code identifiers, settings keys and flags use US spelling too."""
    source = (
        '"""Docstrings are prose: colour, catalogue."""\n'
        "# Comments are prose too: behaviour.\n"
        "CLIENT_BEHAVIOUR = 'client_behaviour'\n"
        "def css_colour(start_minimised: bool) -> str:\n"
        "    return '--minimised' if start_minimised else 'verdra.catalogue'\n"
    )
    findings = check_spelling.check_identifiers(source, "x.py", set())
    words = [(finding.where, finding.word) for finding in findings]
    assert words == [
        ("x.py:3 (CLIENT_BEHAVIOUR)", "BEHAVIOUR"),
        ("x.py:4 (css_colour)", "colour"),
        ("x.py:4 (start_minimised)", "minimised"),
        ("x.py:5 ('--minimised')", "minimised"),
        ("x.py:5 (start_minimised)", "minimised"),
    ]
    assert check_spelling.check_identifiers("colour_ok = 1\n", "x.py", {"colour"}) == []
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "check_colours.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.verdra]\n", encoding="utf-8")
    found = check_spelling.check(tmp_path / "none.ts", (), tmp_path)
    assert [str(finding) for finding in found] == [
        "tools/check_colours.py (file name): British spelling 'colours'; use the US form (color)"
    ]


def test_the_changelog_and_readme_are_checked() -> None:
    """Plan 16.2, "M1 decisions": both become release notes, so the gate reads them."""
    names = {path.name for path in check_spelling.DOCUMENTS}
    assert {"CHANGELOG.md", "README.md"} <= names


@pytest.mark.parametrize("name", ["CHANGELOG.md", "README.md"])
def test_a_british_spelling_planted_in_the_release_notes_fails_the_gate(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.verdra]\n", encoding="utf-8")
    document = tmp_path / name
    document.write_text("# Notes\n\n- The pill shows the right colour.\n", encoding="utf-8")
    findings = check_spelling.check(tmp_path / "none.ts", (document,), tmp_path)
    assert [str(f) for f in findings] == [
        f"{name}:3: British spelling 'colour'; use the US form (color)"
    ]
