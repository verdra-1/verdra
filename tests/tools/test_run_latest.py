# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/run-latest.ps1: update the verdra folder safely, set it up with uv, start Verdra.

The maintainer runs it before every real-machine test (decision record 0021). Two kinds of check:

- on every system, the script contains no command that deletes, resets or overwrites anything,
  pulls with a fast-forward only, syncs the locked packages with the pinned Python, and is plain
  ASCII (Windows PowerShell 5.1 reads a file without a byte-order mark as the local code page);
- on the Windows runner, it runs against throwaway repositories, with a fake `uv` that records
  what it was asked: it fast-forwards a clean folder, refuses a folder with local changes or
  local commits and changes nothing there, refuses a folder that isn't verdra, and starts
  Verdra with the arguments given.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "run-latest.ps1"
GITHUB = "https://github.com/verdra-1/verdra"

#: Anything that could lose the maintainer's work or reach beyond the folder.
FORBIDDEN = re.compile(
    r"git\s+(reset|clean|stash|checkout\s+--|restore|rebase|merge\b|push|branch\s+-D)|--force|"
    r"\s-f\b|Remove-Item|\brm\b|\bdel\b|rmdir|Invoke-WebRequest|Invoke-RestMethod|\biwr\b|"
    r"Start-Process|Set-ExecutionPolicy",
    re.IGNORECASE,
)


def code() -> str:
    """The script without its comment block and comment lines."""
    text = re.sub(r"<#.*?#>", "", SCRIPT.read_text(encoding="utf-8"), flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_script_never_deletes_resets_or_overwrites() -> None:
    found = FORBIDDEN.search(code())
    assert found is None, found
    assert "git pull --ff-only origin main" in code()
    assert "git status --porcelain" in code()
    assert "uv sync --locked --python $Python" in code()
    assert ".python-version" in code()


def test_a_missing_tool_or_wrong_folder_says_exactly_what_to_do() -> None:
    """The preflight messages carry the exact commands (maintainer, 11 October 2026)."""
    text = code()
    assert "winget install --id Git.Git -e --source winget" in text
    assert "winget install --id astral-sh.uv -e" in text
    assert text.count("close PowerShell, ") == 2  # then open it again
    assert "git config --get remote.origin.url" in text
    assert "verdra-1/verdra" in text
    assert "git clone https://github.com/verdra-1/verdra" in text
    assert "never delete it" in text


def test_the_script_is_plain_ascii() -> None:
    SCRIPT.read_bytes().decode("ascii")


# --- On Windows: real runs against throwaway repositories ----------------------------------

windows = pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")


def git(folder: Path, *arguments: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed arguments, the test's own folders
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *arguments],  # noqa: S607
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(the maintainer's verdra folder, one commit behind GitHub; GitHub; the uv record)."""
    seed = tmp_path / "seed"
    (seed / "tools").mkdir(parents=True)
    (seed / "pyproject.toml").write_text('[project]\nname = "verdra"\n', encoding="utf-8")
    (seed / ".python-version").write_text("3.14.8\n", encoding="utf-8")
    shutil.copy(SCRIPT, seed / "tools" / "run-latest.ps1")
    git(seed, "init", "-b", "main")
    git(seed, "add", "-A")
    git(seed, "commit", "-m", "first")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "--bare", str(seed), str(origin))
    mine = tmp_path / "verdra"
    git(tmp_path, "clone", str(origin), str(mine))
    # The real origin's address, sent to the throwaway one: the script checks the address.
    git(mine, "config", "remote.origin.url", GITHUB)
    git(mine, "config", f"url.{origin.as_posix()}.insteadOf", GITHUB)
    (seed / "NEWS").write_text("newer\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-m", "second")
    git(seed, "push", str(origin), "main")
    record = tmp_path / "uv-calls.txt"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uv.cmd").write_text(f'@echo %*>> "{record}"\r\n@exit /b 0\r\n', encoding="ascii")
    return mine, origin, record


def run(
    folder: Path, record: Path, *arguments: str, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the script with the fake uv first on PATH, or with exactly `path`."""
    environment = dict(os.environ)
    environment["PATH"] = (
        path if path is not None else str(record.parent / "bin") + os.pathsep + environment["PATH"]
    )
    return subprocess.run(  # noqa: S603 - the script under test
        [
            shutil.which("powershell") or "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(folder / "tools" / "run-latest.ps1"),
            *arguments,
        ],
        cwd=folder,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )


@windows
def test_a_clean_folder_is_fast_forwarded_and_set_up(folders: tuple[Path, Path, Path]) -> None:
    mine, origin, record = folders
    done = run(mine, record, "-NoStart")
    assert done.returncode == 0, done.stdout + done.stderr
    assert git(mine, "rev-parse", "HEAD") == git(origin, "rev-parse", "main")
    assert (mine / "NEWS").is_file()
    assert record.read_text(encoding="ascii").split() == ["sync", "--locked", "--python", "3.14.8"]


@windows
def test_verdra_starts_with_the_arguments_given(folders: tuple[Path, Path, Path]) -> None:
    mine, _origin, record = folders
    done = run(mine, record, "--format-capture", "15553230204")
    assert done.returncode == 0, done.stdout + done.stderr
    calls = record.read_text(encoding="ascii").splitlines()
    assert calls[-1].split() == [
        "run", "--locked", "--python", "3.14.8", "python", "-m", "verdra",
        "--format-capture", "15553230204",
    ]  # fmt: skip


@windows
def test_local_changes_are_never_touched(folders: tuple[Path, Path, Path]) -> None:
    mine, _origin, record = folders
    before = git(mine, "rev-parse", "HEAD")
    (mine / "pyproject.toml").write_text('[project]\nname = "verdra"\n# mine\n', encoding="utf-8")
    (mine / "notes.txt").write_text("my notes\n", encoding="utf-8")
    done = run(mine, record, "-NoStart")
    assert done.returncode == 1
    assert "pyproject.toml" in done.stdout and "notes.txt" in done.stdout
    assert "Nothing was changed." in done.stdout
    assert git(mine, "rev-parse", "HEAD") == before
    assert "# mine" in (mine / "pyproject.toml").read_text(encoding="utf-8")
    assert (mine / "notes.txt").read_text(encoding="utf-8") == "my notes\n"
    assert not record.exists()  # uv never ran


@windows
def test_local_commits_are_kept_and_nothing_is_forced(folders: tuple[Path, Path, Path]) -> None:
    mine, _origin, record = folders
    (mine / "LOCAL").write_text("mine\n", encoding="utf-8")
    git(mine, "add", "-A")
    git(mine, "commit", "-m", "local")
    mine_head = git(mine, "rev-parse", "HEAD")
    done = run(mine, record, "-NoStart")
    assert done.returncode == 1
    assert "could not be updated by simply moving forward" in done.stdout
    assert git(mine, "rev-parse", "HEAD") == mine_head


@windows
def test_a_folder_that_isnt_verdra_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "other"
    (other / "tools").mkdir(parents=True)
    shutil.copy(SCRIPT, other / "tools" / "run-latest.ps1")
    record = tmp_path / "uv-calls.txt"
    (tmp_path / "bin").mkdir()
    done = run(other, record, "-NoStart")
    assert done.returncode == 1
    assert "isn't one" in done.stdout
    assert not record.exists()


def system_path() -> list[str]:
    """Windows' own folders, so PowerShell itself still runs."""
    root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return [rf"{root}\System32", rf"{root}\System32\WindowsPowerShell\v1.0", root]


@windows
def test_without_git_it_names_the_winget_command(folders: tuple[Path, Path, Path]) -> None:
    mine, _origin, record = folders
    path = os.pathsep.join([str(record.parent / "bin"), *system_path()])
    done = run(mine, record, "-NoStart", path=path)
    assert done.returncode == 1
    assert "git is not installed" in done.stdout
    assert "winget install --id Git.Git -e --source winget" in done.stdout
    assert "close PowerShell, open it again" in done.stdout
    assert not record.exists()


@windows
def test_without_uv_it_names_the_winget_command(folders: tuple[Path, Path, Path]) -> None:
    mine, _origin, record = folders
    found = shutil.which("git")
    assert found is not None
    git_folder = Path(found).parent
    if (git_folder / "uv.exe").exists():
        pytest.skip("uv is installed next to git on this runner")
    done = run(mine, record, "-NoStart", path=os.pathsep.join([str(git_folder), *system_path()]))
    assert done.returncode == 1
    assert "uv is not installed" in done.stdout
    assert "winget install --id astral-sh.uv -e" in done.stdout
    assert "close PowerShell, open it again" in done.stdout


@windows
def test_a_copy_from_elsewhere_is_refused_with_the_clone_steps(
    folders: tuple[Path, Path, Path],
) -> None:
    mine, _origin, record = folders
    before = git(mine, "rev-parse", "HEAD")
    git(mine, "config", "remote.origin.url", "https://github.com/someone/verdra")
    done = run(mine, record, "-NoStart")
    assert done.returncode == 1
    assert "wasn't downloaded from github.com/verdra-1/verdra" in done.stdout
    assert "verdra-old; never delete it" in done.stdout
    assert "git clone https://github.com/verdra-1/verdra" in done.stdout
    assert git(mine, "rev-parse", "HEAD") == before
    assert not record.exists()
