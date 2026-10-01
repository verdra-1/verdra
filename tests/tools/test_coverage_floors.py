# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the coverage gate."""

from tools.coverage_floors import area_totals, check


def entry(covered: int, statements: int) -> dict:
    return {
        "summary": {"covered_lines": covered, "num_statements": statements},
        "executed_lines": [],
        "missing_lines": [],
    }


REPORT = {
    "files": {
        "src/verdra/trunk/rings.py": entry(90, 100),
        "D:\\a\\verdra\\src\\verdra\\canopy\\crown\\window.py": entry(50, 100),
        "src/verdra/soil/atomic.py": entry(80, 100),
        "src/verdra/soil/meadow/launcher.py": entry(0, 100),
        "src/verdra/__main__.py": entry(0, 10),
    }
}


def test_soil_counts_only_the_current_system() -> None:
    assert area_totals(REPORT, "linux")["soil"] == (80, 100)
    assert area_totals(REPORT, "windows")["soil"] == (80, 200)


def test_floors() -> None:
    problems = check(REPORT, "linux", None)
    assert problems == ["canopy: 50.0% of lines covered, floor is 60%"]
