# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Decision record 0012: what CI runs and which check it reports, for each event.

Runs the plan job's own script and evaluates the workflow's own expressions (the final check's
name and the run title) from .github/workflows/ci.yml, so the table below is what CI does.
Only a run against main may report "All gates green", the check branch protection requires.
An edit that isn't a retarget skips the final job, and GitHub shows a skipped job's name
unevaluated (the raw expression), so a no-op run can neither pass nor block that check.
"""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml  # PyYAML comes with pre-commit (dev group)

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
ALL = "All gates green"
STACKED = "Full gates green (stacked)"
NO_OP = "No-op (edited)"


def workflow() -> dict[Any, Any]:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def plan_script() -> str:
    """Return the `run: |` block of the plan job's `mode` step."""
    lines = CI.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "- id: mode")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run]) - len(lines[run].lstrip()) + 2
    block: list[str] = []
    for line in lines[run + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        block.append(line)
    return textwrap.dedent("\n".join(block))


def evaluate(template: str, context: dict[str, Any]) -> str:
    """Evaluate the `${{ … }}` parts of a GitHub expression template against `context`.

    Covers what ci.yml uses: dotted `github.…` lookups (missing ones are null), string
    literals, `==`, `!=`, `!`, `&&`, `||` and parentheses, with GitHub's rule that `&&` and
    `||` return one of their operands.
    """

    def lookup(path: str) -> Any:
        value: Any = context
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    def one(expression: str) -> str:
        python = re.sub(
            r"\bgithub(?:\.[A-Za-z_]+)+", lambda m: f"lookup({m.group(0)!r})", expression
        )
        python = python.replace("&&", " and ").replace("||", " or ")
        python = re.sub(r"!(?!=)", " not ", python)
        python = re.sub(r"\bnull\b", "None", python)
        value = eval(python, {"lookup": lookup})  # noqa: S307 - our own workflow file
        if isinstance(value, bool):
            return "true" if value else "false"
        return "" if value is None else str(value)

    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: one(m.group(1)), template, flags=re.DOTALL)


def event(action: str = "synchronize", base: str = "x", base_from: str | None = None) -> dict:
    """Return a `github` context for a pull request event (or a push with action "push")."""
    if action == "push":
        return {"github": {"event_name": "push", "event": {}, "ref_name": "main"}}
    payload: dict[str, Any] = {"action": action, "pull_request": {"base": {"ref": base}}}
    if base_from is not None:
        payload["changes"] = {"base": {"ref": {"from": base_from}}}
    return {
        "github": {
            "event_name": "pull_request",
            "event": payload,
            "base_ref": base,
            "head_ref": "spec/S-01-screens",
        }
    }


def plan(tmp_path: Path, context: dict) -> str:
    """Run the plan job's script for `context` and return its mode."""
    bash = shutil.which("bash")
    assert bash is not None
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    step = next(s for s in workflow()["jobs"]["plan"]["steps"] if s.get("id") == "mode")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_OUTPUT": str(output),
        **{name: evaluate(value, context) for name, value in step["env"].items()},
    }
    subprocess.run([bash, "-e", "-c", plan_script()], env=env, check=True, capture_output=True)  # noqa: S603
    pairs = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    return pairs["mode"]


EVENTS = [
    # (context, mode, final check name)
    (event("push"), "full", ALL),
    (event(base="main"), "full", ALL),
    (event("opened", base="main"), "full", ALL),
    (event("reopened", base="main"), "full", ALL),
    (event(base="spec/S-01-screens"), "full", STACKED),
    (event("opened", base="spec/S-01-screens"), "full", STACKED),
    # Title or description edited: nothing runs, and no required check is reported.
    (event("edited", base="main"), "skip", NO_OP),
    (event("edited", base="spec/S-01-screens"), "skip", NO_OP),
    # The base branch moved but the pull request still points at it: not a retarget.
    (event("edited", base="main", base_from="main"), "skip", NO_OP),
    # Retargeted to main once the pull request below merged: a new full run against main.
    (event("edited", base="main", base_from="spec/S-01-screens"), "full", ALL),
    (event("edited", base="docs/m1-specs", base_from="main"), "full", STACKED),
]


@pytest.mark.parametrize(("context", "mode", "name"), EVENTS)
def test_each_event_runs_and_reports_as_decided(
    tmp_path: Path, context: dict, mode: str, name: str
) -> None:
    assert plan(tmp_path, context) == mode
    assert evaluate(workflow()["jobs"]["ci-ok"]["name"], context) == name


@pytest.mark.parametrize(("context", "mode", "name"), EVENTS)
def test_the_no_op_name_marks_exactly_the_skipped_runs(
    tmp_path: Path, context: dict, mode: str, name: str
) -> None:
    # The final job is skipped in skip mode, and GitHub then shows its name unevaluated. Should
    # GitHub ever evaluate it, it must be the no-op one: a skipped "All gates green" would count
    # as passed.
    assert (evaluate(workflow()["jobs"]["ci-ok"]["name"], context) == NO_OP) == (mode == "skip")


def test_only_the_final_job_names_the_required_check() -> None:
    jobs = workflow()["jobs"]
    names = {job_id: str(job.get("name", "")) for job_id, job in jobs.items()}
    assert [job_id for job_id, name in names.items() if ALL in name] == ["ci-ok"]
    # A skipped run's check shows the name as written, which is never the required check's.
    assert names["ci-ok"].strip() != ALL
    # It is named from the event alone: a skipped or canceled job can't read `needs`.
    assert "needs." not in names["ci-ok"]
    assert jobs["ci-ok"]["if"] == "${{ !cancelled() && needs.plan.outputs.mode != 'skip' }}"


def test_the_run_title_names_the_event() -> None:
    title = workflow()["run-name"]
    assert evaluate(title, event()) == "CI: synchronize on spec/S-01-screens"
    assert evaluate(title, event("edited", base="main")) == "CI: edited on spec/S-01-screens"
    retarget = event("edited", base="main", base_from="docs/claude-md")
    assert evaluate(title, retarget) == "CI: edited (retarget) on spec/S-01-screens"
    assert evaluate(title, event("push")) == "CI: push on main"


def test_one_run_per_pull_request_head() -> None:
    concurrency = workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    group = concurrency["group"]
    real = evaluate(group, {"github": {**event()["github"], "ref": "refs/pull/26/merge"}})
    no_op = evaluate(group, {"github": {**event("edited")["github"], "ref": "refs/pull/26/merge"}})
    retarget = event("edited", base="main", base_from="x")
    assert real == "ci-refs/pull/26/merge-run"
    assert no_op == "ci-refs/pull/26/merge-ignored-event"
    assert evaluate(group, {"github": {**retarget["github"], "ref": "refs/pull/26/merge"}}) == real
    # "labeled" no longer starts runs.
    assert workflow()[True]["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "edited",
    ]


def test_the_duplicate_run_report_never_fails_the_job() -> None:
    job = workflow()["jobs"]["ci-ok"]
    report = job["steps"][0]
    assert report["name"].startswith("Other completed runs for this head")
    assert report["continue-on-error"] is True
    assert job["permissions"] == {"actions": "read"}


def test_every_run_is_a_full_run() -> None:
    text = CI.read_text(encoding="utf-8")
    # Decision record 0012: no fast mode, no markers left out. Decision record 0014: Windows and
    # Linux runners only; macOS is deferred until after 1.0.
    assert "fast" not in plan_script()
    assert 'pytest -m "not slow"' not in text
    jobs = workflow()["jobs"]
    tests = [
        (entry["runner"], entry["system"])
        for entry in jobs["tests"]["strategy"]["matrix"]["include"]
    ]
    assert tests == [("windows-latest", "windows"), ("ubuntu-24.04", "linux")]
    assert jobs["build"]["strategy"]["matrix"]["runner"] == ["windows-latest", "ubuntu-24.04"]
    assert "macos-" not in text  # no macOS runner label
