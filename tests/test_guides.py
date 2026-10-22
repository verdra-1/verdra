# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Every Verdra command a guide gives the owner must parse (22 October 2026).

The TLS-check guide showed `run-latest.ps1 --format-check` without its asset ID, so Verdra
stopped with "argument --format-check: expected one argument" and the owner lost a run.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from verdra.trunk.sapwood import cli

GUIDES = Path(__file__).resolve().parents[1] / "docs" / "guides"
#: The script that passes everything after its path to Verdra (decision record 0021).
SCRIPT = re.compile(r"run-latest\.ps1\"?(?P<arguments>.*)$")


def commands() -> list[tuple[str, int, list[str]]]:
    """Return (guide, line number, Verdra's arguments) for every run-latest.ps1 command."""
    found: list[tuple[str, int, list[str]]] = []
    for guide in sorted(GUIDES.glob("*.md")):
        for number, line in enumerate(guide.read_text(encoding="utf-8").splitlines(), 1):
            match = SCRIPT.search(line.strip())
            if match is None or "`" in match["arguments"]:
                continue  # prose that names the script, not a command
            arguments = [a for a in shlex.split(match["arguments"]) if a != "-NoStart"]
            found.append((guide.name, number, arguments))
    return found


def test_the_guides_give_commands() -> None:
    assert any(arguments for _guide, _line, arguments in commands())


@pytest.mark.parametrize(("guide", "line", "arguments"), commands())
def test_each_guide_command_parses(guide: str, line: int, arguments: list[str]) -> None:
    assert cli.diagnosis_available()  # tests run from source, like the owner's command
    try:
        parsed = cli.parse(arguments)
    except SystemExit as error:
        pytest.fail(f"{guide}:{line}: Verdra would stop on {arguments} (exit {error.code})")
    flags = [a for a in arguments if a.startswith("--")]
    assert parsed != cli.Arguments() or not flags, f"{guide}:{line}: {flags} did nothing"
