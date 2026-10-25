# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Every Verdra command a guide gives the owner must parse (22 October 2026).

The TLS-check guide showed `run-latest.ps1 --format-check` without its asset ID, so Verdra
stopped with "argument --format-check: expected one argument" and the owner lost a run.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
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


#: A tool command a guide gives the owner, run from Verdra's folder (`uv run --directory`).
TOOL = re.compile(r"uv run --directory \"[^\"]*\" python (?P<arguments>.*)$")
ROOT = GUIDES.parents[1]


def tool_commands() -> list[tuple[str, int, list[str]]]:
    """Return (guide, line number, Python's arguments up to the tool) for every tool command."""
    found: list[tuple[str, int, list[str]]] = []
    for guide in sorted(GUIDES.glob("*.md")):
        for number, line in enumerate(guide.read_text(encoding="utf-8").splitlines(), 1):
            match = TOOL.search(line.strip())
            if match is None:
                continue
            words = match["arguments"].split()
            tool = words[:2] if words[0] == "-m" else [words[0].replace("\\", "/")]
            found.append((guide.name, number, tool))
    return found


def test_the_guides_give_tool_commands() -> None:
    assert any(tool == ["-m", "tools.store_swap"] for _g, _l, tool in tool_commands())


@pytest.mark.parametrize(("guide", "line", "tool"), tool_commands())
def test_each_guide_tool_starts_the_way_the_guide_runs_it(
    guide: str, line: int, tool: list[str]
) -> None:
    """23 October 2026: `python tools\\store_swap.py` stopped with "No module named 'tools'"."""
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(  # noqa: S603 - the guide's own command, with --help
        [sys.executable, *tool, "--help"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, f"{guide}:{line}: {' '.join(tool)} failed:\n{done.stderr}"


def importing_tools() -> list[str]:
    """Every tool that imports another tool (`from tools import …`), as a path from Verdra's folder."""
    return sorted(
        f"tools/{path.name}"
        for path in (ROOT / "tools").glob("*.py")
        if re.search(r"^from tools import|^import tools", path.read_text("utf-8"), re.MULTILINE)
    )


def test_some_tools_import_other_tools() -> None:
    assert "tools/store_swap.py" in importing_tools()


@pytest.mark.parametrize("tool", importing_tools())
def test_a_tool_that_imports_tools_starts_as_a_file(tool: str) -> None:
    """25 October 2026: `python tools\\store_swap.py` needs Verdra's folder on sys.path itself."""
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(  # noqa: S603 - Verdra's own tool, with --help
        [sys.executable, tool, "--help"],
        cwd=ROOT,  # as `uv run --directory`: Python puts tools/, not Verdra's folder, on sys.path
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, f"{tool} failed:\n{done.stderr}"
