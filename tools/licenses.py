# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Licence gate: installed packages and Qt imports against the allowlists.

Runs `pip-licenses` in the current environment and compares every package's licence with
`[tool.verdra.licenses]` in pyproject.toml (Master plan 12.3, Reference R4). A licence expression
passes when any alternative of an OR is allowed and every part of an AND is allowed. It also scans
`src/` for `PySide6.Qt*` imports outside `[tool.verdra.qt] allowed-modules`.

The gate covers every dependency group: runtime, dev and build (decision record 0010). It reads
the locked package list for this system from `uv export --all-groups` and fails when any of
those packages is not installed, so it can never pass on a partial environment. Install all
groups first with `uv sync --all-groups`.

Usage: uv run python tools/licenses.py [--qt-only] [--report]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Free-text classifier names and SPDX spellings mapped onto the allowlist's identifiers.
ALIASES: dict[str, str] = {
    "mit license": "MIT",
    "mit-0": "MIT",
    "bsd license": "BSD-3-Clause",
    "bsd": "BSD-3-Clause",
    "bsd-3-clause license": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "simplified bsd": "BSD-2-Clause",
    "isc license (iscl)": "ISC",
    "isc license": "ISC",
    "apache software license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "python software foundation license": "PSF-2.0",
    "psf": "PSF-2.0",
    "psf-2.0": "PSF-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "historical permission notice and disclaimer (hpnd)": "HPND",
    "the unlicense (unlicense)": "Unlicense",
    "public domain": "public domain",
    "cc0-1.0": "public domain",
}


def load_config() -> dict[str, Any]:
    """Return the `[tool.verdra]` table from pyproject.toml."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["verdra"]


def normalize(term: str) -> str:
    """Map one licence name onto its allowlist spelling."""
    term = term.strip()
    return ALIASES.get(term.lower(), term)


def expression_allowed(expression: str, allowed: set[str]) -> bool:
    """Return whether a licence expression or classifier list is acceptable.

    `pip-licenses` joins several classifiers with "; ". Each joined name is one acceptable
    alternative, like an SPDX OR.
    """
    alternatives = re.split(r";\s*|\s+OR\s+", expression)
    for alternative in alternatives:
        parts = re.split(r"\s+AND\s+", alternative.strip())
        names = [normalize(part) for part in parts if part.strip()]
        if names and all(name in allowed for name in names):
            return True
    return False


def canonical(name: str) -> str:
    """Return a package name in its normalised form (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_packages() -> set[str]:
    """Return every package the lockfile installs on this system, across all groups."""
    from packaging.markers import Marker  # noqa: PLC0415 - only needed for the full gate

    exported = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["uv", "export", "--frozen", "--all-groups", "--no-hashes", "--no-emit-project"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    packages: set[str] = set()
    for line in exported.splitlines():
        if not line or line.startswith(("#", " ", "-")):
            continue
        requirement, _, marker = line.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate():
            continue
        packages.add(canonical(requirement.split("==")[0].strip()))
    return packages


def installed_licenses() -> list[dict[str, str]]:
    """Return name, version and licence of every installed package (from pip-licenses)."""
    result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        [sys.executable, "-m", "piplicenses", "--from=mixed", "--with-system", "--format=json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        {
            "name": str(item["Name"]),
            "version": str(item["Version"]),
            "license": str(item["License"]),
        }
        for item in json.loads(result.stdout)
    ]


def missing_packages(installed: list[dict[str, str]], locked: set[str]) -> list[str]:
    """Return one problem line per locked package that is not installed."""
    present = {canonical(item["name"]) for item in installed} | {"verdra"}
    return [
        f"{name}: locked but not installed; run `uv sync --all-groups` before this gate"
        for name in sorted(locked - present)
    ]


def check_licenses(config: dict[str, Any]) -> list[str]:
    """Return one problem line per package whose licence is not allowed."""
    table = config["licenses"]
    allowed = {normalize(name) for name in table["allowed"]}
    exceptions = {name.lower() for name in table.get("exceptions", {})}
    installed = installed_licenses()
    problems = missing_packages(installed, locked_packages())
    for package in installed:
        name, license = package["name"], package["license"]
        if name.lower() in exceptions or name.lower() == "verdra":
            continue
        if not expression_allowed(license, allowed):
            problems.append(f"{name} {package['version']}: licence {license!r} is not allowed")
    return problems


def report() -> str:
    """Return every installed package's licence, grouped by licence, as Markdown."""
    groups: dict[str, list[str]] = {}
    for package in installed_licenses():
        groups.setdefault(package["license"], []).append(f"{package['name']} {package['version']}")
    lines = ["| Licence | Packages |", "| --- | --- |"]
    for license in sorted(groups, key=str.lower):
        lines.append(f"| {license} | {', '.join(sorted(groups[license], key=str.lower))} |")
    qt = load_config()["licenses"].get("qt-exceptions", {})
    if qt:
        lines += ["", "| Inside Qt libraries (named exception) | Reason |", "| --- | --- |"]
        lines += [f"| {license} | {reason} |" for license, reason in sorted(qt.items())]
    return "\n".join(lines)


def check_qt_imports(config: dict[str, Any]) -> list[str]:
    """Return one problem line per import of a Qt module outside the allowed list."""
    table = config["qt"]
    allowed = set(table["allowed-modules"])
    problems: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module == "PySide6":
                modules = [f"PySide6.{alias.name}" for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                parts = module.split(".")
                is_qt = parts[0] == "PySide6" and len(parts) > 1 and parts[1].startswith("Qt")
                if is_qt and parts[1] not in allowed:
                    relative = path.relative_to(ROOT)
                    problems.append(
                        f"{relative}:{node.lineno}: Qt module {parts[1]} is not allowed"
                    )
    return problems


def main() -> int:
    """Run the gate and return a process exit code."""
    parser = argparse.ArgumentParser(description="Licence gate")
    parser.add_argument("--qt-only", action="store_true", help="only check Qt imports")
    parser.add_argument("--report", action="store_true", help="print every package's licence")
    arguments = parser.parse_args()
    if arguments.report:
        print(report())
    config = load_config()
    problems = check_qt_imports(config)
    if not arguments.qt_only:
        problems += check_licenses(config)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} licence problem(s).")
        return 1
    print("Licences and Qt modules are within the allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
