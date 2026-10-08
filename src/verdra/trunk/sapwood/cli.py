# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Command-line flags: --reset-everything [--quiet], --minimized, a roblox-player: link.

Qt's own arguments (such as `-platform offscreen`) are left for Qt; anything else unknown is
ignored rather than refused, so a launcher passing extra arguments can't stop Verdra starting.

The exceptions are the diagnostics `--diagnose-interception` (spec S-11, plan 16.2) and
`--format-capture <asset IDs>` with `--save-bodies`, and `--control-swap ORIGINAL=DONOR` (spec
S-21, plan 16.2 of 8 October 2026):
they are offered only while Verdra runs from source, where their module (roots/litmus.py) is
present. A frozen build doesn't have that module, so there argparse rejects the flag as unknown
and Verdra exits with code 2 before anything starts (decision record 0015).
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
    #: Asset IDs whose CDN downloads a format capture reports (roots/litmus); () when off.
    format_capture: tuple[int, ...] = ()
    #: Also save each captured body next to its report.
    save_bodies: bool = False
    #: The control experiment (roots/litmus): (original, donor) asset IDs, or None when off.
    control_swap: tuple[int, int] | None = None
    #: Asset IDs whose downloads a format check reports as Verdra answers them; () when off.
    format_check: tuple[int, ...] = ()


DIAGNOSE_FLAG = "--diagnose-interception"
CAPTURE_FLAG = "--format-capture"
BODIES_FLAG = "--save-bodies"
CONTROL_FLAG = "--control-swap"
CHECK_FLAG = "--format-check"
#: Every flag that needs the source-only diagnostic module.
DIAGNOSTIC_FLAGS = (DIAGNOSE_FLAG, CAPTURE_FLAG, BODIES_FLAG, CONTROL_FLAG, CHECK_FLAG)
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
    asked = [flag for flag in DIAGNOSTIC_FLAGS if any(_is_flag(item, flag) for item in argv)]
    if asked and not diagnosis_available():
        # argparse's own "unrecognized arguments" error, then exit code 2.
        parser.parse_args([asked[0]])
    if diagnosis_available():
        parser.add_argument(CAPTURE_FLAG, type=_asset_ids, default=())
        parser.add_argument(BODIES_FLAG, action="store_true")
        parser.add_argument(CONTROL_FLAG, type=_asset_pair, default=None)
        parser.add_argument(CHECK_FLAG, type=_asset_ids, default=())
    known, rest = parser.parse_known_args([item for item in argv if item != DIAGNOSE_FLAG])
    scheme = terrain.URL_SCHEME + ":"
    link = next((item for item in rest if item.lower().startswith(scheme)), None)
    return Arguments(
        reset_everything=known.reset_everything,
        quiet=known.quiet,
        minimized=known.minimized,
        link=link,
        diagnose_interception=diagnose,
        format_capture=getattr(known, "format_capture", ()),
        save_bodies=getattr(known, "save_bodies", False),
        control_swap=getattr(known, "control_swap", None),
        format_check=getattr(known, "format_check", ()),
    )


def _is_flag(item: str, flag: str) -> bool:
    return item == flag or item.startswith(flag + "=")


def _asset_ids(text: str) -> tuple[int, ...]:
    """`15553230204,11473800131` as asset IDs (argparse turns a ValueError into exit code 2)."""
    ids = tuple(int(part) for part in text.replace(" ", "").split(",") if part)
    if not ids or any(asset_id <= 0 for asset_id in ids):
        msg = "give one or more asset IDs, separated by commas"
        raise ValueError(msg)
    return ids


def _asset_pair(text: str) -> tuple[int, int]:
    """`15553230204=11473800131` as (original, donor) (a ValueError becomes exit code 2)."""
    original, mark, donor = text.replace(" ", "").partition("=")
    if not mark or not original.isdigit() or not donor.isdigit() or original == donor:
        msg = "give ORIGINAL=DONOR, two different asset IDs"
        raise ValueError(msg)
    return int(original), int(donor)
