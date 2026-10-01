# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Coverage gate: per-area line floors and the changed-lines floor (Master plan 12.1).

Reads a `coverage json` report and checks:

- trunk, roots, bark, seedbank and strata at least 85% of lines;
- canopy at least 60%;
- soil at least 70%, counting only the shared modules and the package for the system the report
  came from (`--system windows|macos|linux`; omit it for the combined report, which counts all);
- with `--diff-base REF`, at least 80% of the executable lines a pull request adds or changes.

An area with no executable lines yet passes. Usage:
    python tools/coverage_floors.py coverage.json [--system linux] [--diff-base origin/main]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

FLOORS: dict[str, float] = {
    "trunk": 85.0,
    "roots": 85.0,
    "bark": 85.0,
    "seedbank": 85.0,
    "strata": 85.0,
    "canopy": 60.0,
    "soil": 70.0,
}
CHANGED_LINES_FLOOR = 80.0
SYSTEM_PACKAGES = {"windows": "meadow", "macos": "orchard", "linux": "tundra"}


def repo_path(name: str) -> PurePosixPath:
    """Return a report file name as a repository-relative POSIX path."""
    posix = name.replace("\\", "/")
    index = posix.find("src/verdra/")
    return PurePosixPath(posix[index:] if index >= 0 else posix)


def area_of(path: PurePosixPath) -> str | None:
    """Return the top-level area a module belongs to, or None for top-level modules."""
    parts = path.parts
    return parts[2] if len(parts) > 3 and parts[:2] == ("src", "verdra") else None


def counted(path: PurePosixPath, system: str | None) -> bool:
    """Return whether a soil module counts towards the floor on this system."""
    parts = path.parts
    if area_of(path) != "soil" or system is None or len(parts) < 5:
        return True
    return parts[3] not in SYSTEM_PACKAGES.values() or parts[3] == SYSTEM_PACKAGES[system]


def area_totals(report: dict, system: str | None) -> dict[str, tuple[int, int]]:
    """Return (covered, statements) per area."""
    totals: dict[str, tuple[int, int]] = {}
    for name, data in report["files"].items():
        path = repo_path(name)
        area = area_of(path)
        if area is None or not counted(path, system):
            continue
        covered, statements = totals.get(area, (0, 0))
        summary = data["summary"]
        totals[area] = (
            covered + summary["covered_lines"],
            statements + summary["num_statements"],
        )
    return totals


def changed_lines(base: str) -> dict[str, set[int]]:
    """Return the line numbers each file under src/ gained or changed since `base`."""
    diff = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", "src/"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    changes: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and current:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start, length = int(match.group(1)), int(match.group(2) or "1")
                changes.setdefault(current, set()).update(range(start, start + length))
    return changes


def check(report: dict, system: str | None, base: str | None) -> list[str]:
    """Return one problem per floor that isn't met, after printing a summary."""
    problems: list[str] = []
    for area, (covered, statements) in sorted(area_totals(report, system).items()):
        floor = FLOORS.get(area)
        if floor is None or statements == 0:
            continue
        percent = 100.0 * covered / statements
        print(f"{area:10} {percent:6.1f}%  ({covered}/{statements}, floor {floor:.0f}%)")
        if percent < floor:
            problems.append(f"{area}: {percent:.1f}% of lines covered, floor is {floor:.0f}%")
    if base:
        files = {str(repo_path(name)): data for name, data in report["files"].items()}
        executable = hit = 0
        for name, lines in changed_lines(base).items():
            data = files.get(name)
            if data is None:
                continue
            executed = set(data["executed_lines"])
            missing = set(data["missing_lines"])
            executable += len(lines & (executed | missing))
            hit += len(lines & executed)
        if executable:
            percent = 100.0 * hit / executable
            print(f"changed    {percent:6.1f}%  ({hit}/{executable}, floor 80%)")
            if percent < CHANGED_LINES_FLOOR:
                problems.append(f"changed lines: {percent:.1f}% covered, floor is 80%")
    return problems


def main() -> int:
    """Run the gate and return a process exit code."""
    parser = argparse.ArgumentParser(description="Coverage floors")
    parser.add_argument("report", type=Path)
    parser.add_argument("--system", choices=sorted(SYSTEM_PACKAGES))
    parser.add_argument("--diff-base")
    arguments = parser.parse_args()
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    problems = check(report, arguments.system, arguments.diff_base)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
