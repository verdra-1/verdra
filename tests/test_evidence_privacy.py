# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Committed real-machine evidence carries nothing personal (maintainer's rule, 2026-10-04).

Evidence under docs/platforms/evidence/ holds names, sizes, hashes and anonymised host and
path names only: never a user name in a path, a folder named only with digits (a Roblox user
ID), a query string, a signed-URL token or a long numeric ID in a path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "platforms" / "evidence"

FORBIDDEN = {
    "a user name in a Windows path": re.compile(r"[A-Za-z]:\\Users\\(?!%)[^\\\s]+", re.IGNORECASE),
    "a user name in a Linux path": re.compile(r"/home/(?!runner\b)[^/\s]+"),
    "a folder or file named only with digits": re.compile(
        r"(?:folder|file) \| \d+\s*$", re.MULTILINE
    ),
    "a signed-URL secret": re.compile(
        r"__token__|hmac=|[?&](?:sig|signature|token|ticket)=", re.IGNORECASE
    ),
    "a query string": re.compile(r"https?://\S+\?\S+=|\s/\S*\?\S+="),
    "a long numeric ID in a path": re.compile(r"/\d{6,}(?=/|\s|$)"),
}


def evidence_files() -> list[Path]:
    """Evidence from real machines. CI-runner evidence (`ci-run-*`) comes from throwaway public
    runners and quotes public run links and the installer's download address."""
    return sorted(
        path
        for path in EVIDENCE.rglob("*")
        if path.is_file() and not path.name.startswith("ci-run-")
    )


def test_there_is_evidence_to_check() -> None:
    assert len(evidence_files()) >= 2


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_no_evidence_file_holds_anything_personal(name: str) -> None:
    found = [
        f"{path.relative_to(EVIDENCE)}: {match[0]}"
        for path in evidence_files()
        for match in FORBIDDEN[name].finditer(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert found == [], name


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("a user name in a Windows path", r"C:\Users\someone\AppData\Local\Roblox"),
        ("a folder or file named only with digits", "  folder | 1234567890"),
        ("a signed-URL secret", "GET fts.rbxcdn.com /sc7/abc?__token__=exp=1~hmac=ff"),
        ("a query string", "GET apis.roblox.com /v1/x?placeId=1"),
        (
            "a long numeric ID in a path",
            "GET apis.roblox.com /universes/v1/places/1234567/universe",
        ),
    ],
)
def test_the_patterns_catch_what_they_name(name: str, line: str) -> None:
    assert FORBIDDEN[name].search(line)
