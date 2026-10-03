# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Command-line flags: --reset-everything [--quiet], --minimized, a roblox-player: link.

Qt's own arguments (such as `-platform offscreen`) are left for Qt; anything else unknown is
ignored rather than refused, so a launcher passing extra arguments can't stop Verdra starting.

The one exception is `--diagnose-interception` (spec S-11, plan 16.2): it is offered only while
Verdra runs from source, where its module (roots/litmus.py) is present. A frozen build doesn't
have that module, so there argparse rejects the flag as unknown and Verdra exits with code 2
before anything starts (decision record 0015).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from verdra import roots
from verdra.soil import terrain


@dataclass(frozen=True)
class Arguments:
    """What the command line asked for."""

    reset_everything: bool = False
    quiet: bool = False
    minimized: bool = False
    link: str | None = None
    diagnose_interception: bool = False


DIAGNOSE_FLAG = "--diagnose-interception"
#: The source-only module the flag needs (roots/litmus.py); frozen builds leave it out.
DIAGNOSTIC_SOURCE = "litmus.py"


def diagnosis_available() -> bool:
    """Return whether Verdra runs from source, with the diagnostic module's source present."""
    if getattr(sys, "frozen", False):
        return False
    return Path(roots.__file__).with_name(DIAGNOSTIC_SOURCE).is_file()


def parse(argv: list[str]) -> Arguments:
    """Parse the arguments after the program name.

    Raises:
        SystemExit: `--diagnose-interception` was given to a frozen build (code 2).
    """
    parser = argparse.ArgumentParser(prog=terrain.EXECUTABLE, add_help=False)
    parser.add_argument("--reset-everything", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    diagnose = DIAGNOSE_FLAG in argv
    if diagnose and not diagnosis_available():
        # argparse's own "unrecognized arguments" error, then exit code 2.
        parser.parse_args([DIAGNOSE_FLAG])
    known, rest = parser.parse_known_args([item for item in argv if item != DIAGNOSE_FLAG])
    scheme = terrain.URL_SCHEME + ":"
    link = next((item for item in rest if item.lower().startswith(scheme)), None)
    return Arguments(
        reset_everything=known.reset_everything,
        quiet=known.quiet,
        minimized=known.minimized,
        link=link,
        diagnose_interception=diagnose,
    )
