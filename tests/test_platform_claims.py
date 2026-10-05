# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""No text claims Verdra runs on Linux or macOS (decision record 0018, plan 16.2).

Windows is the only platform until further notice: Linux is paused and macOS is deferred
(decision record 0014). User-facing and project texts may name Linux, macOS, Sober or Ubuntu
only together with what makes their status plain: paused, deferred, planned later, not
supported, kept for reference. Each paragraph, list item, table row, quote and catalogue source
string is checked on its own; a section whose heading says it is paused or reference only, and a
page whose opening banner says so, are reference as a whole.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: The texts people read about Verdra (and the rules sessions follow).
DOCUMENTS = sorted(
    {
        *(ROOT / name for name in ("README.md", "PRIVACY.md", "SECURITY.md", "CONTRIBUTING.md")),
        *(ROOT / name for name in ("CODE_OF_CONDUCT.md", "CLAUDE.md")),
        ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
        *(ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"),
        *(ROOT / "docs" / "guides").rglob("*.md"),
        *(ROOT / "docs" / "specs").glob("*.md"),
        *(ROOT / "docs" / "platforms").glob("*.md"),
        ROOT / "docs" / "glossary.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "src" / "verdra" / "assets" / "brand" / "README.md",
    }
)
MESSAGES = ROOT / "src" / "verdra" / "assets" / "i18n" / "verdra_en.ts"
CHANGELOG = ROOT / "CHANGELOG.md"

#: The other systems by name ("The Linux Foundation", in the DCO text, isn't one).
OTHER_SYSTEM = re.compile(
    r"\b(linux(?! foundation)|macos|mac os|sober|ubuntu|flatpak)\b", re.IGNORECASE
)
#: Words that make the status plain.
STATUS = re.compile(
    r"paused|deferred|planned later|for later|not supported|isn't supported|unsupported|"
    r"doesn't run|reference|retired|left with|no longer|windows only|only (supported )?"
    r"(platform|system)|amended",
    re.IGNORECASE,
)
_BLOCK_START = re.compile(r"^\s*(?:[-*] |\d+\. |\||#|>)")
_YAML_KEY = re.compile(r"^\s*[\w-]+:")


def blocks(text: str, *, yaml: bool = False) -> list[str]:
    """Split Markdown or YAML into paragraphs, list items, rows and headings, minus reference parts.

    A page whose first quote block says "paused" or "deferred" is reference as a whole; so is a
    section whose heading says it is paused or reference only, down to the next heading of the
    same or a higher level.
    """
    lines = text.splitlines()
    opening = "\n".join(lines[:15])
    if re.search(r"^> \*\*(Paused|Deferred)", opening, re.MULTILINE):
        return []
    found: list[str] = []
    current: list[str] = []
    skip_level: int | None = None
    for line in lines:
        heading = re.match(r"^(#+)\s+(.*)", line)
        if heading:
            level = len(heading.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and STATUS.search(heading.group(2)):
                skip_level = level
        if skip_level is not None:
            continue
        if not line.strip() or _BLOCK_START.match(line) or (yaml and _YAML_KEY.match(line)):
            if current:
                found.append(" ".join(current))
            current = [line.strip()] if line.strip() else []
        else:
            current.append(line.strip())
    if current:
        found.append(" ".join(current))
    return found


def unreleased(text: str) -> str:
    """Return the CHANGELOG's Unreleased section (released entries are history)."""
    start = text.index("## [Unreleased]")
    following = text.find("\n## [", start + 1)
    return text[start : following if following > 0 else None]


def sentences(block: str) -> list[str]:
    """Split a block into sentences: a status word must stand in the same sentence."""
    return re.split(r"(?<=[.!?])\s+(?=\S)", block)


def claims(texts: dict[str, list[str]]) -> list[str]:
    return [
        f"{name}: {sentence[:160]}"
        for name, items in texts.items()
        for block in items
        for sentence in sentences(block)
        if OTHER_SYSTEM.search(sentence) and not STATUS.search(sentence)
    ]


def test_no_text_claims_linux_or_macos_support() -> None:
    texts = {
        path.relative_to(ROOT).as_posix(): blocks(
            path.read_text("utf-8"), yaml=path.suffix == ".yml"
        )
        for path in DOCUMENTS
    }
    texts["CHANGELOG.md [Unreleased]"] = blocks(unreleased(CHANGELOG.read_text("utf-8")))
    sources = re.findall(r"<source>(.*?)</source>", MESSAGES.read_text("utf-8"), re.DOTALL)
    texts[MESSAGES.name] = sources
    assert len(texts) > 20  # the scan sees the documents it should
    found = claims(texts)
    assert found == [], "\n".join(found)


@pytest.mark.parametrize(
    ("text", "claims_support"),
    [
        ("Works with the Roblox Player on Windows and on Linux with Sober.", True),
        ("Works on Windows and on Linux with Sober.\nmacOS isn't supported before 1.0.", True),
        ("- Left-click opens the window on Windows and Linux.", True),
        ("| Logs | `%LOCALAPPDATA%` | `~/.local/state` (Linux) |", True),
        ("Linux is paused and macOS is deferred, both planned later.", False),
        ("> **Paused, planned later.** Verdra doesn't run on Linux.\n\n| L-01 | Sober |", False),
        ("## Linux steps: paused, reference only\n\n### L-01\n\nRun Sober.\n\n## Windows", False),
    ],
)
def test_the_scan_tells_claims_from_status(text: str, *, claims_support: bool) -> None:
    assert bool(claims({"probe": blocks(text)})) is claims_support
