# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Colour gate: no colour literals outside the token file and generated files.

Master plan 5 and 12.3: `src/verdra/assets/brand/tokens.json` is the only place colour values
live, and 5.6 says the style sheet never contains literal colours. This check scans tracked
source, style and markup files outside the allowed paths for:

- hex literals: `#rgb`, `#rrggbb`, `#rrggbbaa`;
- functional notation with numbers: `rgb(255, 0, 0)`, `rgba(…)`, `hsl(…)`, `hsla(…)`, `hwb(…)`,
  `lab(…)`, `lch(…)`, `oklab(…)`, `oklch(…)`, `color(srgb 1 0 0)`;
- `QColor` built or set from numbers or a name (`QColor(255, 0, 0)`, `QColor("red")`,
  `QColor.fromRgb(…)`, `QColor.fromString("red")`, `color.setRgb(…)`, `color.setNamedColor(…)`);
- Qt's named colours (`Qt.GlobalColor.red`, `Qt.red`), except `transparent`, which is no colour,
  and `QColorConstants` (`QColorConstants.Svg.red`);
- CSS colour names as a style property's value (`color: red`, `fill: red`) or as an SVG
  paint attribute (`fill="red"`, `stroke="navy"`, `stop-color="gold"`).

Usage: python tools/check_colors.py [paths...]   (no paths: every tracked file)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

# Where color values may appear.
ALLOWED = (
    "src/verdra/assets/brand/tokens.json",
    # SVGs generated from tokens.json by tools/icons.py (checked to be up to date in CI).
    "src/verdra/assets/brand/*.svg",
    "src/verdra/assets/brand/generated/*",
    # Third-party icon files are recoloured from tokens at runtime; their sources carry none,
    # but the folder is listed so a future upstream file can't fail the gate by accident.
    "src/verdra/assets/icons/lucide/*.svg",
    # This gate and its tests name the patterns they look for.
    "tools/check_colors.py",
    "tests/tools/test_check_colors.py",
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

# A hex color: '#' then 3, 4, 6 or 8 hex digits, ending at a word boundary and not preceded by a
# word character or '&' (HTML character references). Issue numbers in prose live in .md files,
# which aren't scanned.
HEX_COLOR = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
FUNCTIONAL = re.compile(
    r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(\s*[-+\d.]"
    r"|\bcolor\(\s*(?:srgb|srgb-linear|display-p3|a98-rgb|prophoto-rgb|rec2020|xyz)\b",
    re.IGNORECASE,
)
QCOLOR = re.compile(r"\bQColor\(\s*(?:\d|[\"'][A-Za-z])")
#: QColor's factories and setters given numbers or a name (a token's value goes through
#: QColor(value) or QColor.fromString(value) with a variable, which is allowed).
QCOLOR_FROM = re.compile(
    r"\bQColor\.from(?:Rgb|RgbF|Rgba64|Hsv|HsvF|Hsl|HslF|Cmyk|CmykF|String)\(\s*[-+\d.\"']"
    r"|\.set(?:Rgb|RgbF|Rgba|Rgba64|Hsv|HsvF|Hsl|HslF|Cmyk|CmykF|NamedColor)\(\s*[-+\d.\"']"
)
QCOLOR_CONSTANTS = re.compile(r"\bQColorConstants\b")
#: Qt's named colors (Qt::GlobalColor), as `Qt.GlobalColor.x` or the short `Qt.x`.
QT_NAMES = (
    "white|black|red|darkRed|green|darkGreen|blue|darkBlue|cyan|darkCyan|magenta|darkMagenta|"
    "yellow|darkYellow|gray|darkGray|lightGray|color0|color1"
)
QT_COLOR = re.compile(rf"\bQt\.(?:GlobalColor\.)?(?:{QT_NAMES})\b")
CSS_NAMES = (
    "black|white|red|green|blue|yellow|orange|purple|pink|brown|gray|grey|silver|maroon|navy|"
    "olive|teal|lime|aqua|fuchsia|cyan|magenta|gold|indigo|violet|crimson|coral|salmon|khaki"
)
CSS_COLOR = re.compile(
    rf"\b(?:color|background(?:-color)?|border(?:-[a-z]+)?|outline|fill|stroke|"
    rf"(?:stop|flood|lighting)-color|"
    rf"selection-(?:background-)?color|gridline-color|alternate-background-color)\s*:"
    rf"[^;{{}}\n]*\b(?:{CSS_NAMES})\b",
    re.IGNORECASE,
)
SVG_PAINT = re.compile(
    rf"\b(?:fill|stroke|(?:stop|flood|lighting)-color|color)\s*=\s*[\"']\s*(?:{CSS_NAMES})\b",
    re.IGNORECASE,
)
PATTERNS = (
    HEX_COLOR,
    FUNCTIONAL,
    QCOLOR,
    QCOLOR_FROM,
    QCOLOR_CONSTANTS,
    QT_COLOR,
    CSS_COLOR,
    SVG_PAINT,
)


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
        for pattern in PATTERNS:
            for match in pattern.finditer(line):
                problems.append(
                    f"{path}:{number}: colour literal {match.group(0)!r}; "
                    "use a token from tokens.json"
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
