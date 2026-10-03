# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Command-line flags: --reset-everything [--quiet], --minimized, a roblox-player: link.

Qt's own arguments (such as `-platform offscreen`) are left for Qt; anything else unknown is
ignored rather than refused, so a launcher passing extra arguments can't stop Verdra starting.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from verdra.soil import terrain


@dataclass(frozen=True)
class Arguments:
    """What the command line asked for."""

    reset_everything: bool = False
    quiet: bool = False
    minimized: bool = False
    link: str | None = None


def parse(argv: list[str]) -> Arguments:
    """Parse the arguments after the program name."""
    parser = argparse.ArgumentParser(prog=terrain.EXECUTABLE, add_help=False)
    parser.add_argument("--reset-everything", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    known, rest = parser.parse_known_args(argv)
    scheme = terrain.URL_SCHEME + ":"
    link = next((item for item in rest if item.lower().startswith(scheme)), None)
    return Arguments(
        reset_everything=known.reset_everything,
        quiet=known.quiet,
        minimized=known.minimized,
        link=link,
    )
