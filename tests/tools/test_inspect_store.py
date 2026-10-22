# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/inspect_store.py: structure only, from a copy, never the live folder (decision 0028)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from tools import inspect_store

ASSET = 15553230204
KTX2 = b"\xabKTX 20\xbb\r\n\x1a\n" + b"secret picture bytes"
SECRET_URL = "https://example.invalid/private?token=do-not-print"


def synthetic_store(root: Path) -> Path:
    """A made-up store: a table naming content-addressed files, one row for ASSET."""
    copy = root / "copy"
    folder = copy / inspect_store.FOLDER
    names: list[str] = []
    for index, body in enumerate((KTX2, b"\x28\xb5\x2f\xfd" + b"x" * 40, b"plain")):
        digest = hashlib.md5(body + bytes([index])).hexdigest()  # noqa: S324 - a content name
        (folder / digest[:2]).mkdir(parents=True, exist_ok=True)
        (folder / digest[:2] / digest).write_bytes(body + bytes([index]))
        names.append(digest)
    connection = sqlite3.connect(copy / inspect_store.DATABASE)
    connection.execute("CREATE TABLE content (hash TEXT PRIMARY KEY, size INTEGER, url TEXT)")
    connection.execute("CREATE TABLE assets (asset_id INTEGER, hash TEXT)")
    for name in names:
        connection.execute("INSERT INTO content VALUES (?, ?, ?)", (name, 10, SECRET_URL))
    connection.execute("INSERT INTO assets VALUES (?, ?)", (ASSET, names[0]))
    connection.commit()
    connection.close()
    return copy


def test_the_report_shows_shape_and_never_values(tmp_path: Path) -> None:
    copy = synthetic_store(tmp_path)
    text = "\n".join(inspect_store.inspect(copy, ASSET).lines())
    assert "table assets: 1 rows" in text
    assert "column hash: hex32 ×3" in text
    assert f"{ASSET} appears in assets.asset_id" in text
    assert "folder names: hex2" in text
    assert "file names: hex32 ×3" in text
    assert "KTX2 ×1" in text and "zstd ×1" in text and "unknown ×1" in text
    assert "md5: 3" in text
    assert "content.hash: 3 of 3 values name a file" in text
    assert "assets.hash: 1 of 1 values name a file" in text
    # Nothing from inside the store: no hash, no URL, no file content.
    database = sqlite3.connect(copy / inspect_store.DATABASE)
    for (value,) in database.execute("SELECT hash FROM content"):
        assert value not in text
    database.close()
    assert "token" not in text and "example.invalid" not in text and "secret" not in text


def test_the_copy_itself_is_not_changed(tmp_path: Path) -> None:
    copy = synthetic_store(tmp_path)
    before = {p: p.read_bytes() for p in copy.rglob("*") if p.is_file()}
    inspect_store.inspect(copy, ASSET)
    assert {p: p.read_bytes() for p in copy.rglob("*") if p.is_file()} == before


def test_roblox_own_folder_is_refused(tmp_path: Path) -> None:
    live = tmp_path / "Local" / "Roblox"
    live.mkdir(parents=True)
    environment = {"LOCALAPPDATA": str(tmp_path / "Local")}
    for folder in (live, live / "rbx-storage"):
        with pytest.raises(inspect_store.LiveStoreError):
            inspect_store.refuse_live(folder, environment)
    inspect_store.refuse_live(tmp_path / "copy", environment)  # a copy elsewhere is fine


def test_the_command_refuses_the_live_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Roblox").mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert inspect_store.main([str(tmp_path / "Roblox")]) == 2


def test_the_command_writes_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    copy = synthetic_store(tmp_path)
    out = tmp_path / "report.txt"
    assert inspect_store.main([str(copy), "--asset", str(ASSET), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == capsys.readouterr().out
    assert "## Content addressing" in out.read_text(encoding="utf-8")


def test_a_missing_store_is_described_not_failed(tmp_path: Path) -> None:
    lines = inspect_store.inspect(tmp_path, ASSET).lines()
    assert "- no rbx-storage.db in the copy" in lines
    assert "- no rbx-storage folder in the copy" in lines


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "null"), (7, "int"), ("abc123", "hex6"), ("Hello", "text5"), (b"12", "blob2")],
)
def test_shapes(value: object, expected: str) -> None:
    assert inspect_store.shape(value) == expected
