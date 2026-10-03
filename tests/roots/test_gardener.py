# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-10: the CA block in Roblox trust files (rules 2 to 4, tests 2 and 7)."""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from verdra.bark import resin, scar
from verdra.roots import gardener
from verdra.soil import terrain

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def authority() -> resin.Authority:
    return resin.create_authority(NOW)


def bundle(newline: str = "\n", trailing: bool = True) -> bytes:
    """A trust-file stand-in: two other CAs' PEM blocks, as cacert.pem files hold them."""
    other = resin.create_authority(NOW).certificate
    another = resin.create_authority(NOW).certificate
    text = (
        "## Bundle of CA Root Certificates\n\nOther CA\n"
        + resin.certificate_pem(other).decode()
        + "\nAnother CA\n"
        + resin.certificate_pem(another).decode()
    )
    if not trailing:
        text = text.rstrip("\n")
    return text.replace("\n", newline).encode()


#: Until the trust files are recorded on real machines (plan 16.4), these stand in for them.
FIXTURES = {
    "lf": bundle(),
    "crlf": bundle("\r\n"),
    "no final newline": bundle(trailing=False),
    "empty": b"",
}


def blocks(data: bytes) -> int:
    return data.count(terrain.CA_BEGIN_MARKER.encode())


@pytest.mark.spec("S-10", 2)
@pytest.mark.parametrize("name", list(FIXTURES))
@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
def test_the_block_goes_in_once_and_comes_out_byte_identical(
    tmp_path: Path, authority: resin.Authority, name: str, read_only: bool
) -> None:
    original = FIXTURES[name]
    path = tmp_path / "cacert.pem"
    path.write_bytes(original)
    if read_only:
        os.chmod(path, stat.S_IREAD)
    mode = stat.S_IMODE(path.stat().st_mode)
    book = scar.Ledger(tmp_path / "changes.json")
    assert gardener.add_ca(path, authority.certificate, book)
    assert not gardener.add_ca(path, authority.certificate, book)  # adding twice: still one
    changed = path.read_bytes()
    assert blocks(changed) == 1
    assert changed.startswith(original.rstrip(b"\r\n"))
    assert stat.S_IMODE(path.stat().st_mode) == mode
    (entry,) = book.entries()
    assert entry.kind == "ca_roblox_bundle"
    assert entry.state == "done"
    assert entry.target == str(path)
    for opened in list(book.open_entries()):
        gardener.remove_ca(opened, book)
    assert path.read_bytes() == original
    assert stat.S_IMODE(path.stat().st_mode) == mode
    assert [e.state for e in book.entries()] == ["removed"]
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.spec("S-10", 2)
def test_a_block_the_ledger_doesnt_know_is_replaced_not_doubled(
    tmp_path: Path, authority: resin.Authority
) -> None:
    path = tmp_path / "cacert.pem"
    old = resin.create_authority(NOW).certificate
    path.write_bytes(FIXTURES["lf"] + resin.trust_block(old).encode())
    book = scar.Ledger(tmp_path / "changes.json")
    assert gardener.add_ca(path, authority.certificate, book)
    data = path.read_bytes()
    assert blocks(data) == 1
    assert resin.trust_block(authority.certificate).encode() in data
    assert resin.trust_block(old).encode() not in data


@pytest.mark.spec("S-10", 7)
def test_the_ledger_entry_is_written_before_the_file_changes(
    tmp_path: Path, authority: resin.Authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    ledger_file = tmp_path / "changes.json"
    book = scar.Ledger(ledger_file)
    seen: list[str] = []

    def crash(target: Path, data: bytes, mode: int) -> None:
        # The process dies right here: the entry must already be on disk, the file untouched.
        seen.extend(e.state for e in scar.Ledger(ledger_file).entries())
        raise SystemExit

    monkeypatch.setattr(gardener, "_write_keeping_mode", crash)
    with pytest.raises(SystemExit):
        gardener.add_ca(path, authority.certificate, book)
    monkeypatch.undo()
    assert seen == ["pending"]
    assert path.read_bytes() == FIXTURES["lf"]
    # After the "restart", Reset everything finds the pending entry and undoes it cleanly.
    after = scar.Ledger(ledger_file)
    (entry,) = after.open_entries()
    assert entry.state == "pending"
    gardener.remove_ca(entry, after)
    assert path.read_bytes() == FIXTURES["lf"]
    assert [e.state for e in after.entries()] == ["removed"]


def test_a_failed_write_marks_the_entry_failed(
    tmp_path: Path, authority: resin.Authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    book = scar.Ledger(tmp_path / "changes.json")

    def full(target: Path, data: bytes, mode: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(gardener, "_write_keeping_mode", full)
    with pytest.raises(OSError, match="No space"):
        gardener.add_ca(path, authority.certificate, book)
    (entry,) = book.entries()
    assert entry.state == "failed"
    assert "No space" in entry.details["error"]


def test_removing_from_a_file_that_is_gone_or_was_replaced(
    tmp_path: Path, authority: resin.Authority
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    book = scar.Ledger(tmp_path / "changes.json")
    gardener.add_ca(path, authority.certificate, book)
    (entry,) = book.open_entries()
    path.write_bytes(FIXTURES["crlf"])  # Roblox replaced the file: nothing of ours left
    gardener.remove_ca(entry, book)
    assert path.read_bytes() == FIXTURES["crlf"]
    gardener.add_ca(path, authority.certificate, book)
    (second,) = book.open_entries()
    path.unlink()
    gardener.remove_ca(second, book)
    assert [e.state for e in book.entries()] == ["removed", "removed"]
