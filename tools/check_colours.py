# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Colour gate: no hex colour literals outside the token file and generated files.

Master plan 5 and 12.3: `src/verdra/assets/brand/tokens.json` is the only place colour values
live. This check scans tracked source, style and markup files for `#rgb`, `#rrggbb` and
`#rrggbbaa` literals and fails on any it finds outside the allowed paths.

Usage: python tools/check_colours.py [paths...]   (no paths: every tracked file)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

# Where colour values may appear.
ALLOWED = (
    "src/verdra/assets/brand/tokens.json",
    # SVGs generated from tokens.json by tools/icons.py (checked to be up to date in CI).
    "src/verdra/assets/brand/*.svg",
    "src/verdra/assets/brand/generated/*",
    # Third-party icon files are recoloured from tokens at runtime; their sources carry none,
    # but the folder is listed so a future upstream file can't fail the gate by accident.
    "src/verdra/assets/icons/lucide/*.svg",
)

SCANNED_SUFFIXES = {
    ".py",
    ".qss",
    ".css",
    ".svg",
    ".ui",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".html",
}

# A hex colour: '#' then 3, 4, 6 or 8 hex digits, ending at a word boundary and not preceded by a
# word character or '&' (HTML character references). Issue numbers in prose live in .md files,
# which aren't scanned.
HEX_COLOUR = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")


def is_allowed(path: str) -> bool:
    """Return whether colour literals are permitted in this repository-relative path."""
    pure = PurePosixPath(path)
    return any(pure.full_match(pattern) for pattern in ALLOWED)


def tracked_files() -> list[str]:
    """Return every file Git tracks, relative to the repository root."""
    result = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 - git from PATH is the point
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result.stdout.splitlines()


def scan(path: str) -> list[str]:
    """Return one problem line per colour literal in the file."""
    file = ROOT / path
    if file.suffix not in SCANNED_SUFFIXES or is_allowed(path) or not file.is_file():
        return []
    problems: list[str] = []
    for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        for match in HEX_COLOUR.finditer(line):
            problems.append(
                f"{path}:{number}: colour literal {match.group(0)}; use a token from tokens.json"
            )
    return problems


def main(argv: list[str]) -> int:
    """Run the gate over the given paths (or every tracked file) and return an exit code."""
    paths = [Path(arg).resolve().relative_to(ROOT).as_posix() for arg in argv] or tracked_files()
    problems = [problem for path in paths for problem in scan(path)]
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
