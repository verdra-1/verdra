# SPDX-FileCopyrightText: 2026 q0f7
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
def test_every_job_runs_on_windows_only(path: Path) -> None:
    # Decision record 0018: Windows is the only platform; Linux is paused and macOS is deferred
    # until after 1.0 (decision record 0014). Every runner label is windows-latest.
    text = path.read_text(encoding="utf-8")
    assert re.search(r"macos-\w|ubuntu-\w|ubuntu-latest|runner\.os == 'Linux'", text) is None
    labels = set(re.findall(r"^\s*runs-on:\s*(\S+)", text, re.MULTILINE))
    matrix = set(re.findall(r"\brunner:\s*\[?([\w-]+)", text))
    assert labels <= {"windows-latest", "${{"} and matrix <= {"windows-latest"}, (labels, matrix)


#: Owner decision of 13 October 2026 (plan 16.2, decision record 0026): no public release before
#: 1.0.0. Anything that could publish a release, a tag or a package is refused in every workflow.
PUBLISHING = re.compile(
    r"\bgh release\b"  # GitHub CLI releases
    r"|repos/[^\s\"']*/releases\b(?!/download)"  # the releases API (not a public download URL)
    r"|\bgit (?:tag|push)\b"  # tags and pushes
    r"|(?:contents|packages|deployments|id-token|attestations|pages): write"  # write permissions
    r"|action-gh-release|create-release|upload-release-asset"  # release actions
    r"|^\s+tags:|^\s+release:",  # tag and release triggers
    re.MULTILINE,
)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_no_workflow_can_publish_before_1_0(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = [match.group(0).strip() for match in PUBLISHING.finditer(text)]
    assert found == [], f"{path.name} could publish: {found}"


def test_the_release_workflow_is_a_dry_run_started_by_hand() -> None:
    path = next(path for path in WORKFLOWS if path.name == "release.yml")
    text = path.read_text(encoding="utf-8")
    on = text[text.index("\non:") : text.index("\npermissions:")].splitlines()
    assert [line for line in on if line and not line.startswith("#")] == [
        "on:",
        "  workflow_dispatch:",
    ]
    assert list(jobs(text)) == ["build"]
    assert "retention-days: 5" in text


@pytest.mark.parametrize(
    "line",
    [
        "        run: gh release create v1 out/x.zip",
        "      contents: write",
        '    tags: ["v*"]',
        "        run: git push origin v0.1.0",
        "        run: curl -X POST https://api.github.com/repos/verdra-1/verdra/releases",
        "      - uses: softprops/action-gh-release@0123456789012345678901234567890123456789",
    ],
)
def test_the_publishing_guard_sees_each_way_to_publish(line: str) -> None:
    assert PUBLISHING.search(f"jobs:\n  a:\n{line}\n") is not None


def test_the_publishing_guard_allows_downloads_and_issue_reports() -> None:
    allowed = (
        "        run: curl -L https://github.com/gitleaks/gitleaks/releases/download/v8/x.zip\n"
        "      issues: write\n"
        "      contents: read\n"
    )
    assert PUBLISHING.search(allowed) is None


def test_a_release_dry_run_fails_unless_the_zips_app_passes_the_smoke_test() -> None:
    """M2 final test, 15 October 2026: a ZIP that routed nothing must never be handed out."""
    path = next(path for path in WORKFLOWS if path.name == "release.yml")
    build = jobs(path.read_text(encoding="utf-8"))["build"]
    steps = re.split(r"\n      - ", build)
    smoke = next(i for i, step in enumerate(steps) if "smoke_build.py unpacked/Verdra" in step)
    upload = next(i for i, step in enumerate(steps) if "upload-artifact" in step)
    assert smoke < upload
    assert "continue-on-error" not in steps[smoke]
    assert "if:" not in steps[smoke]
