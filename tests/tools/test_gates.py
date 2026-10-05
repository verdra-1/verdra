# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/gates.py runs each CI job's own steps, with that job's dependency groups."""

import os
import platform
import sys
from pathlib import Path

import pytest

from tools import gates


def test_it_reads_the_real_workflow() -> None:
    jobs = gates.load_jobs()
    assert set(gates.DEFAULT_JOBS) <= set(jobs)
    for name in ("checks", "tests", "build"):
        commands = [command for _, command, _ in gates.steps(jobs[name], network=True) if command]
        # Every job starts by installing its own groups, as on the runner.
        assert commands[0].startswith("uv sync"), name


def test_the_static_job_runs_types_before_the_groups_widen() -> None:
    """The #44 lesson: pyright runs with the default groups; the licence step adds the rest."""
    names = [name for name, _, _ in gates.steps(gates.load_jobs()["checks"], network=True)]
    assert names.index("Types") < names.index("Licences (runtime, dev and build groups)")


def test_runner_only_and_network_steps_are_skipped_and_named() -> None:
    job = {
        "steps": [
            {"name": "Qt system libraries", "run": "sudo apt-get install -y libegl1"},
            {"name": "Vulnerabilities", "run": "uv run pip-audit"},
            {"name": "Lint", "run": "uv run ruff check ."},
            {"uses": "actions/checkout@abc"},
        ]
    }
    assert gates.steps(job, network=False) == [
        ("Qt system libraries", None, "needs the CI runner"),
        ("Vulnerabilities", None, "needs the internet (--network)"),
        ("Lint", "uv run ruff check .", ""),
    ]
    assert gates.steps(job, network=True)[1] == ("Vulnerabilities", "uv run pip-audit", "")


def test_expressions_are_filled_for_this_machine() -> None:
    values = {"matrix.system": gates.system()}
    assert gates.expand("floors --system ${{ matrix.system }}", values).endswith(gates.system())
    assert gates.expand("x${{ matrix.runner }}y", values) == "xy"
    expected = "windows" if platform.system() == "Windows" else "linux"
    assert gates.system() == expected


@pytest.mark.skipif(
    bool(os.environ.get("VERDRA_PYTHON_UNPINNED")),
    reason="the nightly job that tries the newest Python 3.14 on purpose",
)
def test_the_pinned_python_is_the_one_in_use() -> None:
    """CI and local runs use exactly the patch in .python-version (plan 16.2)."""
    pinned = gates.pinned_python()
    assert pinned.count(".") == 2, "pin the exact patch version"
    assert "{}.{}.{}".format(*sys.version_info[:3]) == pinned


def test_a_wrong_python_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pin = tmp_path / ".python-version"
    pin.write_text("3.14.0\n", encoding="utf-8")
    monkeypatch.setattr(gates, "PYTHON_VERSION", pin)
    problem = gates.check_python()
    assert problem is not None
    assert problem.endswith("but .python-version pins 3.14.0")
