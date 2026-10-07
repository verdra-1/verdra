# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Decision record 0019: the Windows test build ZIP, and the build check on that exact ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml  # PyYAML, dev group

from tools import pack_test_build

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "test-build.yml"


def built(tmp_path: Path) -> Path:
    """A stand-in for PyInstaller's one-folder build."""
    folder = tmp_path / "dist" / "Verdra"
    (folder / "_internal" / "PySide6").mkdir(parents=True)
    (folder / "verdra.exe").write_bytes(b"MZ executable")
    (folder / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(b"core")
    (folder / "_internal" / "LICENSE").write_text("license", encoding="utf-8")
    return folder


def files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_the_zip_holds_the_built_folder_and_the_read_me_and_unpacks_to_it(tmp_path: Path) -> None:
    folder = built(tmp_path)
    archive = pack_test_build.pack(folder, tmp_path / "out" / "Verdra-windows-test.zip", "abc123")
    with zipfile.ZipFile(archive) as opened:
        names = opened.namelist()
    assert all(name.startswith("Verdra/") for name in names)
    assert "Verdra/verdra.exe" in names and "Verdra/READ-ME.txt" in names
    unpacked = pack_test_build.unpack(archive, tmp_path / "unpacked")
    assert unpacked == tmp_path / "unpacked" / "Verdra"
    read_me = (unpacked / "READ-ME.txt").read_bytes()
    assert files(unpacked) == {**files(folder), "READ-ME.txt": read_me}  # byte for byte
    text = " ".join(read_me.decode("utf-8").split())  # the words, whatever the line breaks
    assert "\r\n" in read_me.decode("utf-8")  # Notepad shows the lines
    assert "commit abc123" in text
    assert "test build" in text and "isn't signed" in text
    assert '"More info", then "Run anyway"' in text
    assert "%LOCALAPPDATA%\\Verdra" in text


def test_only_a_built_folder_with_verdra_exe_is_packed(tmp_path: Path) -> None:
    empty = tmp_path / "dist" / "Verdra"
    empty.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="verdra.exe"):
        pack_test_build.pack(empty, tmp_path / "x.zip", "abc")


@pytest.mark.parametrize(
    ("entries", "problem"),
    [
        ({"Verdra/verdra.exe": b"x"}, "no Verdra/READ-ME.txt"),
        ({"Verdra/READ-ME.txt": b"x"}, "no Verdra/verdra.exe"),
        ({"Verdra/verdra.exe": b"x", "Verdra/READ-ME.txt": b"x", "Other/a": b"x"}, "unexpected"),
        (
            {"Verdra/verdra.exe": b"x", "Verdra/READ-ME.txt": b"x", "Verdra/../a": b"x"},
            "unexpected",
        ),
    ],
)
def test_unpack_refuses_anything_but_a_test_build(
    tmp_path: Path, entries: dict[str, bytes], problem: str
) -> None:
    archive = tmp_path / "Verdra-windows-test.zip"
    with zipfile.ZipFile(archive, "w") as opened:
        for name, data in entries.items():
            opened.writestr(name, data)
    with pytest.raises(ValueError, match=problem):
        pack_test_build.unpack(archive, tmp_path / "unpacked")
    assert not any((tmp_path / "unpacked").iterdir())  # nothing extracted


def test_unpack_needs_an_empty_folder(tmp_path: Path) -> None:
    archive = pack_test_build.pack(built(tmp_path), tmp_path / "t.zip", "abc")
    target = tmp_path / "unpacked"
    target.mkdir()
    (target / "old").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="isn't empty"):
        pack_test_build.unpack(archive, target)


def test_the_workflow_checks_and_uploads_that_exact_zip() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert set(workflow[True]) == {"push", "workflow_dispatch"}  # never on pull requests
    assert workflow[True]["push"] == {"branches": ["main"]}
    [job] = workflow["jobs"].values()
    assert job["runs-on"] == "windows-latest"
    runs = [step.get("run", "") for step in job["steps"]]
    assert any("pyinstaller packaging/verdra.spec" in run for run in runs)
    pack = next(run for run in runs if "pack_test_build.py dist/Verdra" in run)
    zip_path = pack.split()[pack.split().index("dist/Verdra") + 1]
    assert zip_path == "out/Verdra-windows-test.zip"
    check = next(run for run in runs if "--unpack" in run)
    assert f"--unpack {zip_path} unpacked" in check
    assert "check_build.py unpacked/Verdra --launch" in check
    [upload] = [s for s in job["steps"] if "upload-artifact" in s.get("uses", "")]
    assert upload["with"]["path"] == zip_path  # the file that was checked, not zipped again
    assert upload["with"]["archive"] is False
    # Nothing public beyond the artifact: no release, tag or package step.
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "release" not in text.split("jobs:")[1]
    assert "permissions: {}" in text
