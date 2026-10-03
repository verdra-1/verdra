# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Run the CI gates locally, exactly as each CI job runs them (plan 16.2, "M1 decisions").

Reads `.github/workflows/ci.yml` and runs every `run:` step of the chosen jobs in order, in this
checkout, with that job's environment. Each job starts from the dependency groups its own
`uv sync` step installs: a step that changes the groups (the licence step's
`uv sync --all-groups`, for example) changes them for the steps after it, as on the runner. So a
check that passes only because a group from another job is installed fails here too, as it does
in CI.

First it checks that the Python in use is the patch version pinned in `.python-version`.

Steps that can't run on a contributor's machine are skipped and listed: installing system
packages (`sudo apt-get`), downloading the other runners' coverage, and the Secrets scan
(gitleaks, which needs a download; run with `--network` to include it, and pip-audit too).

    python tools/gates.py                    the checks and tests jobs
    python tools/gates.py --jobs build       also: checks, tests, build (slow)
    python tools/gates.py --network          include the steps that need the internet
"""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
PYTHON_VERSION = ROOT / ".python-version"
#: The jobs a contributor runs; `coverage` combines both runners' results and stays in CI.
DEFAULT_JOBS = ("checks", "tests")
#: Steps that need the internet beyond the package index.
NETWORK = ("pip-audit", "gitleaks")
#: Steps that need the runner itself (system packages, other runners' artifacts).
RUNNER_ONLY = ("sudo apt-get", "coverage combine")


def load_jobs(path: Path = CI) -> dict[str, Any]:
    """Return the `jobs` mapping of a workflow."""
    yaml: Any = importlib.import_module("yaml")  # PyYAML comes with pre-commit (dev group)
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def system() -> str:
    """Return this machine's name in the CI matrix ("windows" or "linux")."""
    return "windows" if platform.system() == "Windows" else "linux"


def expand(text: str, values: dict[str, str]) -> str:
    """Fill the `${{ … }}` expressions a local run can answer; the rest become empty."""
    out = text
    for key, value in values.items():
        out = out.replace("${{ " + key + " }}", value)
    while "${{" in out:
        start = out.index("${{")
        out = out[:start] + out[out.index("}}", start) + 2 :]
    return out


def steps(job: dict[str, Any], *, network: bool) -> list[tuple[str, str | None, str]]:
    """Return (name, command or None if skipped, reason) for each `run:` step of a job."""
    values = {"matrix.system": system(), "github.base_ref": "main"}
    found: list[tuple[str, str | None, str]] = []
    for step in job.get("steps", []):
        if "run" not in step:
            continue
        name = expand(str(step.get("name", "")), values)
        command = expand(str(step["run"]), values)
        if any(marker in command for marker in RUNNER_ONLY):
            found.append((name, None, "needs the CI runner"))
        elif not network and any(marker in command for marker in NETWORK):
            found.append((name, None, "needs the internet (--network)"))
        else:
            found.append((name, command, ""))
    return found


def pinned_python() -> str:
    return PYTHON_VERSION.read_text(encoding="utf-8").strip()


def check_python() -> str | None:
    """Return a problem if `uv run python` isn't the pinned patch version."""
    result = subprocess.run(  # noqa: S603 - uv, from PATH
        [shutil.which("uv") or "uv", "run", "--quiet", "python", "-c",
         "import platform; print(platform.python_version())"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    found = result.stdout.strip()
    wanted = pinned_python()
    if found != wanted:
        return f"Python {found or '?'} is in use, but .python-version pins {wanted}"
    return None


def run_job(name: str, job: dict[str, Any], *, network: bool) -> list[str]:
    """Run one job's steps; return the names of the steps that failed."""
    environment = os.environ | {
        "UV_FROZEN": "1",
        "PYTHONUTF8": "1",
        **{key: str(value) for key, value in (job.get("env") or {}).items()},
    }
    environment.pop("VIRTUAL_ENV", None)
    bash = shutil.which("bash") or "bash"
    failed: list[str] = []
    print(f"\n=== Job {name} ===")
    for step_name, command, reason in steps(job, network=network):
        if command is None:
            print(f"--- skipped: {step_name} ({reason})")
            continue
        started = time.monotonic()
        print(f"--- {step_name}", flush=True)
        result = subprocess.run(  # noqa: S603 - the workflow's own command
            [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", command],
            cwd=ROOT, env=environment, check=False,
        )  # fmt: skip
        verdict = "ok" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
        print(f"--- {step_name}: {verdict} in {time.monotonic() - started:.0f} s", flush=True)
        if result.returncode != 0:
            failed.append(f"{name}: {step_name}")
    return failed


def main(argv: list[str] | None = None) -> int:
    """Run the chosen jobs; exit 1 if the Python version or any step is wrong."""
    parser = argparse.ArgumentParser(description="Run the CI gates as CI runs them.")
    parser.add_argument("--jobs", default=",".join(DEFAULT_JOBS), help="comma-separated jobs")
    parser.add_argument("--network", action="store_true", help="include pip-audit and gitleaks")
    args = parser.parse_args(argv)
    jobs = load_jobs()
    wanted = [name.strip() for name in args.jobs.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in jobs]
    if unknown:
        print(f"Unknown jobs: {', '.join(unknown)}; ci.yml has {', '.join(jobs)}")
        return 2
    problem = check_python()
    if problem:
        print(problem)
        return 1
    failed: list[str] = []
    for name in wanted:
        failed += run_job(name, jobs[name], network=args.network)
    print()
    if failed:
        print("Failed steps:\n- " + "\n- ".join(failed))
        return 1
    print(f"Every step of {', '.join(wanted)} passed on Python {pinned_python()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
