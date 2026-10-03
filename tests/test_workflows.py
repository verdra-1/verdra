# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The workflows are safe to run on a public repository (plan 13.2, 13.5, decision record 0012).

No workflow runs fork code with write access or secrets: no `pull_request_target` or
`workflow_run` trigger, no permissions unless a job asks for them, no write permission in a
workflow that pull requests start, secrets only in a job of the release environment, every
action pinned to a full commit SHA and no checkout that keeps the token on disk.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))
PINNED = re.compile(r"^\s*(?:- )?uses: [\w.-]+/[\w./-]+@[0-9a-f]{40}(?: # v[\w.]+)?$")
JOB = re.compile(r"^  ([\w-]+):$")


def jobs(text: str) -> dict[str, str]:
    """Return each job's name and the text of its block."""
    lines = text.split("\n")
    start = lines.index("jobs:") + 1
    blocks: dict[str, list[str]] = {}
    current: list[str] = []
    for line in lines[start:]:
        match = JOB.match(line)
        if match:
            current = blocks.setdefault(match.group(1), [])
        elif line and not line.startswith(" ") and not line.startswith("#"):
            break
        current.append(line)
    return {name: "\n".join(block) for name, block in blocks.items()}


def test_the_workflows_are_found() -> None:
    assert {path.name for path in WORKFLOWS} >= {"ci.yml", "nightly.yml", "release.yml"}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_no_trigger_runs_fork_code_with_the_repository_token(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    # The trigger, not the API field `workflow_runs` that the duplicate-run report reads.
    assert re.search(r"\bworkflow_run\b", text) is None


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_every_job_names_its_own_permissions(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "\npermissions: {}\n" in text
    found = jobs(text)
    assert found
    for name, block in found.items():
        assert "\n    permissions:" in block, f"{path.name}: job {name} has no permissions"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_pull_requests_get_read_access_only(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if re.search(r"^  pull_request:", text, re.MULTILINE):
        assert ": write" not in text


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_secrets_only_in_the_release_environment(path: Path) -> None:
    for name, block in jobs(path.read_text(encoding="utf-8")).items():
        if "secrets." in block:
            assert path.name == "release.yml", f"{path.name}: job {name} reads a secret"
            assert "\n    environment: release" in block


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_every_action_is_pinned_and_no_checkout_keeps_the_token(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines):
        if "uses:" not in line:
            continue
        assert PINNED.match(line), f"{path.name}:{number + 1}: {line.strip()}"
        if "actions/checkout@" in line:
            step = "\n".join(lines[number + 1 : number + 4])
            assert "persist-credentials: false" in step, f"{path.name}:{number + 1}"


def test_the_job_parser_sees_every_job() -> None:
    text = "on: push\npermissions: {}\njobs:\n  a:\n    permissions: {}\n  b-c:\n    steps: []\n"
    assert list(jobs(text)) == ["a", "b-c"]
    assert "permissions" not in jobs(text)["b-c"]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_no_workflow_runs_on_macos(path: Path) -> None:
    # macOS is deferred until after 1.0 (decision record 0014): Windows and Linux runners only.
    assert re.search(r"macos-\w", path.read_text(encoding="utf-8")) is None
